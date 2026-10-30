"""A daily request cap, kept in DynamoDB because Lambda instances share no memory.

API Gateway HTTP APIs can throttle but have no daily quota (usage plans exist only for REST APIs),
and this account's Lambda concurrency limit is too low to reserve any, so the cap lives here: one
item per UTC day, incremented atomically only while it is below the limit.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from rail_aws_rag.bedrock import TRANSIENT_ERRORS, LLMUnavailable, error_code

KEEP_SECONDS = 3 * 86_400  # DynamoDB TTL removes old days; the table never grows


class DailyQuota:
    def __init__(
        self,
        client: Any,
        table: str,
        limit: int,
        clock: Callable[[], float] = time.time,
    ):
        self.client, self.table, self.limit, self.clock = client, table, limit, clock
        self._exhausted_day: str | None = None

    def take(self) -> bool:
        """Count one request. False once today's limit is used up.

        After the first refusal of the day, this container refuses from memory: under a flood of
        requests, rejections then cost no DynamoDB writes, only the throttled Lambda calls.
        """
        now = self.clock()
        day = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
        if day == self._exhausted_day:
            return False
        try:
            self.client.update_item(
                TableName=self.table,
                Key={"day": {"S": day}},
                UpdateExpression="ADD #n :one SET expires_at = :ttl",
                ConditionExpression="attribute_not_exists(#n) OR #n < :limit",
                ExpressionAttributeNames={"#n": "requests"},
                ExpressionAttributeValues={
                    ":one": {"N": "1"},
                    ":limit": {"N": str(self.limit)},
                    ":ttl": {"N": str(int(now) + KEEP_SECONDS)},
                },
            )
        except Exception as exc:
            code = error_code(exc)
            if code == "ConditionalCheckFailedException":
                self._exhausted_day = day
                return False
            if code in TRANSIENT_ERRORS | {"ProvisionedThroughputExceededException"}:
                # Fail closed: if the counter cannot be read, the cap cannot be enforced.
                raise LLMUnavailable(f"quota table: {code}") from exc
            raise
        return True
