"""Retrieval-only records for the goldpass gate: no LLM, no AWS, deterministic.

For each golden question this runs the index's own search (same embedder, same k, hybrid) with
the rewritten query saved in queries.json, so a change in the score can only come from chunking,
the index, the embedding model, hybrid search or k. `contexts` is the raw top-k hits, so goldpass
reports recall@k, precision@k and MRR as retrieval metrics.

    uv run python eval/goldpass/retrieval_records.py --index build/index
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rail_aws_rag.corpus import REPO_ROOT
from rail_aws_rag.embeddings import BM25Encoder, LocalEmbedder
from rail_aws_rag.index import Index

HERE = Path(__file__).parent
K = 8


def keyword_text(question: str, query: str) -> str:
    return query if query == question else f"{query} {question}"


def records_for(items: list[dict], queries: dict[str, str], index, dense, sparse, k: int = K):
    """goldpass records, one per golden item, in golden-set order."""
    records = []
    for item in items:
        query = queries[item["id"]]
        terms = sparse.embed_query(keyword_text(item["question"], query))
        hits = index.search(dense.embed_query(query), k=k, sparse=terms)
        records.append(
            {
                "id": item["id"],
                "answer": "",  # no generation here
                "contexts": [
                    {"id": h.passage.id, "doc_id": h.passage.doc_id, "score": round(h.score, 4)}
                    for h in hits
                ],
            }
        )
    return records


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--index", type=Path, default=REPO_ROOT / "build" / "index")
    ap.add_argument("--golden", type=Path, default=HERE / "golden.jsonl")
    ap.add_argument("--queries", type=Path, default=HERE / "queries.json")
    ap.add_argument("--out", type=Path, default=HERE / "records.json")
    args = ap.parse_args(argv)

    items = [
        json.loads(line) for line in args.golden.read_text(encoding="utf-8").splitlines() if line
    ]
    queries = json.loads(args.queries.read_text(encoding="utf-8"))
    missing = [i["id"] for i in items if i["id"] not in queries]
    if missing:
        raise SystemExit(f"no saved rewritten query for {missing}")

    index = Index.load(args.index)
    records = records_for(items, queries, index, LocalEmbedder(), BM25Encoder(), K)
    payload = {
        "system": f"rail-aws-rag retrieval (hybrid, k={K}, {index.manifest['dense_model']})",
        "records": records,
    }
    args.out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(records)} records -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
