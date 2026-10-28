from rail_aws_rag import corpus
from rail_aws_rag.corpus import Passage, chunk_section


def record(text: str) -> dict:
    return {"doc_id": "tsi-x", "section": "Article 1", "heading": "Scope", "text": text}


def test_short_section_is_one_passage_with_a_citation_key():
    (p,) = chunk_section(record("One short paragraph."), doc_short="X TSI")
    assert p.id == "tsi-x:Article 1#1"
    assert p.citation == "X TSI, Article 1"
    assert p.embed_text == "X TSI, Scope\nOne short paragraph."


def test_paragraphs_are_packed_up_to_the_word_limit():
    paragraphs = ["word " * 100, "word " * 100, "word " * 100]
    chunks = chunk_section(record("\n".join(paragraphs)), "X", max_words=250)
    assert [len(c.text.split()) for c in chunks] == [200, 100]
    assert [c.id for c in chunks] == ["tsi-x:Article 1#1", "tsi-x:Article 1#2"]


def test_long_paragraph_is_split_into_overlapping_windows():
    chunks = chunk_section(record(" ".join(str(i) for i in range(600))), "X", max_words=250)
    assert all(len(c.text.split()) <= 250 for c in chunks)
    first_end = chunks[0].text.split()[-40:]
    assert chunks[1].text.split()[:40] == first_end  # overlap = 40 words


def test_passage_round_trips_through_a_dict():
    p = Passage("a:b#1", "a", "A", "b", "h", "t")
    assert Passage.from_dict(p.to_dict()) == p


def test_committed_corpus_loads_and_every_passage_id_is_unique():
    documents = corpus.load_manifest()
    passages = corpus.load_passages(documents)
    assert len(documents) == 7
    assert len(passages) == 1589  # the corpus the rail assistant was evaluated on
    assert len({p.id for p in passages}) == len(passages)
    assert {p.doc_id for p in passages} == {d.id for d in documents}
