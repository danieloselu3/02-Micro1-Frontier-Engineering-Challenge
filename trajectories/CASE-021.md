# CASE-021 — duplicate_authorization

> A duplicate authorization is already on file. The baseline got this one wrong.

## Outcome

| | |
|---|---|
| Produced | **denied** citing `R8` |
| Gold label | **denied** citing `R8` |
| Correct | yes |
| Routed to a clinician | yes |
| Model calls | 1 |
| Cost | $0.028509 |
| Document condition | clean |

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

`claude-sonnet-5` · 4373 in / 1026 out · 19.7s

<details><summary>Prompt sent</summary>

```text
[page image, 79 KB PNG — see the case document]

Transcribe this prior-authorization form. Return the JSON object described in your instructions and nothing else.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "fields": {
    "member_name":      {"value": "Anita Ruiz", "confidence": 0.98, "bbox": {"x": 0.096, "y": 0.148, "width": 0.25, "height": 0.02}},
    "member_id":        {"value": "MBR-100118", "confidence": 0.98, "bbox": {"x": 0.51, "y": 0.148, "width": 0.25, "height": 0.02}},
    "date_of_birth":    {"value": "03/12/1999", "confidence": 0.98, "bbox": {"x": 0.096, "y": 0.194, "width": 0.25, "height": 0.02}},
    "group_number":     {"value": "GRP-1057", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.194, "width": 0.25, "height": 0.02}},
    "plan":             {"value": "PLN-PPO-GOLD", "confidence": 0.97, "bbox": {"x": 0.096, "y": 0.242, "width": 0.25, "height": 0.02}},
    "provider_name":    {"value": "Johnson Specialty Clinic", "confidence": 0.97, "bbox": {"x": 0.096, "y": 0.343, "width": 0.35, "height": 0.02}},
    "provider_npi":     {"value": "9040691698", "confidence": 0.96, "bbox": {"x": 0.51, "y": 0.343, "width": 0.25, "height": 0.02}},
    "license_state":    {"value": "IN", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.39, "width": 0.1, "height": 0.02}},
    "procedure_code":   {"value": "70553", "confidence": 0.98, "bbox": {"x": 0.096, "y": 0.487, "width": 0.15, "height": 0.02}},
    "date_of_service":  {"value": "08/14/2026", "confidence": 0.98, "bbox": {"x": 0.51, "y": 0.487, "width": 0.25, "height": 0.02}},
    "units_requested":  {"value": "1", "confidence": 0.98, "bbox": {"x": 0.51, "y": 0.533, "width": 0.1, "height": 0.02}},
    "diagnosis_code":   {"value": "G43.909", "confidence": 0.97, "bbox": {"x": 0.096, "y": 0.579, "width": 0.15, "height": 0.02}}
  },
  "clinical_narrative": "Patient with persistent symptoms unresponsive to initial management. Conservative treatment including physical therapy and anti-inflammatory medication has been completed without adequate improvement. Examination and prior imaging support the requested service. Referred for further evaluation and management.",
  "notes": [
    "Form is clean and legible; no illegible characters were encountered.",
    "Signature line reads 'Johnson Specialty Clinic' rather than an individual provider's name."
  ]
}
```
```
</details>

### Step 2 — resolve entities (deterministic)

*Transcribed strings matched onto real records. No model.*

```text
member   MBR-100118  (match confidence 1.00)
provider 9040691698
procedure 70553   diagnosis G43.909
date of service 2026-08-14
```

### Step 3 — evaluate 9 rules (deterministic)

*Pure functions over the payer records. No model.*

```text
[R1] PASS     CPT 70553 requires prior authorization.
          evidence: procedure_code=70553, requires_preauth=true
[R2] PASS     Coverage active on 08/14/2026.
          evidence: member_id=MBR-100118, status=active, effective_date=2025-10-18, date_of_service=2026-08-14
[R3] n/a      Meridian PPO Gold carries no waiting period.
          evidence: plan_id=PLN-PPO-GOLD, waiting_period_days=0
[R4] PASS     Advanced Imaging is a covered category under Meridian PPO Gold.
          evidence: plan_id=PLN-PPO-GOLD, procedure_code=70553, category=advanced_imaging, excluded_categories=cosmetic
[R5] PASS     Provider state IN is within the plan service area.
          evidence: plan_id=PLN-PPO-GOLD, provider_npi=9040691698, provider_state=IN, covered_states=OH, MI, IN, KY, PA, WV
[R6] PASS     Provider is contracted, licensed through 06/30/2027, and in good standing.
          evidence: provider_npi=9040691698, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=false
[R7] PASS     9600.00 remains in the imaging benefit against a request of 2180.00.
          evidence: category=imaging, plan_year=2026, limit_amount=12000.00, consumed_amount=2400.00, remaining=9600.00, requested_amount=2180.00
[R8] FAIL     Authorization AUTH-CASE-021 is already active for this member and procedure, valid 07/25/2026 through 09/23/2026. The existing authorization should be used.
          evidence: existing_auth_id=AUTH-CASE-021, valid_from=2026-07-25, valid_to=2026-09-23, units_approved=1
[R9] PASS     Diagnosis G43.909 supports CPT 70553.
          evidence: procedure_code=70553, submitted_diagnoses=G43.909, supporting_diagnoses=G43.909, R51.9, G93.1
```

## Final determination

**denied** — Authorization AUTH-CASE-021 is already active for this member and procedure, valid 07/25/2026 through 09/23/2026. The existing authorization should be used.

---

_Replayed from the committed response cache 2026-08-30 10:07 UTC. No live model calls._