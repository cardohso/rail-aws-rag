"""Embed every passage offline and write the index files.

    uv run python -m rail_aws_rag.build_index --out build/index

Nothing here calls AWS. Copy the output to the data bucket with `aws s3 sync` (see README).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from rail_aws_rag import corpus
from rail_aws_rag.embeddings import BM25Encoder, LocalEmbedder
from rail_aws_rag.index import write_index


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=corpus.REPO_ROOT / "build" / "index")
    args = ap.parse_args(argv)

    documents = corpus.load_manifest()
    passages = corpus.load_passages(documents)
    texts = [p.embed_text for p in passages]

    t0 = time.perf_counter()
    dense = LocalEmbedder()
    sparse = BM25Encoder()
    manifest = write_index(
        args.out,
        documents,
        passages,
        dense.embed_documents(texts),
        sparse.embed_documents(texts),
        dense_model=dense.model_name,
        sparse_model=sparse.model_name,
    )
    print(
        f"{manifest['n_passages']} passages, dim {manifest['dim']}, "
        f"{time.perf_counter() - t0:.0f}s -> {args.out}"
    )
    for name, digest in manifest["files"].items():
        print(f"  {name}  {(args.out / name).stat().st_size:>10,} bytes  sha256 {digest[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
