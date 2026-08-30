# CASE-025 — necessity_met

> Full path — every rule passes and the criteria are met, then the case is escalated on the model's own stated uncertainty.

## Outcome

| | |
|---|---|
| Produced | **approved** citing `MP-IMG-001` |
| Gold label | **approved** citing `MP-IMG-001` |
| Correct | yes |
| Routed to a clinician | yes |
| Model calls | 3 |
| Cost | $0.071115 |
| Document condition | clean |

**Why a human was required**

- The assessment flagged 1 point(s) of uncertainty.

## Agent instructions

The system prompts are version-controlled and are not repeated here:

- `agents/intake_extractor/prompt.md`
- `agents/adjudicator/prompt.md`
- `agents/reviewer_critic/prompt.md`

## Trajectory

### Step 1 — `extract` (model)

*intake_extractor reads the page and reports per-field confidence*

`claude-sonnet-5` · 4373 in / 1355 out · 11.5s

<details><summary>Prompt sent</summary>

```text
[page image, 111 KB PNG — see the case document]

Transcribe this prior-authorization form. Return the JSON object described in your instructions and nothing else.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "fields": {
    "member_name": {"value": "William Miller", "confidence": 0.98, "bbox": {"x": 0.09, "y": 0.148, "width": 0.35, "height": 0.02}},
    "member_id": {"value": "MBR-100095", "confidence": 0.97, "bbox": {"x": 0.53, "y": 0.148, "width": 0.28, "height": 0.02}},
    "date_of_birth": {"value": "01/23/1968", "confidence": 0.98, "bbox": {"x": 0.09, "y": 0.197, "width": 0.28, "height": 0.02}},
    "group_number": {"value": "GRP-1009", "confidence": 0.97, "bbox": {"x": 0.53, "y": 0.197, "width": 0.28, "height": 0.02}},
    "plan": {"value": "PLN-PPO-GOLD", "confidence": 0.97, "bbox": {"x": 0.09, "y": 0.238, "width": 0.28, "height": 0.02}},
    "provider_name": {"value": "Taylor Imaging Partners", "confidence": 0.97, "bbox": {"x": 0.09, "y": 0.317, "width": 0.35, "height": 0.02}},
    "provider_npi": {"value": "9155886571", "confidence": 0.96, "bbox": {"x": 0.53, "y": 0.317, "width": 0.28, "height": 0.02}},
    "license_state": {"value": "MI", "confidence": 0.96, "bbox": {"x": 0.53, "y": 0.362, "width": 0.15, "height": 0.02}},
    "procedure_code": {"value": "72148", "confidence": 0.99, "bbox": {"x": 0.09, "y": 0.437, "width": 0.15, "height": 0.02}},
    "date_of_service": {"value": "08/14/2026", "confidence": 0.98, "bbox": {"x": 0.53, "y": 0.437, "width": 0.2, "height": 0.02}},
    "units_requested": {"value": "1", "confidence": 0.98, "bbox": {"x": 0.53, "y": 0.482, "width": 0.1, "height": 0.02}},
    "diagnosis_code": {"value": "M54.16", "confidence": 0.98, "bbox": {"x": 0.09, "y": 0.528, "width": 0.15, "height": 0.02}}
  },
  "clinical_narrative": "58-year-old presenting with axial low back pain radiating into the left lower extremity, onset approximately four months ago after a lifting injury at work. Pain is rated 7/10 and worse with sitting and forward flexion.\n\nConservative management: completed 8 weeks of supervised physical therapy (24 visits, 06/02/2026 through 07/28/2026) with documented adherence, plus a scheduled course of meloxicam 15 mg daily and a two-week trial of cyclobenzaprine. Symptoms have not improved; the patient reports no meaningful change in functional capacity.\n\nNeurologic examination: diminished left patellar reflex (1+ compared with 2+ on the right), decreased sensation in the L4 dermatome, and 4/5 strength on left ankle dorsiflexion. Straight leg raise positive at 40 degrees on the left.\n\nPlain radiographs of the lumbar spine (2 views, 07/30/2026) demonstrate disc space narrowing at L4-L5 without acute fracture or spondylolisthesis.\n\nThe patient has been referred for neurosurgical consultation and MRI is required to determine whether a surgical decompression is indicated.",
  "notes": [
    "Document is clear and legible overall; no significant scan degradation observed.",
    "Diagnosis description field ('Radiculopathy, lumbar region') is not in the required output schema but is present on the form.",
    "State of Residence field present on form but not part of required schema."
  ]
}
```
```
</details>

### Step 2 — resolve entities (deterministic)

*Transcribed strings matched onto real records. No model.*

```text
member   MBR-100095  (match confidence 1.00)
provider 9155886571
procedure 72148   diagnosis M54.16
date of service 2026-08-14
```

### Step 3 — evaluate 9 rules (deterministic)

*Pure functions over the payer records. No model.*

```text
[R1] PASS     CPT 72148 requires prior authorization.
          evidence: procedure_code=72148, requires_preauth=true
