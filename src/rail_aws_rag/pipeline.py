"""The RAG flow as plain functions, with the refusal gates of rail-regulation-rag plus Guardrails.

    guard input -> rewrite -> retrieve -> grade -> generate -> guard output -> answer
        |                       |          |          |              |
        +-----------------------+----------+----------+--------------+--> refuse (with a reason)

Every refusal names its reason. The cheap gates come first: a blocked question or a low retrieval
score is refused before any further model call.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from rail_aws_rag import prompts
from rail_aws_rag.bedrock import LLM, Guardrail, GuardrailResult, InvalidModelOutput, parse_json
from rail_aws_rag.citations import format_citations, renumber
from rail_aws_rag.embeddings import Embedder, SparseEncoder
from rail_aws_rag.index import Index, SearchHit

RefusalReason = Literal[
    "guardrail_input",
    "low_retrieval_score",
    "no_relevant_passages",
    "insufficient_context",
    "no_citations",
    "invalid_model_output",
    "guardrail_output",
]


@dataclass(frozen=True)
class PipelineConfig:
    k: int = 8  # passages retrieved
    min_score: float = 0.60  # cosine floor: below this, refuse without calling the LLM again
    hybrid: bool = True  # BM25 + dense, fused with RRF
    max_context: int = 5  # graded passages passed to the generator
    # Search with the user's own question. A model rewrite is optional: on the 16 answerable
    # golden questions the question alone finds the gold passage 16 times, and Nova Lite's
    # rewrite only 12 (it copies the corpus description from its prompt into the query).
    rewrite: bool = False
    # Every model call is capped. Measured shapes: a one-line query, a short list, <= 5 sentences.
    max_tokens_rewrite: int = 120
    max_tokens_grade: int = 100
    max_tokens_generate: int = 600


@dataclass
class Usage:
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    guardrail_units: int = 0


@dataclass
class AskResult:
    answer: str
    refused: bool
    refusal_reason: RefusalReason | None
    citations: list[dict]
    trace_id: str
    query: str = ""
    hits: list[SearchHit] = field(default_factory=list)  # raw retrieval, before grading
    contexts: list[SearchHit] = field(default_factory=list)  # passages given to the generator
    usage: Usage = field(default_factory=Usage)
    guardrail_findings: dict[str, list[str]] = field(default_factory=dict)
    latency_ms: int = 0

    def response(self) -> dict:
        """The public API body: the same shape as rail-regulation-rag's POST /ask."""
        return {
            "answer": self.answer,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "citations": self.citations,
            "trace_id": self.trace_id,
        }

    def log_record(self) -> dict:
        """What gets logged per request: no question or answer text, only measurements."""
        return {
            "trace_id": self.trace_id,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "n_hits": len(self.hits),
            "max_score": round(max((h.score for h in self.hits), default=0.0), 4),
            "n_context": len(self.contexts),
            "n_citations": len(self.citations),
            "llm_calls": self.usage.llm_calls,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "guardrail_units": self.usage.guardrail_units,
            "guardrail_findings": self.guardrail_findings,
            "latency_ms": self.latency_ms,
        }


def passage_numbers(value) -> list[int]:
    """Unique passage numbers from a grader reply. Tolerates shapes models drift into even with
    structured output: [[1], [2]], ["3"], 2."""
    out: list[int] = []
    stack = [value]
    while stack:
        v = stack.pop(0)
        if isinstance(v, list):
            stack[:0] = v
        elif isinstance(v, bool):
            continue
        elif isinstance(v, int) or (isinstance(v, str) and v.strip().isdigit()):
            n = int(v)
            if n not in out:
                out.append(n)
    return out


def keyword_text(question: str, query: str) -> str:
    """BM25 input: the rewritten query plus the user's own words, so exact wording survives."""
    return query if query == question else f"{query} {question}"


