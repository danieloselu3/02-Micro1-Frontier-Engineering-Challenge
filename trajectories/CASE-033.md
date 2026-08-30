# CASE-033 — necessity_no_evidence

> The documentation is silent on a criterion, so it pends for the missing note rather than denying.

## Outcome

| | |
|---|---|
| Produced | **pended** citing `MP-IMG-001#1` |
| Gold label | **pended** citing `MP-IMG-001` |
| Correct | yes |
| Routed to a clinician | yes |
| Model calls | 3 |
| Cost | $0.069445 |
| Document condition | clean |

**Why a human was required**

- Requests for additional information are confirmed by a reviewer.
- Necessity confidence 0.75 is below the 0.80 threshold.
- The assessment flagged 3 point(s) of uncertainty.
- Verification found 1 unsupported claim(s) in the rationale.

## Agent instructions

The system prompts are version-controlled and are not repeated here:

- `agents/intake_extractor/prompt.md`
- `agents/adjudicator/prompt.md`
- `agents/reviewer_critic/prompt.md`

## Trajectory

### Step 1 — `extract` (model)

*intake_extractor reads the page and reports per-field confidence*

`claude-sonnet-5` · 4373 in / 1130 out · 9.6s

<details><summary>Prompt sent</summary>

```text
[page image, 89 KB PNG — see the case document]

Transcribe this prior-authorization form. Return the JSON object described in your instructions and nothing else.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "fields": {
    "member_name":      {"value": "Mark Reese", "confidence": 0.98, "bbox": {"x": 0.11, "y": 0.148, "width": 0.30, "height": 0.02}},
    "member_id":        {"value": "MBR-100055", "confidence": 0.97, "bbox": {"x": 0.52, "y": 0.148, "width": 0.25, "height": 0.02}},
    "date_of_birth":    {"value": "07/06/1961", "confidence": 0.97, "bbox": {"x": 0.11, "y": 0.199, "width": 0.25, "height": 0.02}},
    "group_number":     {"value": "GRP-1045", "confidence": 0.97, "bbox": {"x": 0.52, "y": 0.199, "width": 0.25, "height": 0.02}},
    "plan":             {"value": "PLN-EPO-VALUE", "confidence": 0.97, "bbox": {"x": 0.11, "y": 0.25, "width": 0.30, "height": 0.02}},
    "provider_name":    {"value": "Johnson Specialty Clinic", "confidence": 0.97, "bbox": {"x": 0.11, "y": 0.328, "width": 0.35, "height": 0.02}},
    "provider_npi":     {"value": "9130899871", "confidence": 0.95, "bbox": {"x": 0.52, "y": 0.328, "width": 0.25, "height": 0.02}},
    "license_state":    {"value": "MI", "confidence": 0.95, "bbox": {"x": 0.52, "y": 0.378, "width": 0.10, "height": 0.02}},
    "procedure_code":   {"value": "72148", "confidence": 0.99, "bbox": {"x": 0.11, "y": 0.457, "width": 0.15, "height": 0.02}},
    "date_of_service":  {"value": "08/14/2026", "confidence": 0.97, "bbox": {"x": 0.52, "y": 0.457, "width": 0.25, "height": 0.02}},
    "units_requested":  {"value": "1", "confidence": 0.97, "bbox": {"x": 0.52, "y": 0.507, "width": 0.05, "height": 0.02}},
    "diagnosis_code":   {"value": "M54.16", "confidence": 0.97, "bbox": {"x": 0.11, "y": 0.557, "width": 0.15, "height": 0.02}}
  },
  "clinical_narrative": "65-year-old with ongoing low back pain radiating into the right leg. Symptoms have been present for several months and continue to limit daily activity.\n\nExamination shows reduced sensation in the right L5 distribution and a positive straight leg raise on the right at approximately 45 degrees.\n\nPlain films of the lumbar spine were obtained on 07/22/2026 and show mild degenerative change at L4-L5 and L5-S1.\n\nRequesting MRI lumbar spine to further evaluate.",
  "notes": [
    "Document is a clean, high-legibility digital form; all fields are clearly printed with no visible scan artifacts or handwriting.",
    "Signature line reads 'Johnson Specialty Clinic' rather than an individual provider's name."
  ]
}
```
```
</details>

### Step 2 — resolve entities (deterministic)

*Transcribed strings matched onto real records. No model.*

```text
member   MBR-100055  (match confidence 1.00)
provider 9130899871
procedure 72148   diagnosis M54.16
date of service 2026-08-14
```

### Step 3 — evaluate 9 rules (deterministic)

*Pure functions over the payer records. No model.*

```text
[R1] PASS     CPT 72148 requires prior authorization.
          evidence: procedure_code=72148, requires_preauth=true
