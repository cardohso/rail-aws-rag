from datetime import UTC, datetime

import pytest

from rail_aws_rag.bedrock import LLMUnavailable
from rail_aws_rag.handler import handler
from rail_aws_rag.quota import KEEP_SECONDS, DailyQuota
from rail_aws_rag.runtime import build_quota

from fakes import FakeClientError, FakeDynamoDB, FakeLLM, make_pipeline

NOON = datetime(2026, 10, 29, 12, 0, tzinfo=UTC).timestamp()


def test_requests_are_allowed_up_to_the_limit_then_refused():
    quota = DailyQuota(FakeDynamoDB(), "t", limit=2, clock=lambda: NOON)
    assert [quota.take() for _ in range(3)] == [True, True, False]


def test_each_utc_day_has_its_own_counter():
    db, now = FakeDynamoDB(), [NOON]
    quota = DailyQuota(db, "t", limit=1, clock=lambda: now[0])
    assert quota.take() and not quota.take()
    now[0] += 86_400
    assert quota.take()
    assert set(db.counts) == {"2026-10-29", "2026-10-30"}


def test_after_the_first_refusal_the_container_refuses_without_a_write():
    db = FakeDynamoDB()
    quota = DailyQuota(db, "t", limit=1, clock=lambda: NOON)
    assert [quota.take() for _ in range(5)] == [True, False, False, False, False]
    assert len(db.requests) == 2  # one success, one refusal; the rest come from memory


def test_the_memory_resets_on_the_next_utc_day():
    now = [NOON]
    quota = DailyQuota(FakeDynamoDB(), "t", limit=1, clock=lambda: now[0])
    quota.take(), quota.take()
    now[0] += 86_400
    assert quota.take()


def test_the_request_is_one_atomic_conditional_add_with_a_ttl():
    db = FakeDynamoDB()
    DailyQuota(db, "quota-table", limit=50, clock=lambda: NOON).take()
    (request,) = db.requests
    assert request["TableName"] == "quota-table"
    assert request["UpdateExpression"] == "ADD #n :one SET expires_at = :ttl"
    assert "attribute_not_exists" in request["ConditionExpression"]
    assert request["ExpressionAttributeValues"][":ttl"]["N"] == str(int(NOON) + KEEP_SECONDS)


def test_a_throttled_table_fails_closed():
    quota = DailyQuota(FakeDynamoDB(FakeClientError("ThrottlingException")), "t", 5)
    with pytest.raises(LLMUnavailable):
        quota.take()


def test_other_errors_are_not_hidden():
    quota = DailyQuota(FakeDynamoDB(FakeClientError("AccessDeniedException")), "t", 5)
    with pytest.raises(FakeClientError):
        quota.take()


def test_build_quota_reads_the_environment():
    assert build_quota({}) is None
    quota = build_quota({"TABLE_NAME": "t", "DAILY_LIMIT": "7"}, dynamodb=FakeDynamoDB())
    assert (quota.table, quota.limit) == ("t", 7)


def ask_event():
    import json

    return {
        "rawPath": "/ask",
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps({"question": "What is the EMU noise limit?"}),
    }


def test_handler_returns_429_over_the_limit_without_calling_the_model(tmp_path):
    llm = FakeLLM()
    pipeline = make_pipeline(tmp_path, llm=llm)
    quota = DailyQuota(FakeDynamoDB(), "t", limit=1)
    assert handler(ask_event(), None, pipeline=pipeline, quota=quota)["statusCode"] == 200
    calls_after_first = len(llm.calls)

    response = handler(ask_event(), None, pipeline=pipeline, quota=quota)
    assert response["statusCode"] == 429
    assert "daily" in response["body"]
    assert len(llm.calls) == calls_after_first


def test_over_quota_request_does_not_build_the_pipeline(monkeypatch):
    def boom():
        raise AssertionError("pipeline must not be built for a rejected request")

    monkeypatch.setattr("rail_aws_rag.handler.get_pipeline", boom)
    quota = DailyQuota(FakeDynamoDB(), "t", limit=0)
    assert handler(ask_event(), None, quota=quota)["statusCode"] == 429


def test_quota_table_outage_is_503(tmp_path):
    quota = DailyQuota(FakeDynamoDB(FakeClientError("ServiceUnavailableException")), "t", 5)
    response = handler(ask_event(), None, pipeline=make_pipeline(tmp_path), quota=quota)
    assert response["statusCode"] == 503


def test_health_does_not_count_against_the_limit(tmp_path):
    db = FakeDynamoDB()
    event = {"rawPath": "/health", "requestContext": {"http": {"method": "GET"}}}
    handler(event, None, pipeline=make_pipeline(tmp_path), quota=DailyQuota(db, "t", 1))
    assert db.requests == []
