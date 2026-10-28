"""The on-disk index and in-memory search: no database, just three files and numpy.

Files (all written by `build_index`, then copied to S3):
- passages.json: the manifest documents and every passage, in row order;
- vectors.npy: one unit-length float32 row per passage (cosine == dot product);
- bm25.npz: the BM25 term-frequency part per passage in CSR form (indptr, indices, values);
- manifest.json: format version, model names and a sha256 per file.

Search mirrors the Qdrant setup of rail-regulation-rag: dense cosine, optional BM25 with IDF
applied at query time, the two top-50 lists fused with Reciprocal Rank Fusion (k=60), and every
hit scored with its cosine similarity so the refusal floor stays portable.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rail_aws_rag.corpus import Document, Passage

FORMAT_VERSION = 1
FILES = ("passages.json", "vectors.npy", "bm25.npz")
HYBRID_CANDIDATES = 50  # per retriever, before fusion
RRF_K = 60


@dataclass(frozen=True)
class SearchHit:
    passage: Passage
    score: float  # cosine similarity, higher is better (also in hybrid mode)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_index(
    out_dir: Path,
    documents: list[Document],
    passages: list[Passage],
    vectors: list[list[float]],
    sparse: list[tuple[list[int], list[float]]],
    *,
    dense_model: str,
    sparse_model: str,
) -> dict:
    """Write the index files and return the manifest. Output is byte-for-byte reproducible."""
    if not (len(passages) == len(vectors) == len(sparse)):
        raise ValueError("passages, vectors and sparse vectors must have the same length")
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "documents": [d.__dict__ for d in documents],
        "passages": [p.to_dict() for p in passages],
    }
    (out_dir / "passages.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8"
    )
    matrix = np.asarray(vectors, dtype=np.float32)
    np.save(out_dir / "vectors.npy", matrix)

    lengths = [len(indices) for indices, _ in sparse]
    np.savez(
        out_dir / "bm25.npz",
        indptr=np.concatenate(([0], np.cumsum(lengths))).astype(np.int64),
        indices=np.asarray([i for indices, _ in sparse for i in indices], dtype=np.int64),
        values=np.asarray([v for _, values in sparse for v in values], dtype=np.float32),
    )

    manifest = {
        "format_version": FORMAT_VERSION,
        "dense_model": dense_model,
        "sparse_model": sparse_model,
        "dim": int(matrix.shape[1]) if matrix.size else 0,
        "n_passages": len(passages),
        "files": {name: sha256_file(out_dir / name) for name in FILES},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _top(scores: np.ndarray, k: int, *, positive_only: bool = False) -> np.ndarray:
    """Row numbers of the k best scores. Ties go to the lower row number, so results are stable."""
    order = np.lexsort((np.arange(len(scores)), -scores))
    if positive_only:
        order = order[scores[order] > 0]
    return order[:k]


class Index:
    def __init__(
        self,
        documents: list[Document],
        passages: list[Passage],
        vectors: np.ndarray,
        indptr: np.ndarray,
        indices: np.ndarray,
        values: np.ndarray,
        manifest: dict | None = None,
    ):
        if not (len(passages) == vectors.shape[0] == len(indptr) - 1):
            raise ValueError("index files disagree on the number of passages")
        self.documents, self.passages, self.vectors = documents, passages, vectors
        self.manifest = manifest or {}
        self._postings, self._idf = self._build_postings(indptr, indices, values)

    @classmethod
    def load(cls, directory: Path | str, *, verify: bool = True) -> Index:
        directory = Path(directory)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"unsupported index format {manifest.get('format_version')!r}")
        if verify:
            for name, expected in manifest["files"].items():
                if sha256_file(directory / name) != expected:
                    raise ValueError(f"{name} does not match its checksum in manifest.json")
        payload = json.loads((directory / "passages.json").read_text(encoding="utf-8"))
        bm25 = np.load(directory / "bm25.npz")
        return cls(
            documents=[Document(**d) for d in payload["documents"]],
            passages=[Passage.from_dict(p) for p in payload["passages"]],
            vectors=np.load(directory / "vectors.npy"),
            indptr=bm25["indptr"],
            indices=bm25["indices"],
            values=bm25["values"],
            manifest=manifest,
        )

    @staticmethod
    def _build_postings(indptr, indices, values):
        n = len(indptr) - 1
        if len(indices) == 0:
            return {}, {}
        rows = np.repeat(np.arange(n), np.diff(indptr))
        order = np.argsort(indices, kind="stable")
        terms, rows, vals = indices[order], rows[order], values[order]
        starts = np.concatenate(([0], np.flatnonzero(np.diff(terms)) + 1))
        ends = np.concatenate((starts[1:], [len(terms)]))
        postings = {
            int(terms[s]): (rows[s:e], vals[s:e]) for s, e in zip(starts, ends, strict=True)
        }
        # Qdrant's IDF modifier: ln(1 + (N - n + 0.5) / (n + 0.5)), n = passages containing the term
        idf = {
            t: math.log(1 + (n - len(r) + 0.5) / (len(r) + 0.5)) for t, (r, _) in postings.items()
        }
        return postings, idf

    def __len__(self) -> int:
        return len(self.passages)

    def search(
        self,
        vector: list[float],
        k: int = 8,
        sparse: tuple[list[int], list[float]] | None = None,
    ) -> list[SearchHit]:
        """Dense search, or hybrid (BM25 + dense, RRF) when ``sparse`` query terms are given.

        Hits come in rank order; scores are cosine similarities either way.
        """
        query = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(query))
        cosines = self.vectors @ (query / norm if norm else query)

        if sparse is None:
            ranked = _top(cosines, k)
        else:
            dense_ids = _top(cosines, HYBRID_CANDIDATES)
            bm25 = np.zeros(len(self), dtype=np.float32)
            for term, weight in zip(*sparse, strict=True):
                if term in self._postings:
                    rows, vals = self._postings[term]
                    bm25[rows] += self._idf[term] * weight * vals
            sparse_ids = _top(bm25, HYBRID_CANDIDATES, positive_only=True)
            fused: dict[int, float] = {}
            for ids in (dense_ids, sparse_ids):
                for rank, row in enumerate(ids, start=1):
                    fused[int(row)] = fused.get(int(row), 0.0) + 1.0 / (RRF_K + rank)
            ranked = sorted(fused, key=lambda r: (-fused[r], -float(cosines[r]), r))[:k]

        return [SearchHit(self.passages[int(r)], float(cosines[int(r)])) for r in ranked]
