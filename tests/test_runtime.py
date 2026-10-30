import pytest

from rail_aws_rag.runtime import build_pipeline, config_from_env, download_index

from fakes import FakeBedrockClient, FakeDense, FakeS3, FakeSparse, build_index

ENV = {
    "INDEX_BUCKET": "data-bucket",
    "INDEX_PREFIX": "index/abc123/",
    "MODEL_ID": "eu.amazon.nova-lite-v1:0",
    "AWS_REGION": "eu-west-1",
}


@pytest.fixture
def s3(tmp_path):
    build_index(tmp_path / "bucket" / "index" / "abc123")
    return FakeS3(tmp_path / "bucket")


def build(tmp_path, s3, env):
    return build_pipeline(
        env,
        s3=s3,
        bedrock=FakeBedrockClient(),
        dense=FakeDense(),
        sparse=FakeSparse(),
        index_dir=tmp_path / "tmp-index",
    )


def test_download_index_fetches_the_manifest_and_every_file(tmp_path, s3):
    download_index(s3, "data-bucket", "index/abc123/", tmp_path / "out")
    assert s3.keys == [
        "data-bucket/index/abc123/manifest.json",
        "data-bucket/index/abc123/passages.json",
        "data-bucket/index/abc123/vectors.npy",
        "data-bucket/index/abc123/bm25.npz",
    ]


def test_build_pipeline_from_env_without_a_guardrail(tmp_path, s3):
    pipeline = build(tmp_path, s3, ENV)
    assert len(pipeline.index) == 3
    assert pipeline.llm.name == "bedrock:eu.amazon.nova-lite-v1:0"
    assert pipeline.guardrail is None


def test_build_pipeline_with_a_guardrail(tmp_path, s3):
    pipeline = build(tmp_path, s3, ENV | {"GUARDRAIL_ID": "gr-1", "GUARDRAIL_VERSION": "3"})
    assert (pipeline.guardrail.guardrail_id, pipeline.guardrail.version) == ("gr-1", "3")


def test_a_corrupted_file_in_s3_stops_the_cold_start(tmp_path, s3):
    vectors = tmp_path / "bucket" / "index" / "abc123" / "vectors.npy"
    vectors.write_bytes(vectors.read_bytes()[:-4] + b"\x00\x00\x00\x00")
    with pytest.raises(ValueError, match="vectors.npy"):
        build(tmp_path, s3, ENV)


def test_config_from_env():
    cfg = config_from_env({"TOP_K": "5", "MIN_SCORE": "0.7", "SEARCH_MODE": "dense"})
    assert (cfg.k, cfg.min_score, cfg.hybrid) == (5, 0.7, False)
    assert config_from_env({}).k == 8
    assert config_from_env({}).rewrite is False
    assert config_from_env({"REWRITE": "1"}).rewrite is True
