# CASE-001 — no_auth_required

> Fast path — the procedure needs no authorization. One model call, exits before retrieval.

## Outcome

| | |
|---|---|
| Produced | **no_auth_required** citing `R1` |
| Gold label | **no_auth_required** citing `R1` |
| Correct | yes |
| Routed to a clinician | no — auto-released |
| Model calls | 1 |
| Cost | $0.027189 |
| Document condition | clean |

## Agent instructions

The system prompts are version-controlled and are not repeated here:

- `agents/intake_extractor/prompt.md`
- `agents/adjudicator/prompt.md`
- `agents/reviewer_critic/prompt.md`

## Trajectory

### Step 1 — `extract` (model)

*intake_extractor reads the page and reports per-field confidence*

`claude-sonnet-5` · 4373 in / 938 out · 8.2s

<details><summary>Prompt sent</summary>

```text
[page image, 78 KB PNG — see the case document]

Transcribe this prior-authorization form. Return the JSON object described in your instructions and nothing else.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "fields": {
    "member_name": {"value": "Mark Rodgers", "confidence": 0.98, "bbox": {"x": 0.09, "y": 0.148, "width": 0.30, "height": 0.02}},
    "member_id": {"value": "MBR-100120", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.148, "width": 0.25, "height": 0.02}},
    "date_of_birth": {"value": "12/05/1980", "confidence": 0.98, "bbox": {"x": 0.09, "y": 0.198, "width": 0.25, "height": 0.02}},
    "group_number": {"value": "GRP-1055", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.198, "width": 0.25, "height": 0.02}},
    "plan": {"value": "PLN-PPO-GOLD", "confidence": 0.97, "bbox": {"x": 0.09, "y": 0.248, "width": 0.25, "height": 0.02}},
    "provider_name": {"value": "Johnson Regional Medical Center", "confidence": 0.97, "bbox": {"x": 0.09, "y": 0.352, "width": 0.35, "height": 0.02}},
    "provider_npi": {"value": "9270405488", "confidence": 0.95, "bbox": {"x": 0.51, "y": 0.352, "width": 0.25, "height": 0.02}},
    "license_state": {"value": "MI", "confidence": 0.95, "bbox": {"x": 0.51, "y": 0.402, "width": 0.1, "height": 0.02}},
    "procedure_code": {"value": "45378", "confidence": 0.98, "bbox": {"x": 0.09, "y": 0.5, "width": 0.15, "height": 0.02}},
    "date_of_service": {"value": "08/14/2026", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.5, "width": 0.2, "height": 0.02}},
    "units_requested": {"value": "1", "confidence": 0.98, "bbox": {"x": 0.51, "y": 0.55, "width": 0.05, "height": 0.02}},
    "diagnosis_code": {"value": "Z12.11", "confidence": 0.97, "bbox": {"x": 0.09, "y": 0.6, "width": 0.15, "height": 0.02}}
  },
  "clinical_narrative": "45-year-old presenting for average-risk colorectal cancer screening. No family history of colorectal malignancy, no rectal bleeding, no change in bowel habit. Submitting for authorization prior to scheduling.",
  "notes": []
}
```
```
</details>

### Step 2 — resolve entities (deterministic)

*Transcribed strings matched onto real records. No model.*

```text
member   MBR-100120  (match confidence 1.00)
provider 9270405488
procedure 45378   diagnosis Z12.11
date of service 2026-08-14
```

### Step 3 — evaluate 9 rules (deterministic)

*Pure functions over the payer records. No model.*

```text
[R1] n/a      CPT 45378 (Colonoscopy, diagnostic, with or without collection of specimen) does not require prior authorization under this plan.
          evidence: procedure_code=45378, requires_preauth=false
[R2] PASS     Coverage active on 08/14/2026.
          evidence: member_id=MBR-100120, status=active, effective_date=2025-10-18, date_of_service=2026-08-14
[R3] n/a      Meridian PPO Gold carries no waiting period.
          evidence: plan_id=PLN-PPO-GOLD, waiting_period_days=0
[R4] PASS     Endoscopy is a covered category under Meridian PPO Gold.
          evidence: plan_id=PLN-PPO-GOLD, procedure_code=45378, category=endoscopy, excluded_categories=cosmetic
[R5] PASS     Provider state MI is within the plan service area.
          evidence: plan_id=PLN-PPO-GOLD, provider_npi=9270405488, provider_state=MI, covered_states=OH, MI, IN, KY, PA, WV
[R6] PASS     Provider is contracted, licensed through 06/30/2027, and in good standing.
          evidence: provider_npi=9270405488, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=false
[R7] PASS     20000.00 remains in the outpatient benefit against a request of 2240.00.
          evidence: category=outpatient, plan_year=2026, limit_amount=25000.00, consumed_amount=5000.00, remaining=20000.00, requested_amount=2240.00
[R8] PASS     No active authorization covers this procedure and date.
          evidence: prior_auths_checked=0
[R9] PASS     Diagnosis Z12.11 supports CPT 45378.
          evidence: procedure_code=45378, submitted_diagnoses=Z12.11, supporting_diagnoses=Z12.11, R10.9, K21.9
```

## Final determination

**no_auth_required** — CPT 45378 (Colonoscopy, diagnostic, with or without collection of specimen) does not require prior authorization under this plan. The provider may proceed with the service. No authorization number is issued, because no authorization was adjudicated -- this notice confirms none is needed.

---

_Replayed from the committed response cache 2026-08-30 10:07 UTC. No live model calls._