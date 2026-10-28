"""Build the pipeline from the Lambda environment: index from S3, models from the image.

Environment variables (set by Terraform):
    INDEX_BUCKET, INDEX_PREFIX   where build_index's files were uploaded
    MODEL_ID                     Bedrock model or inference profile, e.g. eu.amazon.nova-lite-v1:0
    GUARDRAIL_ID, GUARDRAIL_VERSION   optional; without them no guardrail check runs
    TOP_K, MIN_SCORE, SEARCH_MODE     optional retrieval settings
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rail_aws_rag.index import FILES, Index
from rail_aws_rag.pipeline import Pipeline, PipelineConfig

DEFAULT_INDEX_DIR = Path("/tmp/index")  # the only writable path in Lambda


def download_index(s3: Any, bucket: str, prefix: str, dest: Path) -> Path:
    """Copy the index files from S3. Index.load then checks every file against manifest.json."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", *FILES):
        s3.download_file(bucket, f"{prefix.strip('/')}/{name}", str(dest / name))
    return dest


def build_quota(env: Mapping[str, str], *, dynamodb: Any = None):
    """The daily cap, or None when TABLE_NAME is not set (local runs, tests)."""
    if not env.get("TABLE_NAME"):
        return None
    from rail_aws_rag.quota import DailyQuota

    if dynamodb is None:
        import boto3

        dynamodb = boto3.client("dynamodb")
    return DailyQuota(dynamodb, env["TABLE_NAME"], int(env.get("DAILY_LIMIT", "50")))


def config_from_env(env: Mapping[str, str]) -> PipelineConfig:
    return PipelineConfig(
        k=int(env.get("TOP_K", "8")),
        min_score=float(env.get("MIN_SCORE", "0.60")),
        hybrid=env.get("SEARCH_MODE", "hybrid") == "hybrid",
    )


def build_pipeline(
    env: Mapping[str, str],
    *,
    s3: Any = None,
    bedrock: Any = None,
    dense: Any = None,
    sparse: Any = None,
    index_dir: Path = DEFAULT_INDEX_DIR,
) -> Pipeline:
    """Every client and encoder can be injected; the defaults are the real AWS and ONNX ones."""
    from rail_aws_rag.bedrock import BedrockGuardrail, BedrockLLM, make_clients

    if s3 is None:
        import boto3

        s3 = boto3.client("s3")
    if bedrock is None:
        bedrock = make_clients(env.get("AWS_REGION", "eu-west-1"))
    if dense is None or sparse is None:
        from rail_aws_rag.embeddings import BM25Encoder, LocalEmbedder

        dense, sparse = dense or LocalEmbedder(), sparse or BM25Encoder()

    index = Index.load(download_index(s3, env["INDEX_BUCKET"], env["INDEX_PREFIX"], index_dir))
    guardrail = None
    if env.get("GUARDRAIL_ID"):
        guardrail = BedrockGuardrail(
            bedrock, env["GUARDRAIL_ID"], env.get("GUARDRAIL_VERSION", "1")
        )
    return Pipeline(
        BedrockLLM(bedrock, env["MODEL_ID"]),
        index,
        dense,
        sparse,
        guardrail=guardrail,
        cfg=config_from_env(env),
    )
