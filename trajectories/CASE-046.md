# CASE-046 — illegible_member_id

> Handwritten member id. Extraction retries, still refuses to guess the smudged digit, and identity resolves on name and date of birth.

## Outcome

| | |
|---|---|
| Produced | **approved** citing `MP-IMG-001` |
| Gold label | **approved** citing `MP-IMG-001` |
| Correct | yes |
| Routed to a clinician | yes |
| Model calls | 4 |
| Cost | $0.110892 |
| Document condition | handwritten |

**Why a human was required**

- The assessment flagged 2 point(s) of uncertainty.
- Fields read below the confidence floor: member_id.

## Agent instructions

The system prompts are version-controlled and are not repeated here:

- `agents/intake_extractor/prompt.md`
- `agents/adjudicator/prompt.md`
- `agents/reviewer_critic/prompt.md`

## Trajectory

### Step 1 — `extract` (model)

*intake_extractor reads the page and reports per-field confidence*

`claude-sonnet-5` · 4479 in / 2197 out · 21.4s

<details><summary>Prompt sent</summary>

```text
[page image, 1113 KB PNG — see the case document]

Transcribe this prior-authorization form. Return the JSON object described in your instructions and nothing else.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "fields": {
    "member_name": {
      "value": "Cody Gallagher",
      "confidence": 0.98,
      "bbox": {"x": 0.09, "y": 0.183, "width": 0.30, "height": 0.02}
    },
    "member_id": {
      "value": "MBR-100?48",
      "confidence": 0.55,
      "bbox": {"x": 0.52, "y": 0.183, "width": 0.28, "height": 0.02}
    },
    "date_of_birth": {
      "value": "12/08/1964",
      "confidence": 0.97,
      "bbox": {"x": 0.09, "y": 0.235, "width": 0.25, "height": 0.02}
    },
    "group_number": {
      "value": "GRP-1066",
      "confidence": 0.96,
      "bbox": {"x": 0.52, "y": 0.235, "width": 0.25, "height": 0.02}
    },
    "plan": {
      "value": "PLN-PPO-GOLD",
      "confidence": 0.97,
      "bbox": {"x": 0.09, "y": 0.288, "width": 0.28, "height": 0.02}
    },
    "provider_name": {
      "value": "Baker Imaging Partners",
      "confidence": 0.96,
      "bbox": {"x": 0.09, "y": 0.375, "width": 0.35, "height": 0.02}
    },
    "provider_npi": {
      "value": "9954613207",
      "confidence": 0.96,
      "bbox": {"x": 0.52, "y": 0.375, "width": 0.28, "height": 0.02}
    },
    "license_state": {
      "value": "WV",
      "confidence": 0.95,
      "bbox": {"x": 0.52, "y": 0.425, "width": 0.15, "height": 0.02}
    },
    "procedure_code": {
      "value": "72148",
      "confidence": 0.99,
      "bbox": {"x": 0.09, "y": 0.51, "width": 0.2, "height": 0.02}
    },
    "date_of_service": {
      "value": "08/14/2026",
      "confidence": 0.97,
      "bbox": {"x": 0.52, "y": 0.51, "width": 0.25, "height": 0.02}
    },
    "units_requested": {
      "value": "1",
      "confidence": 0.98,
      "bbox": {"x": 0.52, "y": 0.56, "width": 0.1, "height": 0.02}
    },
    "diagnosis_code": {
      "value": "M54.16",
      "confidence": 0.98,
      "bbox": {"x": 0.09, "y": 0.61, "width": 0.2, "height": 0.02}
    }
  },
  "clinical_narrative": "61-year-old presenting with axial low back pain radiating into the left lower extremity, onset approximately four months ago after a lifting injury at work. Pain is rated 7/10 and worse with sitting and forward flexion.\n\nConservative management: completed 8 weeks of supervised physical therapy (24 visits, 06/02/2026 through 07/28/2026) with documented adherence, plus a scheduled course of meloxicam 15 mg daily and a two-week trial of cyclobenzaprine. Symptoms have not improved; the patient reports no meaningful change in functional capacity.\n\nNeurologic examination: diminished left patellar reflex (1+ compared with 2+ on the right), decreased sensation in the L4 dermatome, and 4/5 strength on left ankle dorsiflexion. Straight leg raise positive at 40 degrees on the left.\n\nPlain radiographs of the lumbar spine (2 views, 07/30/2026) demonstrate disc space narrowing at L4-L5 without acute fracture or spondylolisthesis.\n\nThe patient has been referred for neurosurgical consultation and MRI is required to determine whether a surgical decompression is indicated.",
  "notes": [
    "Member ID field appears handwritten/overwritten with overlapping strokes; one digit ('1' or possibly another character before '48') is uncertain and transcribed as '?'.",
    "Specialty field on form reads 'Family Medicine' though provider name is an imaging facility; transcribed as printed without correction.",
    "All other fields are clearly legible with no significant scan degradation noted."
  ]
}
```
```
</details>

### Step 2 — `extract_reread` (model)

*RETRY — fields below the confidence threshold are read again, on an enlarged image*

`claude-sonnet-5` · 6477 in / 353 out · 6.0s

<details><summary>Prompt sent</summary>

```text
[page image, 2358 KB PNG — see the case document]

