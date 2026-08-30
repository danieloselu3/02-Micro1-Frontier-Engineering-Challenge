# Baseline vs. agent pipeline

_Generated 2026-08-30 09:23 UTC over 49 cases._

## Results

| Metric | Baseline | Agent pipeline | Change |
|---|---:|---:|---:|
| Verdict accuracy | 71.4% | 91.8% | ↑ +20.4% |
| Reason accuracy | 69.4% | 73.5% | ↑ +4.1% |
| False denials | 6 | 2 | ↓ -4 |
| False approvals | 5 | 0 | ↓ -5 |
| Mean cost per case | $0.02245 | $0.05980 | ↑ $0.03736 ⚠ |
| Mean latency (s) | 7.26 | 25.34 | ↑ +18.08 ⚠ |
| Model calls | 49 | 108 | ↑ +59 ⚠ |

## Why the two error types are reported separately

A wrong approval costs the payer money and is recoverable when the claim is adjudicated. A wrong denial delays someone's treatment and starts an appeal that takes weeks. They are not interchangeable, and a single blended accuracy figure lets a system trade the second for the first invisibly -- which, because approvals are the majority class in production, is exactly the trade an optimiser makes.

- **False denials** — baseline 6, pipeline 2
- **False approvals** — baseline 5, pipeline 0

## Extraction accuracy by document condition

The baseline emits no per-field transcription, so it is not scored here. These figures are the pipeline's.

| Document tier | Cases | Field accuracy | Verdict accuracy |
|---|---:|---:|---:|
| clean | 12 | 100.0% | 100.0% |
| fax | 13 | 88.5% | 92.3% |
| handwritten | 2 | 91.7% | 100.0% |
| photo | 11 | 100.0% | 100.0% |
| scan | 11 | 100.0% | 72.7% |

## Where the cost difference comes from

The pipeline made **108 model calls** across 49 cases against the baseline's 49, and **22 of 49 cases reached a determination without ever paying for an adjudication** — 3 for procedures that never required authorization, and 19 stopped by a contractual or eligibility rule, where medical necessity is irrelevant and assessing it anyway would be waste with a clinical risk attached.

Extraction runs on every case, so no case reaches zero model calls. The saving is in the two stages that follow it.

## Per scenario

Every scenario is listed, including the ones the pipeline handles worst.

| Scenario | Cases | Baseline verdict | Pipeline verdict | Pipeline reason |
|---|---:|---:|---:|---:|
| always_review_specialty_drug | 2 | 0.0% | 0.0% | 0.0% |
| clean_approval_faxed | 2 | 100.0% | 100.0% | 100.0% |
| code_mismatch | 2 | 0.0% | 100.0% | 50.0% |
| cosmetic_functional_exception | 1 | 0.0% | 100.0% | 100.0% |
| cosmetic_purely_aesthetic | 1 | 100.0% | 100.0% | 100.0% |
| duplicate_authorization | 2 | 0.0% | 100.0% | 100.0% |
| excluded_cosmetic | 2 | 0.0% | 100.0% | 100.0% |
| illegible_member_id | 2 | 100.0% | 100.0% | 100.0% |
| license_expired | 1 | 100.0% | 100.0% | 100.0% |
| limit_exhausted | 2 | 100.0% | 100.0% | 100.0% |
| limit_partial | 2 | 0.0% | 100.0% | 100.0% |
| name_mismatch | 2 | 100.0% | 100.0% | 100.0% |
| necessity_borderline | 2 | 100.0% | 50.0% | 0.0% |
| necessity_met | 3 | 100.0% | 100.0% | 100.0% |
| necessity_met_tka | 2 | 100.0% | 100.0% | 100.0% |
| necessity_no_evidence | 3 | 33.3% | 66.7% | 0.0% |
| necessity_no_evidence_tka | 2 | 100.0% | 100.0% | 0.0% |
| necessity_unmet | 3 | 100.0% | 100.0% | 0.0% |
| no_auth_required | 3 | 100.0% | 100.0% | 100.0% |
| out_of_area | 2 | 50.0% | 100.0% | 100.0% |
| out_of_network | 2 | 100.0% | 100.0% | 100.0% |
| premium_delinquent | 1 | 100.0% | 100.0% | 100.0% |
| provider_sanctioned | 1 | 100.0% | 100.0% | 100.0% |
| terminated_policy | 2 | 100.0% | 100.0% | 100.0% |
| within_waiting_period | 2 | 100.0% | 100.0% | 100.0% |

## Cases the pipeline got wrong

| Case | Scenario | Expected | Produced | Rule cited |
|---|---|---|---|---|
| CASE-034 | necessity_no_evidence | pended | denied | MP-IMG-001#4 |
| CASE-038 | necessity_borderline | pended | denied | MP-PAI-001#2 |
| CASE-042 | always_review_specialty_drug | approved | pended | MP-ONC-001#1 |
| CASE-043 | always_review_specialty_drug | approved | pended | R2 |

## What these numbers do not say

**The case mix is not production-representative.** It is a stress set built for failure-mode coverage, weighted heavily toward denials and adversarial conditions. Real prior authorization approves roughly 85% of requests. Accuracy here is a measure of robustness across failure modes, not an estimate of production performance.

**The baseline is given an advantage.** It receives the correct member, provider and procedure records directly, while the pipeline must resolve them from the document it read. The comparison is therefore conservative: the baseline is spared a step the real system has to get right.

**Both systems are graded against synthetic ground truth.** The labels are derived from generated record state, not from decisions made by practising utilization-review nurses.
