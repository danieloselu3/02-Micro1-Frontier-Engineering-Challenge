# CASE-034 — necessity_no_evidence

> A case the system gets WRONG: denied where a pend was correct.

## Outcome

| | |
|---|---|
| Produced | **denied** citing `MP-IMG-001#4` |
| Gold label | **pended** citing `MP-IMG-001` |
| Correct | **NO** |
| Routed to a clinician | yes |
| Model calls | 3 |
| Cost | $0.072116 |
| Document condition | scan |

**Why a human was required**

- Denials are always reviewed by a clinician before they are issued.
- Necessity confidence 0.72 is below the 0.80 threshold.
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

`claude-sonnet-5` · 4479 in / 1128 out · 9.8s

<details><summary>Prompt sent</summary>

```text
[page image, 1036 KB PNG — see the case document]

Transcribe this prior-authorization form. Return the JSON object described in your instructions and nothing else.
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "fields": {
    "member_name": {"value": "Victoria Kline", "confidence": 0.98, "bbox": {"x": 0.11, "y": 0.165, "width": 0.28, "height": 0.02}},
    "member_id": {"value": "MBR-100155", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.165, "width": 0.22, "height": 0.02}},
    "date_of_birth": {"value": "02/05/1981", "confidence": 0.97, "bbox": {"x": 0.11, "y": 0.22, "width": 0.2, "height": 0.02}},
    "group_number": {"value": "GRP-1036", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.22, "width": 0.2, "height": 0.02}},
    "plan": {"value": "PLN-PPO-GOLD", "confidence": 0.97, "bbox": {"x": 0.11, "y": 0.278, "width": 0.25, "height": 0.02}},
    "provider_name": {"value": "Davies Orthopedic Associates", "confidence": 0.97, "bbox": {"x": 0.11, "y": 0.375, "width": 0.35, "height": 0.02}},
    "provider_npi": {"value": "9578041404", "confidence": 0.96, "bbox": {"x": 0.51, "y": 0.375, "width": 0.22, "height": 0.02}},
    "license_state": {"value": "KY", "confidence": 0.95, "bbox": {"x": 0.51, "y": 0.43, "width": 0.1, "height": 0.02}},
    "procedure_code": {"value": "72148", "confidence": 0.98, "bbox": {"x": 0.11, "y": 0.51, "width": 0.15, "height": 0.02}},
    "date_of_service": {"value": "08/14/2026", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.51, "width": 0.2, "height": 0.02}},
    "units_requested": {"value": "1", "confidence": 0.97, "bbox": {"x": 0.51, "y": 0.565, "width": 0.1, "height": 0.02}},
    "diagnosis_code": {"value": "M54.16", "confidence": 0.97, "bbox": {"x": 0.11, "y": 0.615, "width": 0.15, "height": 0.02}}
  },
  "clinical_narrative": "45-year-old with ongoing low back pain radiating into the right leg. Symptoms have been present for several months and continue to limit daily activity.\n\nExamination shows reduced sensation in the right L5 distribution and a positive straight leg raise on the right at approximately 45 degrees.\n\nPlain films of the lumbar spine were obtained on 07/22/2026 and show mild degenerative change at L4-L5 and L5-S1.\n\nRequesting MRI lumbar spine to further evaluate.",
  "notes": [
    "Document is a clean, legible scan with no significant image degradation.",
    "State of residence field (KY) present but not included in the standard field list; left out per schema.",
    "Signature line reads 'Davies Orthopedic Associates' rather than an individual provider's name."
  ]
}
```
```
</details>

### Step 2 — resolve entities (deterministic)

*Transcribed strings matched onto real records. No model.*

```text
member   MBR-100155  (match confidence 1.00)
provider 9578041404
procedure 72148   diagnosis M54.16
date of service 2026-08-14
```

### Step 3 — evaluate 9 rules (deterministic)

*Pure functions over the payer records. No model.*

```text
[R1] PASS     CPT 72148 requires prior authorization.
          evidence: procedure_code=72148, requires_preauth=true
[R2] PASS     Coverage active on 08/14/2026.
          evidence: member_id=MBR-100155, status=active, effective_date=2025-10-18, date_of_service=2026-08-14
[R3] n/a      Meridian PPO Gold carries no waiting period.
          evidence: plan_id=PLN-PPO-GOLD, waiting_period_days=0