A first pass over this form returned low confidence for the following fields:

- member_id

This image is enlarged. Read those fields again carefully. Return the same JSON structure, but include only the fields listed above. If a character is still unreadable, keep the '?' and the low confidence -- do not guess it.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "fields": {
    "member_id": {
      "value": "MBR-100?48",
      "confidence": 0.4,
      "bbox": {"x": 0.487, "y": 0.183, "width": 0.22, "height": 0.022}
    }
  }
}
```
```
</details>

### Step 3 — resolve entities (deterministic)

*Transcribed strings matched onto real records. No model.*

```text
member   MBR-100148  (match confidence 0.97)
provider 9954613207
procedure 72148   diagnosis M54.16
date of service 2026-08-14
```

### Step 4 — evaluate 9 rules (deterministic)

*Pure functions over the payer records. No model.*

```text
[R1] PASS     CPT 72148 requires prior authorization.
          evidence: procedure_code=72148, requires_preauth=true
[R2] PASS     Coverage active on 08/14/2026.
          evidence: member_id=MBR-100148, status=active, effective_date=2025-10-18, date_of_service=2026-08-14
[R3] n/a      Meridian PPO Gold carries no waiting period.
          evidence: plan_id=PLN-PPO-GOLD, waiting_period_days=0
[R4] PASS     Advanced Imaging is a covered category under Meridian PPO Gold.
          evidence: plan_id=PLN-PPO-GOLD, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic
[R5] PASS     Provider state WV is within the plan service area.
          evidence: plan_id=PLN-PPO-GOLD, provider_npi=9954613207, provider_state=WV, covered_states=OH, MI, IN, KY, PA, WV
[R6] PASS     Provider is contracted, licensed through 06/30/2027, and in good standing.
          evidence: provider_npi=9954613207, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=false
[R7] PASS     9600.00 remains in the imaging benefit against a request of 1450.00.
          evidence: category=imaging, plan_year=2026, limit_amount=12000.00, consumed_amount=2400.00, remaining=9600.00, requested_amount=1450.00
[R8] PASS     No active authorization covers this procedure and date.
          evidence: prior_auths_checked=0
[R9] PASS     Diagnosis M54.16 supports CPT 72148.
          evidence: procedure_code=72148, submitted_diagnoses=M54.16, supporting_diagnoses=M54.50, M54.51, M51.26, M54.16
```

### Step 5 — retrieve criteria (deterministic)

*5 assessable clauses from MP-IMG-001, selected by procedure code rather than similarity search.*

```text
[MP-IMG-001#1] criterion
[MP-IMG-001#2] criterion
[MP-IMG-001#3] criterion
[MP-IMG-001#4] criterion
[MP-IMG-001#5] exception
```

### Step 6 — `adjudicate` (model)

*adjudicator judges the clinical narrative against the retrieved criteria*

`claude-sonnet-5` · 3372 in / 1800 out · 16.0s

<details><summary>Prompt sent</summary>

