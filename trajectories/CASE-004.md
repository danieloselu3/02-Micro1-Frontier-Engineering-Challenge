# CASE-004 — terminated_policy

> Hard stop — coverage terminated. Extraction only; no adjudication is ever paid for.

## Outcome

| | |
|---|---|
| Produced | **denied** citing `R2` |
| Gold label | **denied** citing `R2` |
| Correct | yes |
| Routed to a clinician | yes |
| Model calls | 1 |
| Cost | $0.031266 |
| Document condition | photo |

**Why a human was required**

- Denials are always reviewed by a clinician before they are issued.

## Agent instructions

The system prompts are version-controlled and are not repeated here:

- `agents/intake_extractor/prompt.md`
- `agents/adjudicator/prompt.md`
- `agents/reviewer_critic/prompt.md`

## Trajectory

### Step 1 — `extract` (model)

*intake_extractor reads the page and reports per-field confidence*

`claude-sonnet-5` · 4697 in / 1145 out · 10.3s

<details><summary>Prompt sent</summary>

```text
[page image, 1523 KB PNG — see the case document]

Transcribe this prior-authorization form. Return the JSON object described in your instructions and nothing else.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "fields": {
    "member_name": {"value": "Holly Moore", "confidence": 0.98, "bbox": {"x": 0.13, "y": 0.172, "width": 0.25, "height": 0.02}},
    "member_id": {"value": "MBR-100059", "confidence": 0.95, "bbox": {"x": 0.51, "y": 0.196, "width": 0.24, "height": 0.02}},
    "date_of_birth": {"value": "08/05/1972", "confidence": 0.97, "bbox": {"x": 0.13, "y": 0.229, "width": 0.22, "height": 0.02}},
    "group_number": {"value": "GRP-1045", "confidence": 0.96, "bbox": {"x": 0.51, "y": 0.253, "width": 0.2, "height": 0.02}},
    "plan": {"value": "PLN-HMO-CORE", "confidence": 0.97, "bbox": {"x": 0.13, "y": 0.283, "width": 0.24, "height": 0.02}},
    "provider_name": {"value": "Adams Regional Medical Center", "confidence": 0.97, "bbox": {"x": 0.13, "y": 0.373, "width": 0.36, "height": 0.02}},
    "provider_npi": {"value": "9995034623", "confidence": 0.95, "bbox": {"x": 0.51, "y": 0.38, "width": 0.24, "height": 0.02}},
    "license_state": {"value": "OH", "confidence": 0.95, "bbox": {"x": 0.51, "y": 0.432, "width": 0.08, "height": 0.02}},
    "procedure_code": {"value": "72148", "confidence": 0.99, "bbox": {"x": 0.13, "y": 0.499, "width": 0.14, "height": 0.02}},
    "date_of_service": {"value": "08/14/2026", "confidence": 0.96, "bbox": {"x": 0.51, "y": 0.514, "width": 0.2, "height": 0.02}},
    "units_requested": {"value": "1", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.567, "width": 0.06, "height": 0.02}},
    "diagnosis_code": {"value": "M54.16", "confidence": 0.97, "bbox": {"x": 0.13, "y": 0.598, "width": 0.15, "height": 0.02}}
  },
  "clinical_narrative": "Patient with persistent symptoms unresponsive to initial management. Conservative treatment including physical therapy and anti-inflammatory medication has been completed without adequate improvement. Examination and prior imaging support the requested service. Referred for further evaluation and management.",
  "notes": [
    "Image is a phone photograph with visible glare/shadow gradient across the page, but text remains legible.",
    "Highlighted/shaded boxes appear over some field values (member ID, procedure code, date of service, NPI) - these appear to be form field background shading, not obscuring the text.",
    "Provider description field also lists 'MRI lumbar spine without contrast' and diagnosis description 'Radiculopathy, lumbar region' - not requested in schema but visible for context.",
    "Signature line reads 'Adams Regional Medical Center' rather than an individual clinician name."
  ]
}
```
```
</details>

### Step 2 — resolve entities (deterministic)

*Transcribed strings matched onto real records. No model.*

```text
member   MBR-100059  (match confidence 1.00)
provider 9995034623
procedure 72148   diagnosis M54.16
date of service 2026-08-14
```

### Step 3 — evaluate 9 rules (deterministic)

*Pure functions over the payer records. No model.*

```text
[R1] PASS     CPT 72148 requires prior authorization.
          evidence: procedure_code=72148, requires_preauth=true
[R2] FAIL     Coverage terminated 07/31/2026, before the 08/14/2026 date of service.
          evidence: member_id=MBR-100059, status=terminated, effective_date=2026-03-02, termination_date=2026-07-31, date_of_service=2026-08-14
[R3] PASS     Waiting period satisfied 05/31/2026.
          evidence: plan_id=PLN-HMO-CORE, waiting_period_days=90, enrolled_at=2026-03-02, days_elapsed=165, satisfied_on=2026-05-31
[R4] PASS     Advanced Imaging is a covered category under Meridian HMO Core.
          evidence: plan_id=PLN-HMO-CORE, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic
[R5] PASS     Provider state OH is within the plan service area.
          evidence: plan_id=PLN-HMO-CORE, provider_npi=9995034623, provider_state=OH, covered_states=OH
[R6] PASS     Provider is contracted, licensed through 06/30/2027, and in good standing.
          evidence: provider_npi=9995034623, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=true
[R7] PASS     5400.00 remains in the imaging benefit against a request of 1450.00.
          evidence: category=imaging, plan_year=2026, limit_amount=6000.00, consumed_amount=600.00, remaining=5400.00, requested_amount=1450.00
[R8] PASS     No active authorization covers this procedure and date.
          evidence: prior_auths_checked=0
[R9] PASS     Diagnosis M54.16 supports CPT 72148.
          evidence: procedure_code=72148, submitted_diagnoses=M54.16, supporting_diagnoses=M54.50, M54.51, M51.26, M54.16
```

## Final determination

**denied** — Coverage terminated 07/31/2026, before the 08/14/2026 date of service.

---

_Replayed from the committed response cache 2026-08-30 10:07 UTC. No live model calls._