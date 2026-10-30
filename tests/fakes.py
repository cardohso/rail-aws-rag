"""Test doubles for Bedrock, Guardrails, S3 and the encoders. No network, no AWS, no ONNX."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from rail_aws_rag import prompts
from rail_aws_rag.bedrock import Completion, GuardrailResult
from rail_aws_rag.corpus import Document, Passage
from rail_aws_rag.index import Index, write_index
from rail_aws_rag.pipeline import Pipeline, PipelineConfig

DOCS = [Document("tsi-noi", "NOI TSI", "02014R1304-20230928", "Noise TSI")]


def unit(*xs: float) -> list[float]:
    v = np.asarray(xs, dtype=np.float32)
    return (v / np.linalg.norm(v)).tolist()


# Cosine with the query (1, 0): p1 = 1.0, p2 = 0.8, p3 = 0.0
PASSAGES = [
    Passage("tsi-noi:Annex §4.2.1#1", "tsi-noi", "NOI TSI", "Annex §4.2.1", "Stationary", "65 dB"),
    Passage("tsi-noi:Annex §4.2.2#1", "tsi-noi", "NOI TSI", "Annex §4.2.2", "Starting", "82 dB"),
    Passage("tsi-noi:Annex §4.2.3#1", "tsi-noi", "NOI TSI", "Annex §4.2.3", "Pass-by", "83 dB"),
]
VECTORS = [unit(1, 0), unit(0.8, 0.6), unit(0, 1)]


def build_index(directory: Path) -> Path:
    write_index(
        directory,
        DOCS,
        PASSAGES,
        VECTORS,
        [([], []), ([], []), ([], [])],
        dense_model="fake-dense",
        sparse_model="fake-sparse",
    )
    return directory


class FakeDense:
    dim = 2

    def __init__(self, vector=None):
        self.vector = vector or unit(1, 0)
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self.vector


class FakeSparse:
    def embed_query(self, text: str) -> tuple[list[int], list[float]]:
        return [], []


class FakeLLM:
    """Replies scripted per prompt; records every call."""

    name = "fake:llm"

    def __init__(self, rewrite="noise limit EMU", grade=None, generate=None):
        self.replies = {
            prompts.REWRITE: rewrite,
            prompts.GRADE: json.dumps(grade if grade is not None else {"relevant": [1]}),
            prompts.GENERATE: json.dumps(
                generate
                if generate is not None
                else {"answer": "The limit is 65 dB [1].", "insufficient": False}
            ),
        }
        self.calls: list[dict] = []

    def complete(self, system, user, *, max_tokens, schema=None):
        self.calls.append(
            {"system": system, "user": user, "max_tokens": max_tokens, "schema": schema}
        )
        reply = self.replies[system]
        if isinstance(reply, Exception):
            raise reply
        return Completion(reply, input_tokens=100, output_tokens=10, stop_reason="end_turn")


class FakeGuardrail:
    def __init__(self, input_result=None, output_result=None):
        self.results = {"INPUT": input_result, "OUTPUT": output_result}
        self.calls: list[tuple[str, str]] = []

    def check(self, text, source):
        self.calls.append((source, text))
        return self.results[source] or GuardrailResult(False, False, text, [], 1)


def make_pipeline(tmp_path: Path, llm=None, guardrail=None, dense=None, **cfg) -> Pipeline:
    return Pipeline(
        llm or FakeLLM(),
        Index.load(build_index(tmp_path / "index")),
        dense or FakeDense(),
        FakeSparse(),
        guardrail=guardrail,
        cfg=PipelineConfig(**cfg),
    )


class FakeClientError(Exception):
    """Shaped like botocore.exceptions.ClientError: the code is in .response."""

    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code, "Message": code}}


class FakeBedrockClient:
    def __init__(self, converse=None, guardrail=None):
        self.converse_reply = converse
        self.guardrail_reply = guardrail
        self.requests: list[dict] = []

    def converse(self, **request):
        self.requests.append(request)
        if isinstance(self.converse_reply, Exception):
            raise self.converse_reply
        return self.converse_reply

    def apply_guardrail(self, **request):
        self.requests.append(request)
        if isinstance(self.guardrail_reply, Exception):
            raise self.guardrail_reply
        return self.guardrail_reply


class FakeS3:
    """download_file from a local folder that stands in for s3://bucket/."""

    def __init__(self, root: Path):
        self.root = root
        self.keys: list[str] = []

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        self.keys.append(f"{bucket}/{key}")
        shutil.copyfile(self.root / key, filename)


def converse_response(*, text=None, tool_input=None, stop="end_turn", tokens=(50, 5)) -> dict:
    content = []
    if text is not None:
        content.append({"text": text})
    if tool_input is not None:
        content.append({"toolUse": {"toolUseId": "t1", "name": "reply", "input": tool_input}})
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
        "usage": {"inputTokens": tokens[0], "outputTokens": tokens[1], "totalTokens": sum(tokens)},
        "metrics": {"latencyMs": 100},
    }


class FakeDynamoDB:
    """update_item with the conditional ADD that DailyQuota uses: one counter per day key."""

    def __init__(self, error: Exception | None = None):
        self.counts: dict[str, int] = {}
        self.error = error
        self.requests: list[dict] = []

    def update_item(self, **request):
        self.requests.append(request)
        if self.error:
            raise self.error
        day = request["Key"]["day"]["S"]
        limit = int(request["ExpressionAttributeValues"][":limit"]["N"])
        if self.counts.get(day, 0) >= limit:
            raise FakeClientError("ConditionalCheckFailedException")
        self.counts[day] = self.counts.get(day, 0) + 1