[R2] PASS     Coverage active on 08/14/2026.
          evidence: member_id=MBR-100095, status=active, effective_date=2025-10-18, date_of_service=2026-08-14
[R3] n/a      Meridian PPO Gold carries no waiting period.
          evidence: plan_id=PLN-PPO-GOLD, waiting_period_days=0
[R4] PASS     Advanced Imaging is a covered category under Meridian PPO Gold.
          evidence: plan_id=PLN-PPO-GOLD, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic
[R5] PASS     Provider state MI is within the plan service area.
          evidence: plan_id=PLN-PPO-GOLD, provider_npi=9155886571, provider_state=MI, covered_states=OH, MI, IN, KY, PA, WV
[R6] PASS     Provider is contracted, licensed through 06/30/2027, and in good standing.
          evidence: provider_npi=9155886571, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=false
[R7] PASS     4800.00 remains in the imaging benefit against a request of 1450.00.
          evidence: category=imaging, plan_year=2026, limit_amount=12000.00, consumed_amount=7200.00, remaining=4800.00, requested_amount=1450.00
[R8] PASS     No active authorization covers this procedure and date.
          evidence: prior_auths_checked=0
[R9] PASS     Diagnosis M54.16 supports CPT 72148.
          evidence: procedure_code=72148, submitted_diagnoses=M54.16, supporting_diagnoses=M54.50, M54.51, M51.26, M54.16
