"""Write rail_hybrid_hits.json: what the rail assistant's Qdrant index returns in hybrid mode.

The hits saved in rail_hits.json come from a dense-mode eval run, so hybrid parity needs its own
reference. Run this from a rail-regulation-rag checkout that has a built local index:

    cd ../rail-regulation-rag
    uv run python ../rail-aws-rag/eval/parity/make_hybrid_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

from rail_rag.config import get_settings
from rail_rag.embeddings import LocalEmbedder
from rail_rag.graph import keyword_text
from rail_rag.vectorstore import make_store

HERE = Path(__file__).parent
K = 8


def main() -> int:
    source = json.loads((HERE / "rail_hits.json").read_text(encoding="utf-8"))["items"]
    settings = get_settings().model_copy(update={"vector_store": "qdrant"})
    embedder, store = LocalEmbedder(settings.embedding_model), make_store(settings)
    items = []
    for it in source:
        text = keyword_text({"question": it["question"], "query": it["query"]})
        hits = store.search(embedder.embed_query(it["query"]), k=K, text=text)
        items.append(
            {
                "id": it["id"],
                "question": it["question"],
                "query": it["query"],
                "hits": [{"passage_id": h.passage.id, "score": round(h.score, 4)} for h in hits],
            }
        )
    out = {
        "source": "rail-regulation-rag local Qdrant index, hybrid, k=8, bge-small-en-v1.5",
        "items": items,
    }
    (HERE / "rail_hybrid_hits.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"{len(items)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
