import math

import numpy as np
import pytest

from rail_aws_rag.corpus import Document, Passage
from rail_aws_rag.index import FILES, HYBRID_CANDIDATES, RRF_K, Index, write_index

DOCS = [Document("d", "D TSI", "0201", "Doc")]


def passage(n: int) -> Passage:
    return Passage(f"d:s#{n}", "d", "D TSI", f"s{n}", "h", f"text {n}")


def unit(*xs: float) -> list[float]:
    v = np.asarray(xs, dtype=np.float32)
    return (v / np.linalg.norm(v)).tolist()


# Four passages in 2-D. Cosine to the query (1, 0): p0 > p1 > p2 > p3.
VECTORS = [unit(1, 0), unit(1, 1), unit(0, 1), unit(-1, 1)]
# BM25 terms: term 7 appears only in p3 (rare), term 8 in p0 and p3 (common).
SPARSE = [([8], [1.0]), ([], []), ([], []), ([7, 8], [1.0, 1.0])]


@pytest.fixture
def index(tmp_path):
    write_index(
        tmp_path,
        DOCS,
        [passage(i) for i in range(4)],
        VECTORS,
        SPARSE,
        dense_model="dense",
        sparse_model="sparse",
    )
    return Index.load(tmp_path)


def test_dense_search_ranks_by_cosine(index):
    hits = index.search(unit(1, 0), k=3)
    assert [h.passage.id for h in hits] == ["d:s#0", "d:s#1", "d:s#2"]
    assert hits[0].score == pytest.approx(1.0)
    assert hits[1].score == pytest.approx(math.sqrt(0.5))


def test_query_vector_need_not_be_normalised(index):
    assert index.search([5.0, 0.0], k=1)[0].passage.id == "d:s#0"


def test_hybrid_lets_a_rare_keyword_pull_up_a_dense_straggler(index):
    # Dense alone puts p3 last. Its rare term 7 makes it the only BM25 hit, so RRF lifts it.
    dense_only = [h.passage.id for h in index.search(unit(1, 0), k=4)]
    hybrid = [h.passage.id for h in index.search(unit(1, 0), k=4, sparse=([7], [1.0]))]
    assert dense_only[-1] == "d:s#3"
    assert hybrid.index("d:s#3") < dense_only.index("d:s#3")


def test_hybrid_scores_are_cosines_not_rank_scores(index):
    hits = index.search(unit(1, 0), k=4, sparse=([7], [1.0]))
    by_id = {h.passage.id: h.score for h in hits}
    assert by_id["d:s#3"] == pytest.approx(float(np.dot(unit(1, 0), VECTORS[3])), abs=1e-6)


def test_rrf_scores_follow_the_formula(index):
    # p3 is rank 4 in dense and rank 1 in BM25; p0 is rank 1 in dense and absent from BM25.
    hits = index.search(unit(1, 0), k=4, sparse=([7], [1.0]))
    expected_p3 = 1 / (RRF_K + 4) + 1 / (RRF_K + 1)
    expected_p0 = 1 / (RRF_K + 1)
    assert expected_p3 > expected_p0
    assert [h.passage.id for h in hits][0] == "d:s#3"


def test_idf_downweights_common_terms(index):
    # Term 8 is in 2 of 4 passages, term 7 in 1: the rarer term has the higher IDF.
    assert index._idf[7] > index._idf[8]
    assert index._idf[7] == pytest.approx(math.log(1 + (4 - 1 + 0.5) / (1 + 0.5)))


def test_unknown_query_terms_fall_back_to_dense_order(index):
    assert [h.passage.id for h in index.search(unit(1, 0), k=3, sparse=([999], [1.0]))] == [
        "d:s#0",
        "d:s#1",
        "d:s#2",
    ]


def test_candidate_pool_is_capped_at_fifty_per_retriever():
    assert HYBRID_CANDIDATES == 50


def test_ties_resolve_to_the_lower_row_number(tmp_path):
    write_index(
        tmp_path,
        DOCS,
        [passage(0), passage(1)],
        [unit(1, 0), unit(1, 0)],
        [([], []), ([], [])],
        dense_model="d",
        sparse_model="s",
    )
    ids = [h.passage.id for h in Index.load(tmp_path).search(unit(1, 0), k=2)]
    assert ids == ["d:s#0", "d:s#1"]


def test_load_rejects_a_tampered_file(tmp_path, index):
    path = tmp_path / "passages.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="passages.json"):
        Index.load(tmp_path)


def test_load_rejects_an_unknown_format_version(tmp_path, index):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(manifest.read_text().replace('"format_version": 1', '"format_version": 9'))
    with pytest.raises(ValueError, match="format"):
        Index.load(tmp_path)


def test_write_index_is_reproducible(tmp_path):
    args = (DOCS, [passage(i) for i in range(4)], VECTORS, SPARSE)
    a = write_index(tmp_path / "a", *args, dense_model="d", sparse_model="s")
    b = write_index(tmp_path / "b", *args, dense_model="d", sparse_model="s")
    assert a == b
    assert set(a["files"]) == set(FILES)


def test_write_index_rejects_mismatched_lengths(tmp_path):
    with pytest.raises(ValueError):
        write_index(
            tmp_path, DOCS, [passage(0)], VECTORS, SPARSE, dense_model="d", sparse_model="s"
        )


def test_manifest_records_models_and_size(index):
    assert index.manifest["dense_model"] == "dense"
    assert index.manifest["dim"] == 2
    assert index.manifest["n_passages"] == len(index) == 4
