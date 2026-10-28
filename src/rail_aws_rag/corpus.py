"""Corpus manifest and passages: parsed sections split into passages that keep citation keys.

Chunking is the rail-regulation-rag logic unchanged, so passage ids match the golden set.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
PROCESSED_DIR = DATA_DIR / "processed"
MANIFEST = DATA_DIR / "sources.yaml"

MAX_WORDS = 250  # ~330 tokens, below the 512-token limit of the embedding model
OVERLAP = 40


@dataclass(frozen=True)
class Document:
    id: str
    short: str
    celex: str
    title: str


@dataclass(frozen=True)
class Passage:
    id: str  # "<doc_id>:<section>#<n>", the citation key used everywhere downstream
    doc_id: str
    doc_short: str
    section: str
    heading: str
    text: str

    @property
    def citation(self) -> str:
        return f"{self.doc_short}, {self.section}"

    @property
    def embed_text(self) -> str:
        return f"{self.doc_short}, {self.heading}\n{self.text}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Passage:
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


def load_manifest(path: Path = MANIFEST) -> list[Document]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        Document(**{k: str(d[k]).strip() for k in Document.__dataclass_fields__})
        for d in data["documents"]
    ]


def _windows(words: list[str], max_words: int, overlap: int) -> list[str]:
    step = max_words - overlap
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words) - overlap, step)]


def chunk_section(
    record: dict, doc_short: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP
) -> list[Passage]:
    pieces: list[str] = []
    for para in record["text"].split("\n"):
        words = para.split()
        if len(words) > max_words:
            pieces += _windows(words, max_words, overlap)
        else:
            pieces.append(para)

    # Greedily pack whole paragraphs into passages of at most max_words.
    chunks: list[list[str]] = []
    size = 0
    for piece in pieces:
        n = len(piece.split())
        if chunks and size + n <= max_words:
            chunks[-1].append(piece)
            size += n
        else:
            chunks.append([piece])
            size = n

    base = f"{record['doc_id']}:{record['section']}"
    return [
        Passage(
            id=f"{base}#{i}",
            doc_id=record["doc_id"],
            doc_short=doc_short,
            section=record["section"],
            heading=record["heading"],
            text="\n".join(chunk),
        )
        for i, chunk in enumerate(chunks, start=1)
    ]


def load_passages(
    documents: list[Document] | None = None, processed_dir: Path = PROCESSED_DIR
) -> list[Passage]:
    passages: list[Passage] = []
    for doc in documents or load_manifest():
        lines = (processed_dir / f"{doc.id}.jsonl").read_text(encoding="utf-8").splitlines()
        for line in lines:
            passages += chunk_section(json.loads(line), doc_short=doc.short)
    return passages
