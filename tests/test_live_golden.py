"""The live gate's golden set must match the corpus it is scored against."""

import importlib.util
import json
from pathlib import Path

from rail_aws_rag import corpus

LIVE = Path(__file__).resolve().parents[1] / "eval" / "live"


def load_converter():
    spec = importlib.util.spec_from_file_location("make_golden", LIVE / "make_golden.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def golden() -> list[dict]:
    return [json.loads(line) for line in (LIVE / "golden.jsonl").read_text("utf-8").splitlines()]


def test_committed_golden_is_the_converters_output():
    make = load_converter()
    rows = [
        json.loads(line) for line in (LIVE / "golden_set.jsonl").read_text("utf-8").splitlines()
    ]
    assert (LIVE / "golden.jsonl").read_text("utf-8") == make.render(make.convert(rows))


def test_twenty_questions_sixteen_to_answer_and_four_to_refuse():
    items = golden()
    assert len(items) == 20
    assert len({i["id"] for i in items}) == 20
    assert sum(i["expected"] == "answer" for i in items) == 16
    assert sum(i["expected"] == "refuse" for i in items) == 4
    assert sum("wrong-document" in i.get("tags", []) for i in items) == 3


def test_every_gold_passage_exists_in_the_corpus_with_the_right_document():
    passages = {p.id: p for p in corpus.load_passages()}
    for item in golden():
        if item["expected"] == "refuse":
            assert "gold_passage_ids" not in item and "source_doc_ids" not in item
            continue
        assert item["gold_passage_ids"], item["id"]
        for passage_id in item["gold_passage_ids"]:
            assert passage_id in passages, f"{item['id']}: {passage_id} is not in the corpus"
            assert passages[passage_id].doc_id in item["source_doc_ids"], item["id"]