```text
## Request

Procedure: CPT 72148 — MRI lumbar spine without contrast
Diagnosis: M54.16 — Radiculopathy, lumbar region

## Governing policy criteria

[MP-IMG-001#1] REQUIREMENT
Criterion 1 -- Failure of conservative management.
The record documents a trial of conservative therapy of at least six weeks
in duration, undertaken within the twelve months preceding the request.
Acceptable modalities include supervised physical therapy, a documented
course of non-steroidal anti-inflammatory medication, activity modification,
or a home exercise programme with recorded adherence. The record must state
the duration of the trial and its outcome. A statement that conservative
therapy was offered and declined does not satisfy this criterion.

[MP-IMG-001#2] REQUIREMENT
Criterion 2 -- Objective neurologic or radicular findings.
Physical examination documents at least one of the following: a diminished
or absent deep tendon reflex asymmetric to the contralateral side; sensory
loss in an identifiable dermatomal distribution; motor weakness of 4/5 or
less in a myotomal distribution; or a positive straight leg raise reproducing
radicular symptoms below the knee. Subjective report of radiating pain alone,
without a corroborating examination finding, does not satisfy this criterion.

[MP-IMG-001#3] REQUIREMENT
Criterion 3 -- Prior plain radiography.
Plain radiographs of the lumbar spine have been performed and interpreted
prior to the request, and the report is available. Radiographs performed more
than twelve months before the request do not satisfy this criterion unless
the clinical presentation is unchanged.

[MP-IMG-001#4] REQUIREMENT
Criterion 4 -- Impact on management.
The record identifies how the imaging result will alter management. Acceptable
statements include a pending surgical or neurosurgical consultation, planned
interventional pain management contingent on the result, or evaluation for a
procedure the member is otherwise a candidate for. Imaging requested solely
for reassurance, or to document a condition where management will not change,
does not satisfy this criterion.

[MP-IMG-001#5] EXCEPTION
Criterion 5 -- Red-flag exception.
Where any of the following is documented, criteria 1 through 4 are waived and
imaging is authorized without further review: suspected cauda equina syndrome
(saddle anaesthesia, new bowel or bladder dysfunction, bilateral leg
weakness); progressive or severe neurologic deficit; suspected spinal
infection (fever with intravenous drug use, recent spinal instrumentation, or
immunosuppression); suspected malignancy (known primary tumour, unexplained
weight loss, night pain unrelieved by position); or significant trauma in a
member with osteoporosis or on chronic corticosteroids.

This clause is an exception, not a requirement. Most requests will not
document a red flag, and their absence is the ordinary case rather than a gap
in the documentation.

## Clinical documentation as submitted

61-year-old presenting with axial low back pain radiating into the left lower extremity, onset approximately four months ago after a lifting injury at work. Pain is rated 7/10 and worse with sitting and forward flexion.

Conservative management: completed 8 weeks of supervised physical therapy (24 visits, 06/02/2026 through 07/28/2026) with documented adherence, plus a scheduled course of meloxicam 15 mg daily and a two-week trial of cyclobenzaprine. Symptoms have not improved; the patient reports no meaningful change in functional capacity.

Neurologic examination: diminished left patellar reflex (1+ compared with 2+ on the right), decreased sensation in the L4 dermatome, and 4/5 strength on left ankle dorsiflexion. Straight leg raise positive at 40 degrees on the left.

Plain radiographs of the lumbar spine (2 views, 07/30/2026) demonstrate disc space narrowing at L4-L5 without acute fracture or spondylolisthesis.

The patient has been referred for neurosurgical consultation and MRI is required to determine whether a surgical decompression is indicated.

## Task

Assess each criterion above against the documentation. Return the JSON object
described in your instructions and nothing else.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "assessments": [
    {
      "clause_id": "MP-IMG-001#1",
      "criterion_text": "Documented trial of conservative therapy ≥6 weeks within past 12 months, with stated duration and outcome.",
      "status": "met",
      "rationale": "PT course clearly exceeds the 6-week minimum, is within the past 12 months, includes documented adherence, and the outcome (no improvement) is stated.",
      "narrative_support": "completed 8 weeks of supervised physical therapy (24 visits, 06/02/2026 through 07/28/2026) with documented adherence, plus a scheduled course of meloxicam 15 mg daily and a two-week trial of cyclobenzaprine. Symptoms have not improved; the patient reports no meaningful change in functional capacity."
    },
    {
      "clause_id": "MP-IMG-001#2",
      "criterion_text": "Exam documents an objective neurologic/radicular finding (reflex asymmetry, dermatomal sensory loss, myotomal weakness ≤4/5, or positive SLR with radicular reproduction below knee).",
      "status": "met",
      "rationale": "Multiple qualifying findings are documented independently — asymmetric reflex, dermatomal sensory loss, and 4/5 myotomal weakness — any one of which satisfies this criterion.",
      "narrative_support": "diminished left patellar reflex (1+ compared with 2+ on the right), decreased sensation in the L4 dermatome, and 4/5 strength on left ankle dorsiflexion."
    },
    {
      "clause_id": "MP-IMG-001#3",
      "criterion_text": "Plain radiographs performed and interpreted prior to the MRI request, report available.",
      "status": "met",
      "rationale": "Radiographs were taken shortly before the request and findings are reported, satisfying the recency and availability requirement.",
      "narrative_support": "Plain radiographs of the lumbar spine (2 views, 07/30/2026) demonstrate disc space narrowing at L4-L5 without acute fracture or spondylolisthesis."
    },
    {
      "clause_id": "MP-IMG-001#4",
      "criterion_text": "Record identifies how imaging will change management (e.g., pending surgical/interventional consult).",
      "status": "met",
      "rationale": "The record ties the MRI directly to a pending neurosurgical decision about surgical decompression, which is an acceptable management-impact statement.",
      "narrative_support": "The patient has been referred for neurosurgical consultation and MRI is required to determine whether a surgical decompression is indicated."
    },
    {
      "clause_id": "MP-IMG-001#5",
      "criterion_text": "Red-flag exception waiving criteria 1-4 if cauda equina, progressive deficit, infection, malignancy, or trauma-in-osteoporosis is documented.",
      "status": "no_evidence",
      "rationale": "No red-flag findings (bowel/bladder dysfunction, saddle anesthesia, progressive deficit, infection, malignancy, or trauma with osteoporosis/steroids) are mentioned; this is the expected, non-exceptional case.",
      "narrative_support": null
    }
  ],
  "summary": "All four core requirements are clearly supported by the documentation: adequate conservative therapy with a stated poor outcome, solid objective neuro exam findings, recent plain films, and a stated management impact (neurosurgical decision-making). No red flags are documented, which is normal and does not affect the assessment.",
  "confidence": 0.9,
  "uncertainties": [
    "The straight-leg-raise finding does not explicitly state that it reproduced radicular symptoms below the knee, though this is immaterial since other exam findings independently satisfy Criterion 2.",
    "Exact request date isn't given, so the 12-month windows for PT and radiographs are inferred from the 2026 dates provided; if the request date is much later than 07/30/2026, recency could be revisited."
  ]
}
```
```
</details>

### Step 7 — `verify` (model)

*reviewer_critic audits the drafted rationale against the evidence supplied*

`claude-haiku-4-5-20251001` · 2573 in / 17 out · 1.0s

<details><summary>Prompt sent</summary>

```text
## Draft rationale under audit

