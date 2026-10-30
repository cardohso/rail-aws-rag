# Tuning notes: why the first live gate runs failed and what changed

The thresholds in `thresholds.yaml` were written before the first run and were not touched.
Everything below changed the pipeline, not the bar.

## What the live gate measured first

| Run (deployed API, 20 questions) | hit_rate | answered_rate | recall_at_k | grounding | refusal_rate |
|---|---|---|---|---|---|
| Amazon Nova Lite | 0.75 | 0.75 | 0.72 | 1.00 | 0.75 |
| Amazon Nova 2 Lite | 0.69 | 0.69 | 0.63 | 1.00 | 0.75 |
| Threshold | 0.80 | 0.80 | 0.60 | 0.90 | 0.75 |

Both failed `hit_rate` and `answered_rate`. The files are in `results/`.

## What the traces showed

My first reading, "retrieval is fine because the best cosine is above 0.6", was wrong. A high
best score says some passage is close, not that the *right* passage is in the top 8.

`local_system.py` runs the same pipeline and Guardrail from a laptop, without the API's daily
quota, and records every model reply. It reproduced the four refused questions of the live run
(q03, q06, q09, q10), and for q03, q06, q10 and q13 the gold passage was **not in the top 8**.

The cause is the query rewrite. The rewrite prompt lists the corpus ("Interoperability Directive
(EU) 2016/797 ... TSIs for control-command and signalling ..."), and Nova Lite copies that list
into the query, which drowns the real keywords. No model call is needed to check it. Gold passage
in the top 8, for the 16 answerable questions:

| Query used for retrieval | found | recall@8 |
|---|---|---|
| the question itself | 16 / 16 | 1.00 |
| Gemini rewrite (the rail assistant's, saved) | 16 / 16 | 1.00 |
| Nova Lite rewrite (as deployed) | 12 / 16 | 0.75 |

## Changes

1. **Retrieval uses the user's question; the rewrite is optional and off** (`PipelineConfig.rewrite`,
   env `REWRITE=1`). One model call fewer per question, and the PII-masked question is what gets
   embedded.
2. **The generator is told how many passages it has** ("numbered [1] to [N]; cite only these
   numbers") and that an answer which only restates the question is insufficient.

## Result on the 20 questions, same thresholds

| Run | hit_rate | answered_rate | recall_at_k | grounding | refusal_rate | gate |
|---|---|---|---|---|---|---|
| Before, run locally (Nova Lite) | 0.69 | 0.75 | 0.66 | 1.00 | 0.75 | fail |
| After, run locally (Nova Lite), run 1 | 0.94 | 0.94 | 0.89 | 1.00 | 0.75 | pass |
| After, run locally (Nova Lite), run 2 | 0.94 | 0.94 | 0.89 | 1.00 | 0.75 | pass |

The result above is from the local harness. The live gate against the deployed API has to be rerun
after the new code is deployed, and that run is the one that counts.

## Limits, stated plainly

- **I tuned on the same 20 questions that gate the result.** The retrieval finding is structural
  (the rewrite copies its own prompt), so it should hold on other questions, but the pass is not
  independent evidence. A held-out question set would be needed to claim more.
- **Two questions are still wrong.** q09 is refused because the generator cites `[4]` and `[5]`
  when it was given one passage. q19 should be refused but is answered with a vacuous sentence,
  because the grader accepts seven passages for an out-of-scope question. `refusal_rate` sits
  exactly on its 0.75 minimum, so one more wrong answer fails it.
- Runs are repeatable at temperature 0 (two identical outcomes), but Bedrock does not promise
  bit-identical replies.