[R2] PASS     Coverage active on 08/14/2026.
          evidence: member_id=MBR-100055, status=active, effective_date=2025-09-18, date_of_service=2026-08-14
[R3] PASS     Waiting period satisfied 10/18/2025.
          evidence: plan_id=PLN-EPO-VALUE, waiting_period_days=30, enrolled_at=2025-09-18, days_elapsed=330, satisfied_on=2025-10-18
[R4] PASS     Advanced Imaging is a covered category under Meridian EPO Value.
          evidence: plan_id=PLN-EPO-VALUE, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic, specialty_drug
[R5] PASS     Provider state MI is within the plan service area.
          evidence: plan_id=PLN-EPO-VALUE, provider_npi=9130899871, provider_state=MI, covered_states=OH, MI
[R6] PASS     Provider is contracted, licensed through 06/30/2027, and in good standing.
          evidence: provider_npi=9130899871, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=true
[R7] PASS     2900.00 remains in the imaging benefit against a request of 1450.00.
          evidence: category=imaging, plan_year=2026, limit_amount=4000.00, consumed_amount=1100.00, remaining=2900.00, requested_amount=1450.00
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

`claude-sonnet-5` · 3144 in / 1777 out · 16.3s

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

65-year-old with ongoing low back pain radiating into the right leg. Symptoms have been present for several months and continue to limit daily activity.

Examination shows reduced sensation in the right L5 distribution and a positive straight leg raise on the right at approximately 45 degrees.

Plain films of the lumbar spine were obtained on 07/22/2026 and show mild degenerative change at L4-L5 and L5-S1.

Requesting MRI lumbar spine to further evaluate.

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
      "criterion_text": "Documented trial of conservative therapy of at least six weeks within the past 12 months, with duration and outcome stated.",
      "status": "no_evidence",
      "rationale": "The narrative describes ongoing symptoms for several months but never mentions physical therapy, NSAIDs, activity modification, or a home exercise program, nor any duration or outcome of such a trial.",
      "narrative_support": null
    },
    {
      "clause_id": "MP-IMG-001#2",
      "criterion_text": "Objective exam finding of dermatomal sensory loss, asymmetric reflex loss, myotomal weakness, or positive SLR reproducing radicular symptoms below the knee.",
      "status": "met",
      "rationale": "Exam documents sensory loss in a specific dermatomal distribution, which independently satisfies this criterion regardless of how the SLR finding is interpreted.",
      "narrative_support": "reduced sensation in the right L5 distribution"
    },
    {
      "clause_id": "MP-IMG-001#3",
      "criterion_text": "Plain radiographs of the lumbar spine performed and interpreted prior to the request, with report available.",
      "status": "met",
      "rationale": "Plain films were obtained and interpreted, showing mild degenerative changes, and there is nothing indicating this predates the request by more than 12 months.",
      "narrative_support": "Plain films of the lumbar spine were obtained on 07/22/2026 and show mild degenerative change at L4-L5 and L5-S1."
    },
    {
      "clause_id": "MP-IMG-001#4",
      "criterion_text": "Record identifies how the MRI result will change management (e.g., surgical/pain management consult contingent on findings).",
      "status": "no_evidence",
      "rationale": "The request states only that imaging is 'to further evaluate,' with no mention of a pending surgical, neurosurgical, or interventional pain consult contingent on the result.",
      "narrative_support": null
    },
    {
      "clause_id": "MP-IMG-001#5",
      "criterion_text": "Red-flag exception (cauda equina, progressive/severe deficit, infection, malignancy, trauma with osteoporosis/steroids) waiving criteria 1-4.",
      "status": "no_evidence",
      "rationale": "No red-flag symptoms such as saddle anesthesia, bowel/bladder dysfunction, bilateral weakness, fever, weight loss, or trauma are documented, which is the expected, ordinary case.",
      "narrative_support": null
    }
  ],
  "summary": "Objective findings (dermatomal sensory loss) and prior plain radiography are documented and support criteria 2 and 3. Conservative therapy trial and the anticipated impact on management are not addressed at all in the record, so those should be requested from the provider rather than treated as failures. No red flags are documented, which is the ordinary case.",
  "confidence": 0.75,
  "uncertainties": [
    "The positive straight leg raise is noted at 45 degrees but the narrative doesn't state whether it reproduced radicular pain below the knee — this doesn't change the outcome since sensory loss alone satisfies criterion 2, but it's worth flagging for completeness.",
    "No documentation of conservative therapy (PT, NSAIDs, activity modification) is present — this may simply be missing from the submission rather than reflecting that no such therapy occurred; recommend requesting those records before making a final determination.",
    "No exact request date is given, so I assumed the 07/22/2026 x-ray predates the request within the required window; if the request date is materially later, this should be rechecked."
  ]
}
```
```
</details>

