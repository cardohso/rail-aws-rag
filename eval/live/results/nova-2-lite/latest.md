## goldpass: FAILED ❌

System `http:POST https://<api-id>.execute-api.eu-west-1.amazonaws.com/ask` · generator `amazon.nova-2-lite-v1` (amazon) · no LLM judge · 20 golden items · commit `f9ce129` · 2026-10-30T15:59:36Z

| Metric | Value | 95% CI | n | Threshold | Status |
|---|---|---|---|---|---|
| Precision@k | 0.66 | 0.41–0.84 | 16 | — |  |
| Recall@k | 0.62 | 0.39–0.82 | 16 | ≥ 0.6 | ✅ |
| Context precision | 0.69 | 0.44–0.86 | 16 | — |  |
| MRR | 0.69 | 0.44–0.86 | 16 | — |  |
| Hit@k | 0.69 | 0.44–0.86 | 16 | ≥ 0.8 | ❌ |
| Grounding | 1.00 | 0.74–1.00 | 11 | ≥ 0.9 | ✅ |
| Answered rate | 0.69 | 0.44–0.86 | 16 | ≥ 0.8 | ❌ |
| Refusal rate | 0.75 | 0.30–0.95 | 4 | ≥ 0.75 | ✅ |
| Errors | 0 |  |  | ≤ 0 | ✅ |

_95% CI: Wilson score interval over n questions (conservative for scores that are not yes/no). With few questions it is wide: one question moves a rate by 1/n._

> ⚠️ **Fragile:** passes, but a single question could fail it: Recall@k, Refusal rate, Grounding [tag:wrong-document].

### What failed

- **Hit@k**: 0.688 < 0.8 (needs ≥ 0.8; 2 questions from passing)
  - failing questions: `q09`, `q10`, `q11`, `q13`, `q16`
- **Answered rate**: 0.688 < 0.8 (needs ≥ 0.8; 2 questions from passing)
  - failing questions: `q09`, `q10`, `q11`, `q13`, `q16`

### By tag

| Tag | Answered rate | Grounding | Recall@k | Faithfulness (judge) |
|---|---|---|---|---|
| `wrong-document` | 0.67 (n=3) | 1.00 (n=2) | 0.67 (n=3) | — |

### Grounding per source document

| Document | Questions | Answered | Grounding | Also cited |
|---|---|---|---|---|
| `iop-directive` | 3 | 2 | 1.00 | — |
| `tsi-ccs` | 1 | 0 | — | — |
| `tsi-ene` | 1 | 1 | 1.00 | — |
| `tsi-noi` | 2 | 2 | 1.00 | — |
| `tsi-ope` | 3 | 0 | — | — |
| `tsi-prm` | 2 | 2 | 1.00 | — |
| `tsi-srt` | 4 | 4 | 1.00 | — |

<details><summary>Per-item scores</summary>

| Item | Expected | Refused | Recall@k | Grounding | Faithfulness (judge) | Answer relevancy (judge) | Note |
|---|---|---|---|---|---|---|---|
| `q01` | answer | no | 1.00 | yes | — | — |  |
| `q02` | answer | no | 1.00 | yes | — | — |  |
| `q03` | answer | no | 1.00 | yes | — | — |  |
| `q04` | answer | no | 1.00 | yes | — | — |  |
| `q05` | answer | no | 0.50 | yes | — | — |  |
| `q06` | answer | no | 1.00 | yes | — | — |  |
| `q07` | answer | no | 1.00 | yes | — | — |  |
| `q08` | answer | no | 1.00 | yes | — | — |  |
| `q09` | answer | yes | 0.00 | — | — | — |  |
| `q10` | answer | yes | 0.00 | — | — | — |  |
| `q11` | answer | yes | 0.00 | — | — | — |  |
| `q12` | answer | no | 0.50 | yes | — | — |  |
| `q13` | answer | yes | 0.00 | — | — | — |  |
| `q14` | answer | no | 1.00 | yes | — | — |  |
| `q15` | answer | no | 1.00 | yes | — | — |  |
| `q16` | answer | yes | 0.00 | — | — | — |  |
| `q17` | refuse | yes | — | — | — | — |  |
| `q18` | refuse | yes | — | — | — | — |  |
| `q19` | refuse | no | — | — | — | — |  |
| `q20` | refuse | yes | — | — | — | — |  |

</details>

_No baseline found at `eval/live/baseline.json`: the comparison was skipped._
