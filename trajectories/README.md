# Agent trajectories

One trace per distinct path through the system, replayed from the committed response cache. Each shows the agent instructions in use, every prompt and response, the deterministic stages between them, any retry, and whether a clinician was required.

Regenerate with `python -m eval.harness.trajectories` — it costs nothing and needs no API key.

## Agents

| Agent | Instructions | Role |
|---|---|---|
| `intake_extractor` | [prompt.md](../agents/intake_extractor/prompt.md) | Reads the form; reports what it could not read rather than guessing |
| `adjudicator` | [prompt.md](../agents/adjudicator/prompt.md) | Judges the narrative against retrieved criteria. Returns no verdict |
| `reviewer_critic` | [prompt.md](../agents/reviewer_critic/prompt.md) | Audits the rationale for claims not traceable to evidence |

## Traces

| Case | Scenario | Verdict correct | Trace |
|---|---|---|---|
| CASE-001 | no_auth_required | yes | [CASE-001.md](CASE-001.md) |
| CASE-004 | terminated_policy | yes | [CASE-004.md](CASE-004.md) |
| CASE-025 | necessity_met | yes | [CASE-025.md](CASE-025.md) |
| CASE-021 | duplicate_authorization | yes | [CASE-021.md](CASE-021.md) |
| CASE-033 | necessity_no_evidence | yes | [CASE-033.md](CASE-033.md) |
| CASE-046 | illegible_member_id | yes | [CASE-046.md](CASE-046.md) |
| CASE-034 | necessity_no_evidence | **no** | [CASE-034.md](CASE-034.md) |

The set deliberately includes a case the system gets wrong. A trajectory set showing only successes is marketing, not evidence.
