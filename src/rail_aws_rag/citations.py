"""Map [n] markers in generated answers to passages and format them for the API."""

from __future__ import annotations

import re

from rail_aws_rag.index import SearchHit

MARKER = re.compile(r"\[(\d+)\]")
EURLEX_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"


def renumber(answer: str, context: list[SearchHit]) -> tuple[str, list[SearchHit]]:
    """Keep only markers that point at real passages and renumber them 1..m by first use.

    Returns the rewritten answer and the cited passages, where citations[k-1] is marker [k].
    """
    order: list[int] = []
    for m in MARKER.finditer(answer):
        i = int(m.group(1))
        if 1 <= i <= len(context) and i not in order:
            order.append(i)
    new_number = {old: new for new, old in enumerate(order, start=1)}

    def sub(m: re.Match) -> str:
        i = int(m.group(1))
        return f"[{new_number[i]}]" if i in new_number else ""

    text = re.sub(r"\s+([.,;:])", r"\1", MARKER.sub(sub, answer)).strip()
    return text, [context[i - 1] for i in order]


def format_citations(cited: list[SearchHit], celex_by_doc: dict[str, str]) -> list[dict]:
    """Citation objects in the same shape as the rail-regulation-rag API."""
    return [
        {
            "n": n,
            "passage_id": h.passage.id,
            "doc_id": h.passage.doc_id,
            "document": h.passage.doc_short,
            "section": h.passage.section,
            "heading": h.passage.heading,
            "passage": h.passage.text,
            "url": EURLEX_URL.format(celex=celex_by_doc.get(h.passage.doc_id, "")),
            "score": round(h.score, 4),
        }
        for n, h in enumerate(cited, start=1)
    ]
