import base64
import json

import pytest

from rail_aws_rag import prompts
from rail_aws_rag.bedrock import LLMUnavailable
from rail_aws_rag.handler import handler

from fakes import FakeClientError, FakeLLM, make_pipeline


class Context:
    aws_request_id = "req-1"


def event(method: str, path: str, body=None, b64=False) -> dict:
    e = {"rawPath": path, "requestContext": {"http": {"method": method}}}
    if body is not None:
        raw = body if isinstance(body, str) else json.dumps(body)
        e["body"] = base64.b64encode(raw.encode()).decode() if b64 else raw
        e["isBase64Encoded"] = b64
    return e


@pytest.fixture
def pipeline(tmp_path):
    return make_pipeline(tmp_path)


def call(pipeline, *args, **kwargs):
    response = handler(event(*args, **kwargs), Context(), pipeline=pipeline)
    return response["statusCode"], json.loads(response["body"])


def test_health(pipeline):
    status, body = call(pipeline, "GET", "/health")
    assert status == 200
    assert body["status"] == "ok"
    assert body["passages"] == 3
    assert body["generator"] == "fake:llm"
    assert body["search_mode"] == "hybrid"


def test_ask_returns_the_rail_shape_with_the_request_id(pipeline):
    status, body = call(pipeline, "POST", "/ask", {"question": "What is the EMU noise limit?"})
    assert status == 200
    assert body["refused"] is False
    assert body["citations"][0]["passage_id"] == "tsi-noi:Annex §4.2.1#1"
    assert body["trace_id"] == "req-1"


def test_base64_body_is_decoded(pipeline):
    status, _ = call(pipeline, "POST", "/ask", {"question": "EMU noise?"}, b64=True)
    assert status == 200


@pytest.mark.parametrize(
    "body",
    ["not json", {"q": "missing"}, {"question": 42}, {"question": "  a "}, {"question": "x" * 501}],
)
def test_bad_requests_get_400_before_any_model_call(tmp_path, body):
    llm = FakeLLM()
    status, payload = call(make_pipeline(tmp_path, llm=llm), "POST", "/ask", body)
    assert status == 400
    assert "question" in payload["error"]
    assert llm.calls == []


def test_unknown_route_is_404(pipeline):
    assert call(pipeline, "GET", "/ask")[0] == 404
    assert call(pipeline, "DELETE", "/health")[0] == 404


def test_model_unavailable_is_503(tmp_path):
    llm = FakeLLM()
    llm.replies[prompts.GRADE] = LLMUnavailable("ThrottlingException")
    status, body = call(make_pipeline(tmp_path, llm=llm), "POST", "/ask", {"question": "EMU?"})
    assert status == 503
    assert "try again" in body["error"]


def test_unexpected_error_is_500_with_the_trace_id(tmp_path):
    llm = FakeLLM()
    llm.replies[prompts.GRADE] = FakeClientError("AccessDeniedException")
    status, body = call(make_pipeline(tmp_path, llm=llm), "POST", "/ask", {"question": "EMU?"})
    assert status == 500
    assert body["trace_id"] == "req-1"


def test_request_log_is_one_json_line_without_the_question(pipeline, capsys):
    secret = "my private case about Lisbon depot"
    call(pipeline, "POST", "/ask", {"question": secret})
    (line,) = capsys.readouterr().out.strip().splitlines()
    record = json.loads(line)
    assert record["event"] == "ask"
    assert record["question_chars"] == len(secret)
    assert record["llm_calls"] == 2
    assert "Lisbon" not in line