```

### Step 4 — retrieve criteria (deterministic)

*5 assessable clauses from MP-IMG-001, selected by procedure code rather than similarity search.*

```text
[MP-IMG-001#1] criterion
[MP-IMG-001#2] criterion
[MP-IMG-001#3] criterion
[MP-IMG-001#4] criterion
[MP-IMG-001#5] exception
```

### Step 5 — `adjudicate` (model)

*adjudicator judges the clinical narrative against the retrieved criteria*

`claude-sonnet-5` · 3372 in / 1661 out · 15.1s

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

58-year-old presenting with axial low back pain radiating into the left lower extremity, onset approximately four months ago after a lifting injury at work. Pain is rated 7/10 and worse with sitting and forward flexion.

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
      "criterion_text": "Documented conservative therapy trial of at least 6 weeks within the past 12 months, with duration and outcome stated.",
      "status": "met",
      "rationale": "PT trial of 8 weeks with documented adherence, plus medication trials, exceeds the 6-week threshold and the outcome (no improvement) is explicitly stated.",
      "narrative_support": "completed 8 weeks of supervised physical therapy (24 visits, 06/02/2026 through 07/28/2026) with documented adherence, plus a scheduled course of meloxicam 15 mg daily and a two-week trial of cyclobenzaprine. Symptoms have not improved; the patient reports no meaningful change in functional capacity."
    },
    {
      "clause_id": "MP-IMG-001#2",
      "criterion_text": "Objective exam finding of asymmetric reflex loss, dermatomal sensory loss, myotomal weakness ≤4/5, or positive SLR reproducing radicular symptoms below the knee.",
      "status": "met",
      "rationale": "Exam documents multiple qualifying findings — asymmetric reflex, dermatomal sensory loss, and 4/5 motor weakness — any one of which satisfies this criterion.",
      "narrative_support": "diminished left patellar reflex (1+ compared with 2+ on the right), decreased sensation in the L4 dermatome, and 4/5 strength on left ankle dorsiflexion."
    },
    {
      "clause_id": "MP-IMG-001#3",
      "criterion_text": "Plain lumbar radiographs performed and interpreted prior to the request, report available.",
      "status": "met",
      "rationale": "Radiographs were taken shortly before the request with findings documented and available.",
      "narrative_support": "Plain radiographs of the lumbar spine (2 views, 07/30/2026) demonstrate disc space narrowing at L4-L5 without acute fracture or spondylolisthesis."
    },
    {
      "clause_id": "MP-IMG-001#4",
      "criterion_text": "Record identifies how imaging will change management (e.g., pending surgical consult).",
      "status": "met",
      "rationale": "The record ties the MRI directly to a pending neurosurgical consultation and decision about surgical decompression, which is an accepted management-impact statement.",
      "narrative_support": "The patient has been referred for neurosurgical consultation and MRI is required to determine whether a surgical decompression is indicated."
    },
    {
      "clause_id": "MP-IMG-001#5",
      "criterion_text": "Red-flag exception waiving criteria 1-4 if cauda equina, progressive/severe deficit, infection, malignancy, or trauma-with-osteoporosis is documented.",
      "status": "no_evidence",
      "rationale": "No red-flag findings (bowel/bladder dysfunction, bilateral weakness, infection or malignancy signs, trauma with osteoporosis) are documented; this is the expected ordinary case, not a deficiency.",
      "narrative_support": null
    }
  ],
  "summary": "All four core requirements are affirmatively supported: adequate conservative therapy trial with stated outcome, objective radicular findings on exam, prior plain films, and a clear management-impact statement tied to neurosurgical consultation. No red-flag exception applies, which is expected and does not affect the assessment.",
  "confidence": 0.92,
  "uncertainties": [
    "The straight leg raise is described as positive at 40 degrees but the narrative doesn't explicitly state it reproduced symptoms below the knee — I inferred this met the criterion based on the overall constellation of findings, but a stricter reviewer might want that phrase explicit."
  ]
}
```
```
</details>

### Step 6 — `verify` (model)

*reviewer_critic audits the drafted rationale against the evidence supplied*

`claude-haiku-4-5-20251001` · 2555 in / 17 out · 1.1s

<details><summary>Prompt sent</summary>

```text
## Draft rationale under audit

All 5 criteria in MP-IMG-001 are documented. All four core requirements are affirmatively supported: adequate conservative therapy trial with stated outcome, objective radicular findings on exam, prior plain films, and a clear management-impact statement tied to neurosurgical consultation. No red-flag exception applies, which is expected and does not affect the assessment.

## Deterministic rule results and the record values they read

[R1] Authorization required: PASS
    CPT 72148 requires prior authorization.
    evidence: procedure_code=72148, requires_preauth=true
[R2] Member eligibility: PASS
    Coverage active on 08/14/2026.
    evidence: member_id=MBR-100095, status=active, effective_date=2025-10-18, date_of_service=2026-08-14
[R3] Waiting period: NOT_APPLICABLE
    Meridian PPO Gold carries no waiting period.
    evidence: plan_id=PLN-PPO-GOLD, waiting_period_days=0
[R4] Benefit coverage: PASS
    Advanced Imaging is a covered category under Meridian PPO Gold.
    evidence: plan_id=PLN-PPO-GOLD, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic
[R5] Area of cover: PASS
    Provider state MI is within the plan service area.
    evidence: plan_id=PLN-PPO-GOLD, provider_npi=9155886571, provider_state=MI, covered_states=OH, MI, IN, KY, PA, WV
[R6] Provider standing: PASS
    Provider is contracted, licensed through 06/30/2027, and in good standing.
    evidence: provider_npi=9155886571, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=false
[R7] Benefit limits: PASS
    4800.00 remains in the imaging benefit against a request of 1450.00.
    evidence: category=imaging, plan_year=2026, limit_amount=12000.00, consumed_amount=7200.00, remaining=4800.00, requested_amount=1450.00
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

[MP-IMG-001#1] MET -- PT trial of 8 weeks with documented adherence, plus medication trials, exceeds the 6-week threshold and the outcome (no improvement) is explicitly stated.
[MP-IMG-001#2] MET -- Exam documents multiple qualifying findings — asymmetric reflex, dermatomal sensory loss, and 4/5 motor weakness — any one of which satisfies this criterion.
[MP-IMG-001#3] MET -- Radiographs were taken shortly before the request with findings documented and available.
[MP-IMG-001#4] MET -- The record ties the MRI directly to a pending neurosurgical consultation and decision about surgical decompression, which is an accepted management-impact statement.
[MP-IMG-001#5] NO_EVIDENCE -- No red-flag findings (bowel/bladder dysfunction, bilateral weakness, infection or malignancy signs, trauma with osteoporosis) are documented; this is the expected ordinary case, not a deficiency.

## Clinical narrative as submitted

58-year-old presenting with axial low back pain radiating into the left lower extremity, onset approximately four months ago after

… truncated, 1077 more characters
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

**approved** — All 5 criteria in MP-IMG-001 are documented. All four core requirements are affirmatively supported: adequate conservative therapy trial with stated outcome, objective radicular findings on exam, prior plain films, and a clear management-impact statement tied to neurosurgical consultation. No red-flag exception applies, which is expected and does not affect the assessment.

---

_Replayed from the committed response cache 2026-08-30 10:07 UTC. No live model calls._