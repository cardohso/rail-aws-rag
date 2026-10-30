"""A goldpass `python` system: the real pipeline and the real Bedrock, run on this machine.

The live gate calls the deployed API, which is capped at 50 questions a day. To tune prompts and
compare models, this runs the same pipeline, the same index and the same Guardrail from here, so
a run costs the same few cents but uses none of the API's daily quota. It also writes a trace of
every model reply, which the API never returns, so a refusal can be traced to the step that
caused it.

    PYTHONPATH=eval/live:src uv run goldpass run --config eval/live/local.yaml

Bedrock is called through the AWS CLI (already installed, no extra package). Settings come from
the deployed Lambda, so the defaults mirror production; override with MODEL_ID, GUARDRAIL_ID and
GUARDRAIL_VERSION, and pick the credentials with AWS_PROFILE.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

from rail_aws_rag import prompts
from rail_aws_rag.bedrock import BedrockGuardrail, BedrockLLM, Completion
from rail_aws_rag.corpus import REPO_ROOT
from rail_aws_rag.embeddings import BM25Encoder, LocalEmbedder
from rail_aws_rag.index import Index
from rail_aws_rag.pipeline import Pipeline, PipelineConfig

REGION = "eu-west-1"
FUNCTION = "rail-aws-rag-ask"
TRACE = REPO_ROOT / "build" / "local" / "trace.jsonl"
STEPS = {prompts.REWRITE: "rewrite", prompts.GRADE: "grade", prompts.GENERATE: "generate"}


class CliError(RuntimeError):
    """A failed `aws` call, shaped like botocore's ClientError so error_code() reads it."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.response = {"Error": {"Code": code, "Message": message}}


def error_code_from(stderr: str) -> str:
    """The AWS error code in the CLI's message: 'An error occurred (ThrottlingException) ...'."""
    match = re.search(r"\((\w+Exception)\)", stderr)
    return match.group(1) if match else "CliError"


def run_aws(args: list[str]) -> dict:
    done = subprocess.run(["aws", *args, "--region", REGION, "--output", "json"],
                          capture_output=True, text=True, timeout=60)  # fmt: skip
    if done.returncode != 0:
        raise CliError(done.stderr.strip()[-300:], error_code_from(done.stderr))
    return json.loads(done.stdout) if done.stdout.strip() else {}


class CliBedrock:
    """The two bedrock-runtime calls the pipeline makes, with boto3's call shape."""

    def converse(self, **request) -> dict:
        return run_aws(["bedrock-runtime", "converse", "--cli-input-json", json.dumps(request)])

    def apply_guardrail(self, **request) -> dict:
        return run_aws(
            ["bedrock-runtime", "apply-guardrail", "--cli-input-json", json.dumps(request)]
        )


class TracingLLM:
    """Records every reply of one question, tagged with the step that asked for it."""

    def __init__(self, inner: BedrockLLM):
        self.inner, self.name, self.calls = inner, inner.name, []

    def complete(self, system, user, *, max_tokens, schema=None) -> Completion:
        reply = self.inner.complete(system, user, max_tokens=max_tokens, schema=schema)
        self.calls.append(
            {
                "step": STEPS.get(system, "?"),
                "user_chars": len(user),
                "reply": reply.text,
                "stop": reply.stop_reason,
            }
        )
        return reply


def production_settings() -> dict[str, str]:
    """MODEL_ID and the guardrail from the deployed Lambda, unless the environment overrides."""
    env = {
        k: os.environ[k]
        for k in ("MODEL_ID", "GUARDRAIL_ID", "GUARDRAIL_VERSION")
        if k in os.environ
    }
    if len(env) < 3:
        deployed = run_aws(
            ["lambda", "get-function-configuration", "--function-name", FUNCTION,
             "--query", "Environment.Variables"]
        )  # fmt: skip
        env = {k: deployed[k] for k in ("MODEL_ID", "GUARDRAIL_ID", "GUARDRAIL_VERSION")} | env
    return env


_pipeline: tuple[Pipeline, TracingLLM] | None = None


def get_pipeline() -> tuple[Pipeline, TracingLLM]:
    global _pipeline
    if _pipeline is None:
        settings = production_settings()
        bedrock = CliBedrock()
        llm = TracingLLM(BedrockLLM(bedrock, settings["MODEL_ID"]))
        guardrail = BedrockGuardrail(
            bedrock, settings["GUARDRAIL_ID"], settings["GUARDRAIL_VERSION"]
        )
        index = Index.load(REPO_ROOT / "build" / "index")
        _pipeline = (
            Pipeline(llm, index, LocalEmbedder(), BM25Encoder(), guardrail, PipelineConfig()),
            llm,
        )
        print(f"local system: {llm.name}, guardrail {settings['GUARDRAIL_ID']}")
    return _pipeline


def ask(question: str) -> dict:
    pipeline, llm = get_pipeline()
    llm.calls = []
    result = pipeline.ask(question)
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    with TRACE.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "model": llm.name,
                    "question": question,
                    "refused": result.refused,
                    "refusal_reason": result.refusal_reason,
                    "query": result.query,
                    "hits": [[h.passage.id, round(h.score, 3)] for h in result.hits],
                    "context": [h.passage.id for h in result.contexts],
                    "guardrail": result.guardrail_findings,
                    "calls": llm.calls,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    # goldpass's default shape for a Python system: contexts and citations as the live API's
    # citations, so these numbers are comparable with the live gate.
    cited = [
        {"id": c["passage_id"], "doc_id": c["doc_id"], "text": c["passage"], "score": c["score"]}
        for c in result.citations
    ]
    return {
        "answer": result.answer,
        "refused": result.refused,
        "contexts": cited,
        "citations": [{"passage_id": c["id"], "doc_id": c["doc_id"]} for c in cited],
    }