All 5 criteria in MP-IMG-001 are documented. All four core requirements are clearly supported by the documentation: adequate conservative therapy with a stated poor outcome, solid objective neuro exam findings, recent plain films, and a stated management impact (neurosurgical decision-making). No red flags are documented, which is normal and does not affect the assessment.

## Deterministic rule results and the record values they read

[R1] Authorization required: PASS
    CPT 72148 requires prior authorization.
    evidence: procedure_code=72148, requires_preauth=true
[R2] Member eligibility: PASS
    Coverage active on 08/14/2026.
    evidence: member_id=MBR-100148, status=active, effective_date=2025-10-18, date_of_service=2026-08-14
[R3] Waiting period: NOT_APPLICABLE
    Meridian PPO Gold carries no waiting period.
    evidence: plan_id=PLN-PPO-GOLD, waiting_period_days=0
[R4] Benefit coverage: PASS
    Advanced Imaging is a covered category under Meridian PPO Gold.
    evidence: plan_id=PLN-PPO-GOLD, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic
[R5] Area of cover: PASS
    Provider state WV is within the plan service area.
    evidence: plan_id=PLN-PPO-GOLD, provider_npi=9954613207, provider_state=WV, covered_states=OH, MI, IN, KY, PA, WV
[R6] Provider standing: PASS
    Provider is contracted, licensed through 06/30/2027, and in good standing.
    evidence: provider_npi=9954613207, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=false
[R7] Benefit limits: PASS
    9600.00 remains in the imaging benefit against a request of 1450.00.
    evidence: category=imaging, plan_year=2026, limit_amount=12000.00, consumed_amount=2400.00, remaining=9600.00, requested_amount=1450.00
