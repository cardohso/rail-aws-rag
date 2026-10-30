"""Does the numpy index return what the Qdrant index of rail-regulation-rag returned?

Two references, each the raw top-8 hits for the 20 golden questions with the rewritten query the
rail assistant used:
- rail_hits.json: saved from the rail assistant's last live eval run, which searched in dense mode;
- rail_hybrid_hits.json: what the rail repo's Qdrant index returns in hybrid mode (see
  make_hybrid_fixture.py).

This script runs the same queries through the new index and compares the ranked passage ids.

    uv run python eval/parity/check.py --index build/index
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
REFERENCES = {"dense": "rail_hits.json", "hybrid": "rail_hybrid_hits.json"}


def keyword_text(question: str, query: str) -> str:
    """BM25 input of the rail pipeline: the rewritten query plus the user's own words."""
    return query if query == question else f"{query} {question}"


def compare(index: Index, dense, sparse, items: list[dict], mode: str, k: int = K) -> list[dict]:
    rows = []
    for item in items:
        question, query = item["question"], item["query"]
        terms = sparse.embed_query(keyword_text(question, query)) if mode == "hybrid" else None
        hits = index.search(dense.embed_query(query), k=k, sparse=terms)
        got = [h.passage.id for h in hits]
        want = [h["passage_id"] for h in item["hits"]]
        gap = max(
            (abs(h.score - w["score"]) for h, w in zip(hits, item["hits"], strict=False)),
            default=0.0,
        )
        rows.append(
            {
                "id": item["id"],
                "same_order": got == want,
                "same_set": set(got) == set(want),
                "overlap": len(set(got) & set(want)),
                "max_score_gap": round(gap, 4),
                "got": got,
                "want": want,
            }
        )
    return rows


def summarise(rows: list[dict]) -> dict:
    return {
        "items": len(rows),
        "same_order": sum(r["same_order"] for r in rows),
        "same_set": sum(r["same_set"] for r in rows),
        "mean_overlap_at_8": round(sum(r["overlap"] for r in rows) / len(rows), 3),
        "max_score_gap": max(r["max_score_gap"] for r in rows),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--index", type=Path, default=REPO_ROOT / "build" / "index")
    ap.add_argument("--out", type=Path, default=HERE / "results.json")
    args = ap.parse_args(argv)

    index, dense, sparse = Index.load(args.index), LocalEmbedder(), BM25Encoder()
    report = {}
    for mode, name in REFERENCES.items():
        items = json.loads((HERE / name).read_text(encoding="utf-8"))["items"]
        rows = compare(index, dense, sparse, items, mode)
        report[mode] = {"reference": name, "summary": summarise(rows), "items": rows}
        print(f"{mode}: {json.dumps(report[mode]['summary'])}")
        for r in rows:
            if not r["same_order"]:
                print(f"  {r['id']}: overlap {r['overlap']}/{K}, score gap {r['max_score_gap']}")

    args.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