[R4] PASS     Advanced Imaging is a covered category under Meridian PPO Gold.
          evidence: plan_id=PLN-PPO-GOLD, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic
[R5] PASS     Provider state KY is within the plan service area.
          evidence: plan_id=PLN-PPO-GOLD, provider_npi=9578041404, provider_state=KY, covered_states=OH, MI, IN, KY, PA, WV
[R6] PASS     Provider is contracted, licensed through 06/30/2027, and in good standing.
          evidence: provider_npi=9578041404, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=false
[R7] PASS     12000.00 remains in the imaging benefit against a request of 1450.00.
          evidence: category=imaging, plan_year=2026, limit_amount=12000.00, consumed_amount=0.00, remaining=12000.00, requested_amount=1450.00
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

`claude-sonnet-5` · 3144 in / 1941 out · 18.6s

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

45-year-old with ongoing low back pain radiating into the right leg. Symptoms have been present for several months and continue to limit daily activity.

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
{
  "assessments": [
    {
      "clause_id": "MP-IMG-001#1",
      "criterion_text": "Documented six-week trial of conservative therapy within the past 12 months, with duration and outcome stated.",
      "status": "no_evidence",
      "rationale": "The narrative never mentions physical therapy, NSAIDs, activity modification, or a home exercise program. Nothing to indicate this was tried or declined.",
      "narrative_support": null
    },
    {
      "clause_id": "MP-IMG-001#2",
      "criterion_text": "Objective exam finding: asymmetric reflex loss, dermatomal sensory loss, myotomal weakness, or positive SLR reproducing radicular symptoms below the knee.",
      "status": "met",
      "rationale": "Exam documents sensory loss in a specific dermatome (L5), which independently satisfies this criterion.",
      "narrative_support": "Examination shows reduced sensation in the right L5 distribution"
    },
    {
      "clause_id": "MP-IMG-001#3",
      "criterion_text": "Plain lumbar radiographs performed and interpreted prior to the request, report available.",
      "status": "met",
      "rationale": "Plain films were obtained and a reading is documented; no indication they predate the request by more than 12 months.",
      "narrative_support": "Plain films of the lumbar spine were obtained on 07/22/2026 and show mild degenerative change at L4-L5 and L5-S1."
    },
    {
      "clause_id": "MP-IMG-001#4",
      "criterion_text": "Record identifies how the MRI result will change management (e.g., surgical/interventional referral pending result).",
      "status": "unmet",
      "rationale": "The only stated purpose is 'to further evaluate,' which the policy explicitly treats as insufficient — there is no pending surgical, neurosurgical, or interventional plan tied to the result.",
      "narrative_support": "Requesting MRI lumbar spine to further evaluate."
    },
    {
      "clause_id": "MP-IMG-001#5",
      "criterion_text": "Red-flag exception (cauda equina, progressive deficit, infection, malignancy, trauma with osteoporosis/steroids) waiving criteria 1-4.",
      "status": "no_evidence",
      "rationale": "No red-flag features are mentioned; this is the expected, ordinary scenario, not a documentation gap.",
      "narrative_support": null
    }
  ],
  "summary": "Exam findings (L5 sensory loss) support the objective-deficit criterion, and imaging/x-ray criterion is met. Conservative therapy is completely undocumented, and the stated reason for MRI ('to further evaluate') is exactly the vague purpose the policy excludes — management impact is unmet. No red flags are present, which is normal. Recommend requesting conservative-care documentation and a clearer management-impact statement before proceeding.",
  "confidence": 0.72,
  "uncertainties": [
    "No documentation at all addresses conservative therapy — need to confirm with provider whether it was tried, and if so for how long, before treating this as a hard denial versus a paperwork gap.",
    "The straight-leg-raise result doesn't state whether it reproduced pain below the knee, so I relied on the sensory-loss finding alone to satisfy criterion 2 — worth confirming SLR quality if the sensory finding is later questioned.",
    "No explicit request date is given, so I assumed the July 2026 x-ray predates the request within the 12-month window; if the request date is materially later, criterion 3 should be re-checked."
  ]
}
```
</details>

### Step 6 — `verify` (model)

*reviewer_critic audits the drafted rationale against the evidence supplied*

`claude-haiku-4-5-20251001` · 2352 in / 172 out · 3.0s

<details><summary>Prompt sent</summary>

```text
## Draft rationale under audit