[R8] Duplicate authorization: PASS
    No active authorization covers this procedure and date.
    evidence: prior_auths_checked=0
[R9] Code coherence: PASS
    Diagnosis M54.16 supports CPT 72148.
    evidence: procedure_code=72148, submitted_diagnoses=M54.16, supporting_diagnoses=M54.50, M54.51, M51.26, M54.16

## Policy clauses that were retrieved

[MP-IMG-001#1]
Criterion 1 -- Failure of conservative management.
The record documents a trial of conservative therapy of at least six weeks
in duration, undertaken within the twelve months preceding the request.
Acceptable modalities include supervised physical therapy, a documented
course of non-steroidal anti-inflammatory medication, activity modification,
or a home exercise programme with recorded adherence. The record must state
the duration of the trial and its outcome. A statement that conservative
therapy was offered and declined does not satisfy this criterion.

[MP-IMG-001#2]
Criterion 2 -- Objective neurologic or radicular findings.
Physical examination documents at least one of the following: a diminished
or absent deep tendon reflex asymmetric to the contralateral side; sensory
loss in an identifiable dermatomal distribution; motor weakness of 4/5 or
less in a myotomal distribution; or a positive straight leg raise reproducing
radicular symptoms below the knee. Subjective report of radiating pain alone,
without a corroborating examination finding, does not satisfy this criterion.

[MP-IMG-001#3]
Criterion 3 -- Prior plain radiography.
Plain radiographs of the lumbar spine have been performed and interpreted
prior to the request, and the report is available. Radiographs performed more
than twelve months before the request do not satisfy this criterion unless
the clinical presentation is unchanged.

[MP-IMG-001#4]
Criterion 4 -- Impact on management.
The record identifies how the imaging result will alter management. Acceptable
statements include a pending surgical or neurosurgical consultation, planned
interventional pain management contingent on the result, or evaluation for a
procedure the member is otherwise a candidate for. Imaging requested solely
for reassurance, or to document a condition where management will not change,
does not satisfy this criterion.

[MP-IMG-001#5]
Criterion 5 -- Red-flag exception.
Where any of the following is documented, criteria 1 through 4 are waived and
imaging is authorized without further review: suspected cauda equina syndrome
(saddle anaesthesia, new bowel or bladder dysfunction, bilateral leg
weakness); progressive or severe neurologic deficit; suspected spinal
infection (fever with intravenous drug use, recent spinal instrumentation, or
immunosuppression); suspected malignancy (known primary tumour, unexplained
weight loss, night pain unrelieved by position); or significant trauma in a
member with osteoporosis or on chronic corticosteroids.

This clause is an exception, not a requirement. Most requests will not
document a red flag, and their absence is the ordinary case rather than a gap
in the documentation.

## Medical necessity assessment supplied

[MP-IMG-001#1] MET -- PT course clearly exceeds the 6-week minimum, is within the past 12 months, includes documented adherence, and the outcome (no improvement) is stated.
[MP-IMG-001#2] MET -- Multiple qualifying findings are documented independently — asymmetric reflex, dermatomal sensory loss, and 4/5 myotomal weakness — any one of which satisfies this criterion.
[MP-IMG-001#3] MET -- Radiographs were taken shortly before the request and findings are reported, satisfying the recency and availability requirement.
[MP-IMG-001#4] MET -- The record ties the MRI directly to a pending neurosurgical decision about surgical decompression, which is an acceptable management-impact statement.
[MP-IMG-001#5] NO_EVIDENCE -- No red-flag findings (bowel/bladder dysfunction, saddle anesthesia, progressive deficit, infection, malignancy, or trauma with osteoporosis/steroids) are mentioned; this is the expected, non-exceptional case.

## Clinical narrative as submitted

61-year-old presenting with axial low back pain radiating into the left lower e

… truncated, 1128 more characters
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "findings": []
}
```
```
</details>

## Final determination

**approved** — All 5 criteria in MP-IMG-001 are documented. All four core requirements are clearly supported by the documentation: adequate conservative therapy with a stated poor outcome, solid objective neuro exam findings, recent plain films, and a stated management impact (neurosurgical decision-making). No red flags are documented, which is normal and does not affect the assessment.

---

_Replayed from the committed response cache 2026-08-30 10:07 UTC. No live model calls._