### Step 6 — `verify` (model)

*reviewer_critic audits the drafted rationale against the evidence supplied*

`claude-haiku-4-5-20251001` · 2394 in / 179 out · 2.5s

<details><summary>Prompt sent</summary>

```text
## Draft rationale under audit

The record does not address 2 of the 5 criteria in MP-IMG-001. Nothing in the documentation contradicts them, so the request is returned for the missing information rather than denied.

## Deterministic rule results and the record values they read

[R1] Authorization required: PASS
    CPT 72148 requires prior authorization.
    evidence: procedure_code=72148, requires_preauth=true
[R2] Member eligibility: PASS
    Coverage active on 08/14/2026.
    evidence: member_id=MBR-100055, status=active, effective_date=2025-09-18, date_of_service=2026-08-14
[R3] Waiting period: PASS
    Waiting period satisfied 10/18/2025.
    evidence: plan_id=PLN-EPO-VALUE, waiting_period_days=30, enrolled_at=2025-09-18, days_elapsed=330, satisfied_on=2025-10-18
[R4] Benefit coverage: PASS
    Advanced Imaging is a covered category under Meridian EPO Value.
    evidence: plan_id=PLN-EPO-VALUE, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic, specialty_drug
[R5] Area of cover: PASS
    Provider state MI is within the plan service area.
    evidence: plan_id=PLN-EPO-VALUE, provider_npi=9130899871, provider_state=MI, covered_states=OH, MI
[R6] Provider standing: PASS
    Provider is contracted, licensed through 06/30/2027, and in good standing.
    evidence: provider_npi=9130899871, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=true
[R7] Benefit limits: PASS
    2900.00 remains in the imaging benefit against a request of 1450.00.
    evidence: category=imaging, plan_year=2026, limit_amount=4000.00, consumed_amount=1100.00, remaining=2900.00, requested_amount=1450.00
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

[MP-IMG-001#1] NO_EVIDENCE -- The narrative describes ongoing symptoms for several months but never mentions physical therapy, NSAIDs, activity modification, or a home exercise program, nor any duration or outcome of such a trial.
[MP-IMG-001#2] MET -- Exam documents sensory loss in a specific dermatomal distribution, which independently satisfies this criterion regardless of how the SLR finding is interpreted.
[MP-IMG-001#3] MET -- Plain films were obtained and interpreted, showing mild degenerative changes, and there is nothing indicating this predates the request by more than 12 months.
[MP-IMG-001#4] NO_EVIDENCE -- The request states only that imaging is 'to further evaluate,' with no mention of a pending surgical, neurosurgical, or interventional pain consult contingent on the result.
[MP-IMG-001#5] NO_EVIDENCE -- No red-flag symptoms such as saddle anesthesia, bowel/bladder dysfunction, bilateral weakness, fever, weight loss, or trauma are documented, which is the expected, ordinary case.

## Clinical narrative as submitted

65-year-old with ongoing low back pain radiating into the right leg. Symptoms have been present for several months and continue to limit daily

… truncated, 453 more characters
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "findings": [
    {
      "severity": "blocking",
      "claim": "The record does not address 2 of the 5 criteria in MP-IMG-001.",
      "problem": "The medical necessity assessment marks criterion 5 as NO_EVIDENCE, but MP-IMG-001#5 explicitly states 'This clause is an exception, not a requirement. Most requests will not document a red flag, and their absence is the ordinary case rather than a gap in the documentation.' The absence of red flags is not a criterion gap; it is the expected ordinary case. Only 2 criteria are actually unaddressed: #1 and #4. Criterion #5's absence does not count as a missing criterion."
    }
  ]
}
```
```
</details>

## Final determination

**pended** — The record does not address 2 of the 5 criteria in MP-IMG-001. Nothing in the documentation contradicts them, so the request is returned for the missing information rather than denied.

Information requested:

- Documented trial of conservative therapy of at least six weeks within the past 12 months, with duration and outcome stated.
- Record identifies how the MRI result will change management (e.g., surgical/pain management consult contingent on findings).

---

_Replayed from the committed response cache 2026-08-30 10:07 UTC. No live model calls._