The documentation does not meet 1 of the 5 criteria in MP-IMG-001. The only stated purpose is 'to further evaluate,' which the policy explicitly treats as insufficient — there is no pending surgical, neurosurgical, or interventional plan tied to the result.

## Deterministic rule results and the record values they read

[R1] Authorization required: PASS
    CPT 72148 requires prior authorization.
    evidence: procedure_code=72148, requires_preauth=true
[R2] Member eligibility: PASS
    Coverage active on 08/14/2026.
    evidence: member_id=MBR-100155, status=active, effective_date=2025-10-18, date_of_service=2026-08-14
[R3] Waiting period: NOT_APPLICABLE
    Meridian PPO Gold carries no waiting period.
    evidence: plan_id=PLN-PPO-GOLD, waiting_period_days=0
[R4] Benefit coverage: PASS
    Advanced Imaging is a covered category under Meridian PPO Gold.
    evidence: plan_id=PLN-PPO-GOLD, procedure_code=72148, category=advanced_imaging, excluded_categories=cosmetic
[R5] Area of cover: PASS
    Provider state KY is within the plan service area.
    evidence: plan_id=PLN-PPO-GOLD, provider_npi=9578041404, provider_state=KY, covered_states=OH, MI, IN, KY, PA, WV
[R6] Provider standing: PASS
    Provider is contracted, licensed through 06/30/2027, and in good standing.
    evidence: provider_npi=9578041404, network_tier=in_network, license_expiry=2027-06-30, sanctioned=false, contract_start=2023-01-01, plan_requires_in_network=false
[R7] Benefit limits: PASS
    12000.00 remains in the imaging benefit against a request of 1450.00.
    evidence: category=imaging, plan_year=2026, limit_amount=12000.00, consumed_amount=0.00, remaining=12000.00, requested_amount=1450.00
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

[MP-IMG-001#1] NO_EVIDENCE -- The narrative never mentions physical therapy, NSAIDs, activity modification, or a home exercise program. Nothing to indicate this was tried or declined.
[MP-IMG-001#2] MET -- Exam documents sensory loss in a specific dermatome (L5), which independently satisfies this criterion.
[MP-IMG-001#3] MET -- Plain films were obtained and a reading is documented; no indication they predate the request by more than 12 months.
[MP-IMG-001#4] UNMET -- The only stated purpose is 'to further evaluate,' which the policy explicitly treats as insufficient — there is no pending surgical, neurosurgical, or interventional plan tied to the result.
[MP-IMG-001#5] NO_EVIDENCE -- No red-flag features are mentioned; this is the expected, ordinary scenario, not a documentation gap.

## Clinical narrative as submitted

45-year-old with ongoing low back pain radiating into the right leg. Symptoms have been present for several months and continue to limit daily activity.

Examination shows reduced sensation in the right L5 distribution and a positive straight leg raise on the right at approximately 45 degrees.

Plain films of the lumbar spine were ob

… truncated, 260 more characters
```
</details>

<details open><summary>Response</summary>

```json
```json
{
  "findings": [
    {
      "severity": "blocking",
      "claim": "the policy explicitly treats as insufficient — there is no pending surgical, neurosurgical, or interventional plan tied to the result",
      "problem": "This characterizes the policy's language, but MP-IMG-001#4 does not use the word 'explicitly' and does not state that the absence of a plan makes a request insufficient on its own. The clause says imaging requested 'solely for reassurance' or where 'management will not change' does not satisfy the criterion. The rationale has not established from the narrative that management will not change — only that no plan is currently documented. These are different conclusions."
    }
  ]
}
```
```
</details>

## Final determination

**denied** — The documentation does not meet 1 of the 5 criteria in MP-IMG-001. The only stated purpose is 'to further evaluate,' which the policy explicitly treats as insufficient — there is no pending surgical, neurosurgical, or interventional plan tied to the result.

## Why this one is wrong

Expected **pended** citing `MP-IMG-001`.

Gold rationale: Neurologic findings and prior radiographs are documented, but the record does not address the required trial of conservative therapy. Nothing contradicts it -- the documentation is silent, so the correct action is to request it.

---

_Replayed from the committed response cache 2026-08-30 10:07 UTC. No live model calls._