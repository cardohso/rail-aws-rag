"""Amazon Bedrock clients: the Converse call for generation and ApplyGuardrail for safety checks.

Both take an injected boto3 client so tests can pass a fake; boto3 is imported only by the
factory functions, which the Lambda runtime provides.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

# Errors worth a 503 ("try again shortly") rather than a 500. botocore already retried them.
TRANSIENT_ERRORS = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "ModelNotReadyException",
    "ModelTimeoutException",
    "InternalServerException",
}
REPLY_TOOL = "reply"


class LLMUnavailable(RuntimeError):
    """Bedrock kept failing with a transient error after botocore's retries."""


class InvalidModelOutput(ValueError):
    """The model's reply could not be used: no JSON, wrong shape, or cut off by max_tokens."""


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""


class LLM(Protocol):
    name: str

    def complete(
        self, system: str, user: str, *, max_tokens: int, schema: dict | None = None
    ) -> Completion:
        """Return the model's text, or a JSON string matching ``schema`` when one is given."""


def error_code(exc: Exception) -> str:
    """The AWS error code of a botocore ClientError, without importing botocore."""
    response = getattr(exc, "response", None) or {}
    return str(response.get("Error", {}).get("Code", ""))


def parse_json(text: str) -> dict:
    """Parse a JSON object from a model reply, tolerating ```json fences and surrounding prose."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise InvalidModelOutput(f"no JSON object in model reply: {text[:200]!r}")
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise InvalidModelOutput(f"invalid JSON in model reply: {exc}") from exc
    if not isinstance(value, dict):
        raise InvalidModelOutput("model reply is not a JSON object")
    return value


class BedrockLLM:
    """Converse with temperature 0. A schema becomes a single tool that the model must call,
    which is how Nova returns structured JSON."""

    def __init__(self, client: Any, model_id: str):
        self.client = client
        self.model_id = model_id
        self.name = f"bedrock:{model_id}"

    def complete(
        self, system: str, user: str, *, max_tokens: int, schema: dict | None = None
    ) -> Completion:
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system}],
            "messages": [{"role": "user", "content": [{"text": user}]}],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0},
        }
        if schema is not None:
            request["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": REPLY_TOOL,
                            "description": "Return the reply in the required JSON shape.",
                            "inputSchema": {"json": schema},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": REPLY_TOOL}},
            }
        try:
            response = self.client.converse(**request)
        except Exception as exc:
            if error_code(exc) in TRANSIENT_ERRORS:
                raise LLMUnavailable(f"{error_code(exc)}: {exc}") from exc
            raise

        stop = response.get("stopReason", "")
        usage = response.get("usage", {})
        content = response.get("output", {}).get("message", {}).get("content", [])
        if schema is not None:
            tool_input = next((b["toolUse"]["input"] for b in content if "toolUse" in b), None)
            # Fall back to JSON in plain text, in case the model answered without the tool.
            text = json.dumps(tool_input) if isinstance(tool_input, dict) else _text(content)
        else:
            text = _text(content)
        if stop == "max_tokens" and schema is not None:
            raise InvalidModelOutput(f"reply cut off at max_tokens={max_tokens}")
        return Completion(
            text=text,
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            stop_reason=stop,
        )


def _text(content: list[dict]) -> str:
    return "".join(b.get("text", "") for b in content)


@dataclass(frozen=True)
class GuardrailResult:
    intervened: bool
    blocked: bool  # True if any policy blocked the text (not just masked it)
    text: str  # the text to use from here on: masked if PII was anonymised, else unchanged
    findings: list[str] = field(default_factory=list)  # e.g. "topic:Legal advice", no raw matches
    units: int = 0  # text units billed across policies


class Guardrail(Protocol):
    def check(self, text: str, source: Literal["INPUT", "OUTPUT"]) -> GuardrailResult: ...


class BedrockGuardrail:
    def __init__(self, client: Any, guardrail_id: str, version: str):
        self.client = client
        self.guardrail_id = guardrail_id
        self.version = version

    def check(self, text: str, source: Literal["INPUT", "OUTPUT"]) -> GuardrailResult:
        try:
            response = self.client.apply_guardrail(
                guardrailIdentifier=self.guardrail_id,
                guardrailVersion=self.version,
                source=source,
                content=[{"text": {"text": text}}],
            )
        except Exception as exc:
            if error_code(exc) in TRANSIENT_ERRORS:
                raise LLMUnavailable(f"guardrail {error_code(exc)}: {exc}") from exc
            raise
        return parse_guardrail_response(response, text)


def parse_guardrail_response(response: dict, original: str) -> GuardrailResult:
    """Summarise an ApplyGuardrail response. Findings name the policy and type but never the
    matched text, so they are safe to log."""
    intervened = response.get("action") == "GUARDRAIL_INTERVENED"
    findings: list[str] = []
    blocked = False
    for assessment in response.get("assessments", []):
        entries = [
            ("topic", e.get("name"), e) for e in assessment.get("topicPolicy", {}).get("topics", [])
        ]
        entries += [
            ("content", e.get("type"), e)
            for e in assessment.get("contentPolicy", {}).get("filters", [])
        ]
        entries += [
            ("word", e.get("type", "custom"), e)
            for policy in ("customWords", "managedWordLists")
            for e in assessment.get("wordPolicy", {}).get(policy, [])
        ]
        pii = assessment.get("sensitiveInformationPolicy", {})
        entries += [("pii", e.get("type"), e) for e in pii.get("piiEntities", [])]
        entries += [("regex", e.get("name"), e) for e in pii.get("regexes", [])]
        for kind, label, entry in entries:
            if entry.get("detected") is False:
                continue  # present only with outputScope=FULL; not a finding
            action = entry.get("action", "")
            findings.append(f"{kind}:{label}:{action}")
            blocked = blocked or action == "BLOCKED"

    outputs = response.get("outputs") or response.get("output") or []
    text = original
    if intervened and not blocked and outputs:
        text = "".join(o.get("text", "") for o in outputs)  # anonymised version
    usage = response.get("usage", {})
    units = sum(int(v) for k, v in usage.items() if k.endswith("Units") and "Free" not in k)
    return GuardrailResult(intervened, blocked, text, findings, units)


def make_clients(region: str):
    """bedrock-runtime client with short timeouts and standard retries (Lambda has 25 s)."""
    import boto3
    from botocore.config import Config

    config = Config(
        region_name=region,
        connect_timeout=3,
        read_timeout=15,
        retries={"mode": "standard", "max_attempts": 3},
    )
    return boto3.client("bedrock-runtime", config=config)