class Pipeline:
    def __init__(
        self,
        llm: LLM,
        index: Index,
        dense: Embedder,
        sparse: SparseEncoder,
        guardrail: Guardrail | None = None,
        cfg: PipelineConfig | None = None,
    ):
        self.llm, self.index, self.dense, self.sparse = llm, index, dense, sparse
        self.guardrail = guardrail
        self.cfg = cfg or PipelineConfig()
        self.celex = {d.id: d.celex for d in index.documents}

    def _complete(self, usage: Usage, system: str, user: str, max_tokens: int, schema=None):
        reply = self.llm.complete(system, user, max_tokens=max_tokens, schema=schema)
        usage.llm_calls += 1
        usage.input_tokens += reply.input_tokens
        usage.output_tokens += reply.output_tokens
        return reply

    def _guard(self, result: AskResult, text: str, source) -> GuardrailResult | None:
        if self.guardrail is None:
            return None
        checked = self.guardrail.check(text, source)
        result.usage.guardrail_units += checked.units
        if checked.findings:
            result.guardrail_findings[source.lower()] = checked.findings
        return checked

    def ask(self, question: str, trace_id: str | None = None) -> AskResult:
        start = time.perf_counter()
        result = AskResult("", False, None, [], trace_id or uuid.uuid4().hex)
        try:
            self._run(question, result)
        finally:
            result.latency_ms = int((time.perf_counter() - start) * 1000)
        return result

    def _refuse(self, result: AskResult, reason: RefusalReason) -> None:
        result.refused, result.refusal_reason, result.citations = True, reason, []
        blocked = reason in ("guardrail_input", "guardrail_output")
        result.answer = prompts.GUARDRAIL_REFUSAL if blocked else prompts.REFUSAL

    def _run(self, question: str, result: AskResult) -> None:
        cfg, usage = self.cfg, result.usage

        checked = self._guard(result, question, "INPUT")
        if checked and checked.blocked:
            return self._refuse(result, "guardrail_input")
        if checked:
            question = checked.text  # PII masked, if any

        try:
            result.query = question
            if cfg.rewrite:
                lines = self._complete(
                    usage, prompts.REWRITE, question, cfg.max_tokens_rewrite
                ).text.strip()
                result.query = (lines.splitlines() or [""])[0].strip() or question

            terms = (
                self.sparse.embed_query(keyword_text(question, result.query))
                if cfg.hybrid
                else None
            )
            result.hits = self.index.search(
                self.dense.embed_query(result.query), k=cfg.k, sparse=terms
            )
            # Best cosine among the hits: in hybrid mode the top-ranked passage can be a keyword
            # match with a lower cosine than one ranked below it.
            if not result.hits or max(h.score for h in result.hits) < cfg.min_score:
                return self._refuse(result, "low_retrieval_score")

            user = f"Question: {question}\n\nPassages:\n" + prompts.numbered_passages(
                [h.passage.embed_text for h in result.hits]
            )
            reply = parse_json(
                self._complete(
                    usage, prompts.GRADE, user, cfg.max_tokens_grade, prompts.GRADE_SCHEMA
                ).text
            )
            picked = [
                i for i in passage_numbers(reply.get("relevant")) if 1 <= i <= len(result.hits)
            ]
            # Keep retrieval order (best first), not the order the grader listed them.
            result.contexts = [result.hits[i - 1] for i in sorted(picked)][: cfg.max_context]
            if not result.contexts:
                return self._refuse(result, "no_relevant_passages")

            n = len(result.contexts)
            user = (
                f"Question: {question}\n\nPassages (numbered [1] to [{n}]; cite only these "
                f"numbers):\n"
                + prompts.numbered_passages([h.passage.embed_text for h in result.contexts])
            )
            reply = parse_json(
                self._complete(
                    usage,
                    prompts.GENERATE,
                    user,
                    cfg.max_tokens_generate,
                    prompts.GENERATE_SCHEMA,
                ).text
            )
        except InvalidModelOutput:
            return self._refuse(result, "invalid_model_output")

        insufficient = reply.get("insufficient")
        if isinstance(insufficient, str):  # "false" is truthy; models sometimes quote booleans
            insufficient = insufficient.strip().lower() == "true"
        if insufficient or not str(reply.get("answer", "")).strip():
            return self._refuse(result, "insufficient_context")
        answer, cited = renumber(str(reply["answer"]), result.contexts)
        if not cited:  # an answer we cannot ground in a passage is not returned
            return self._refuse(result, "no_citations")

        checked = self._guard(result, answer, "OUTPUT")
        if checked and checked.blocked:
            return self._refuse(result, "guardrail_output")
        result.answer = checked.text if checked else answer
        result.citations = format_citations(cited, self.celex)
        result.refused, result.refusal_reason = False, None
