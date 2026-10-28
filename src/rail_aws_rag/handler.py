"""AWS Lambda entry point behind an API Gateway HTTP API (payload format 2.0).

    GET  /health  index size, model and settings; no Bedrock call
    POST /ask     {"question": "..."} -> {answer, refused, refusal_reason, citations, trace_id}

The pipeline is built once per container (cold start) and reused by warm invocations.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

from rail_aws_rag import __version__
from rail_aws_rag.bedrock import LLMUnavailable

MIN_QUESTION, MAX_QUESTION = 3, 500

logger = logging.getLogger("rail_aws_rag")

_pipeline = None
_quota = None
_quota_ready = False


def get_quota():
    global _quota, _quota_ready
    if not _quota_ready:
        from rail_aws_rag.runtime import build_quota

        _quota, _quota_ready = build_quota(os.environ), True
    return _quota


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from rail_aws_rag.runtime import build_pipeline

        _pipeline = build_pipeline(os.environ)
    return _pipeline


def _json(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _log(event: str, **fields: Any) -> None:
    # One JSON object per line: CloudWatch Logs Insights reads its fields without a parse step.
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _question(event: dict) -> str | None:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    question = data.get("question") if isinstance(data, dict) else None
    if not isinstance(question, str):
        return None
    question = question.strip()
    return question if MIN_QUESTION <= len(question) <= MAX_QUESTION else None


def health(pipeline) -> dict:
    cfg = pipeline.cfg
    return {
        "status": "ok",
        "version": __version__,
        "passages": len(pipeline.index),
        "vectors_sha256": pipeline.index.manifest.get("files", {}).get("vectors.npy", "")[:12],
        "generator": pipeline.llm.name,
        "guardrail": pipeline.guardrail is not None,
        "search_mode": "hybrid" if cfg.hybrid else "dense",
        "top_k": cfg.k,
        "min_score": cfg.min_score,
    }


def ask(get_pipeline_fn, quota, event: dict, request_id: str) -> dict:
    question = _question(event)
    if question is None:
        return _json(
            400,
            {
                "error": f'Send JSON {{"question": "..."}} with {MIN_QUESTION} to '
                f"{MAX_QUESTION} characters."
            },
        )
    try:
        # The cap is checked before the pipeline is built, so a rejected request on a cold
        # container costs one DynamoDB write, not an index download.
        if quota is not None and not quota.take():
            _log("ask_over_quota", trace_id=request_id)
            return _json(429, {"error": "The daily question limit is used up; try again tomorrow."})
        result = get_pipeline_fn().ask(question, trace_id=request_id)
    except LLMUnavailable:
        _log("ask_unavailable", trace_id=request_id)
        return _json(503, {"error": "The language model is busy; try again shortly."})
    _log("ask", question_chars=len(question), **result.log_record())
    return _json(200, result.response())


def handler(event: dict, context: Any = None, pipeline=None, quota=None) -> dict:
    http = event.get("requestContext", {}).get("http", {})
    method, path = http.get("method", ""), event.get("rawPath", "")
    request_id = getattr(context, "aws_request_id", "") or "local"
    try:
        if (method, path) == ("GET", "/health"):
            return _json(200, health(pipeline or get_pipeline()))
        if (method, path) == ("POST", "/ask"):
            return ask(
                (lambda: pipeline) if pipeline else get_pipeline,
                quota if quota is not None else get_quota(),
                event,
                request_id,
            )
        return _json(404, {"error": "Not found. Use GET /health or POST /ask."})
    except Exception:
        logger.exception("unhandled error, trace_id=%s", request_id)
        return _json(500, {"error": "Internal error.", "trace_id": request_id})
