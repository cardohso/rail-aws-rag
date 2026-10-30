"""Convert eval/live/golden_set.jsonl to goldpass's format (https://github.com/cardohso/goldpass).

Unlike the retrieval gate's golden set (answerable questions only, no model), this one keeps the
unanswerable questions as `expected: refuse`, because the live gate calls the deployed endpoint
and can check refusals. tests/test_live_golden.py checks that the committed golden.jsonl is
exactly this script's output.

    uv run python eval/live/make_golden.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "golden_set.jsonl"
OUT = HERE / "golden.jsonl"


def convert(rows: list[dict]) -> list[dict]:
    items = []
    for r in rows:
        if r["type"] == "unanswerable":
            items.append(
                {
                    "id": r["id"],
                    "question": r["question"],
                    "expected": "refuse",
                    "reference_answer": r["reference_answer"],
                }
            )
            continue
        item = {"id": r["id"], "question": r["question"], "expected": "answer"}
        if r.get("reference_answer"):
            item["reference_answer"] = r["reference_answer"]
        item["gold_passage_ids"] = r["supporting_passages"]
        item["source_doc_ids"] = r["expected_docs"]
        if r["type"] == "wrong_document":
            item["tags"] = ["wrong-document"]
        if r.get("notes"):
            item["notes"] = r["notes"]
        items.append(item)
    return items


def render(items: list[dict]) -> str:
    return "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items)


def main() -> None:
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]
    OUT.write_text(render(convert(rows)), encoding="utf-8")
    print(f"wrote {OUT.relative_to(HERE.parent.parent)}: {len(rows)} items")


if __name__ == "__main__":
    main()
