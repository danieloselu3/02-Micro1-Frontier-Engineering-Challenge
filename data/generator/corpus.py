"""The retrieval corpus: medical policies and certificates of coverage.

These are synthetic documents written in the register and structure of real
US commercial payer medical policy bulletins. They are the rubric the
medical-necessity judgment is scored against, so two properties matter:

1. Criteria are numbered and individually quotable. Chunking splits on those
   numbered boundaries, never on token counts, so a retrieved clause is
   always a complete rule a reviewer can read on its own.

2. Criteria are written independently of the gold labels. The labels come
   from record state in scenarios.py; these documents describe the clinical
   standard. If the two disagree on a case, that is a finding worth
   reporting rather than something to reconcile silently.
"""

from __future__ import annotations

from pydantic import BaseModel


class PolicyDoc(BaseModel):
    document_id: str
    title: str
    doc_type: str  # medical_policy | coverage_certificate
    version: str
    preamble: str
    criteria: list[str]
    footer: str = ""

    #: 1-based indices into `criteria` that are *exceptions* rather than
    #: requirements -- clauses which, when satisfied, waive the others.
    #: A red-flag clause is the canonical case: it is not something the
    #: documentation must establish, it is something that short-circuits the
    #: rest when present. Treating one as a requirement means every ordinary
    #: request is pended for failing to document an emergency it does not
    #: have.
    exception_criteria: list[int] = []

    def chunks(self) -> list[tuple[str, str, str]]:
        """(clause_id, text, role) split on criterion boundaries.

        Roles matter downstream. Only `criterion` clauses are things the
        submitted documentation is required to establish; `scope` and `note`
        are context a reviewer may want but which nothing can "fail", and
        `exception` waives the requirements when it applies.
        """
        out = [
            (
                f"{self.document_id}#0",
                f"{self.title} -- Scope\n\n{self.preamble.strip()}",
                "scope",
            )
        ]
        for i, text in enumerate(self.criteria, start=1):
            role = "exception" if i in self.exception_criteria else "criterion"
            out.append((f"{self.document_id}#{i}", text.strip(), role))
        if self.footer:
            out.append((f"{self.document_id}#F", self.footer.strip(), "note"))
        return out

    @property
    def body(self) -> str:
        parts = [self.preamble.strip(), ""]
        parts += [c.strip() for c in self.criteria]
        if self.footer:
            parts += ["", self.footer.strip()]
        return "\n\n".join(parts)


# ==========================================================================
# Medical policies
# ==========================================================================

MP_IMG_001 = PolicyDoc(
    document_id="MP-IMG-001",
    title="Medical Policy MP-IMG-001: Magnetic Resonance Imaging of the Lumbar Spine",
    doc_type="medical_policy",
    version="2026.2",
    preamble="""
This policy applies to CPT 72148 (MRI lumbar spine without contrast) for
members presenting with low back pain, with or without radicular symptoms.
It does not apply to imaging performed during an inpatient admission, to
post-operative surveillance imaging, or to members with a known malignancy
under active surveillance, each of which is addressed separately.

Advanced imaging of the lumbar spine is considered medically necessary when
criterion 1 and criterion 2 are both satisfied, and criteria 3 and 4 are
documented. Where a red-flag condition under criterion 5 is present,
criteria 1 through 4 are waived and imaging may proceed without delay.
""",
    criteria=[
        """
Criterion 1 -- Failure of conservative management.
The record documents a trial of conservative therapy of at least six weeks
in duration, undertaken within the twelve months preceding the request.
Acceptable modalities include supervised physical therapy, a documented
course of non-steroidal anti-inflammatory medication, activity modification,
or a home exercise programme with recorded adherence. The record must state
the duration of the trial and its outcome. A statement that conservative
therapy was offered and declined does not satisfy this criterion.
""",
        """
Criterion 2 -- Objective neurologic or radicular findings.
Physical examination documents at least one of the following: a diminished
or absent deep tendon reflex asymmetric to the contralateral side; sensory
loss in an identifiable dermatomal distribution; motor weakness of 4/5 or
less in a myotomal distribution; or a positive straight leg raise reproducing
radicular symptoms below the knee. Subjective report of radiating pain alone,
without a corroborating examination finding, does not satisfy this criterion.
""",
        """
Criterion 3 -- Prior plain radiography.
Plain radiographs of the lumbar spine have been performed and interpreted
prior to the request, and the report is available. Radiographs performed more
than twelve months before the request do not satisfy this criterion unless
the clinical presentation is unchanged.
""",
        """
Criterion 4 -- Impact on management.
The record identifies how the imaging result will alter management. Acceptable
statements include a pending surgical or neurosurgical consultation, planned
interventional pain management contingent on the result, or evaluation for a
procedure the member is otherwise a candidate for. Imaging requested solely
for reassurance, or to document a condition where management will not change,
does not satisfy this criterion.
""",
        """
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
""",
    ],
    exception_criteria=[5],
    footer="""
Where the submitted documentation does not address a criterion, the request
is returned for additional information rather than denied. A denial is issued
only where the record affirmatively establishes that a criterion is not met.
""",
)


MP_ORT_001 = PolicyDoc(
    document_id="MP-ORT-001",
    title="Medical Policy MP-ORT-001: Total Knee Arthroplasty",
    doc_type="medical_policy",
    version="2026.1",
    preamble="""
This policy applies to CPT 27447 (total knee arthroplasty) for members with
degenerative joint disease of the knee. It does not apply to revision
arthroplasty, to arthroplasty performed for acute fracture, or to
unicompartmental replacement, each of which is addressed separately.

Total knee arthroplasty is considered medically necessary when all four
criteria below are satisfied.
""",
    criteria=[
        """
Criterion 1 -- Radiographic severity.
Weight-bearing radiographs of the affected knee, obtained within the twelve
months preceding the request, demonstrate Kellgren-Lawrence grade 3 or grade
4 change: definite joint space narrowing with osteophyte formation and
subchondral sclerosis, or bone-on-bone contact. Non-weight-bearing films do
not satisfy this criterion, as they systematically understate joint space
loss. MRI findings alone do not substitute for weight-bearing radiographs.
""",
        """
Criterion 2 -- Failure of conservative management.
The record documents at least three months of conservative management within
the preceding twelve months, comprising at least two of: supervised physical
therapy; a documented course of analgesic or anti-inflammatory medication;
intra-articular injection therapy; assistive device use; or a structured
weight management programme where indicated. The duration and outcome of each
modality must be stated.
""",
        """
Criterion 3 -- Functional limitation.
The record documents that pain or functional impairment substantially limits
activities of daily living, expressed in observable terms: restricted walking
distance, inability to negotiate stairs, night pain interfering with sleep,
or dependence on an assistive device. A pain score alone does not satisfy
this criterion.
""",
        """
Criterion 4 -- Surgical candidacy.
The record documents that the member has undergone preoperative medical
evaluation and is an appropriate surgical candidate, including consideration
of comorbidities affecting operative risk.
""",
    ],
    footer="""
Where the submitted documentation does not address a criterion, the request
is returned for additional information rather than denied.
""",
)


MP_PAI_001 = PolicyDoc(
    document_id="MP-PAI-001",
    title="Medical Policy MP-PAI-001: Lumbar Transforaminal Epidural Steroid Injection",
    doc_type="medical_policy",
    version="2026.1",
    preamble="""
This policy applies to CPT 64483 (transforaminal epidural steroid injection,
lumbar or sacral, single level) performed for radicular pain.

The procedure is considered medically necessary when all four criteria are
satisfied. Where the documentation is internally inconsistent, or where the
imaging findings cannot be reconciled with the reported symptom distribution,
the request is referred for clinical review rather than decided on the record
as submitted.
""",
    criteria=[
        """
Criterion 1 -- Radicular pain of sufficient duration.
Radicular pain has been present for at least four weeks and is documented as
limiting function. Axial back pain without a radicular component is not an
indication for transforaminal injection.
""",
        """
Criterion 2 -- Conservative management.
A trial of conservative therapy has been undertaken, comprising physical
therapy, oral analgesic or neuropathic medication, or both. The record states
the duration and the member's adherence. Where adherence is documented as
partial or inconsistent, the criterion is not clearly satisfied and the
request is referred for clinical review.
""",
        """
Criterion 3 -- Dermatomal correlation.
The reported symptom distribution follows an identifiable dermatomal pattern
and is corroborated by examination findings. Sensory disturbance described in
non-dermatomal or vague terms does not satisfy this criterion.
""",
        """
Criterion 4 -- Imaging correlation.
Advanced imaging demonstrates a structural lesion -- disc protrusion,
foraminal stenosis, or lateral recess stenosis -- at a level anatomically
consistent with the documented symptom distribution. Where the imaging
finding and the clinical distribution are discordant, the request is referred
for clinical review.
""",
    ],
)


MP_COS_001 = PolicyDoc(
    document_id="MP-COS-001",
    title="Medical Policy MP-COS-001: Blepharoplasty and Repair of Blepharoptosis",
    doc_type="medical_policy",
    version="2026.1",
    preamble="""
This policy applies to CPT 15823 (blepharoplasty, upper eyelid). Blepharoplasty
performed to improve appearance is cosmetic and is not covered under any plan.
Repair undertaken to correct a documented visual field deficit is considered
reconstructive and is evaluated against the criteria below.

Note that where a member's plan excludes the cosmetic benefit category as a
whole, that contractual exclusion applies to this procedure regardless of the
clinical documentation, and is determined before this policy is reached.
""",
    criteria=[
        """
Criterion 1 -- Documented visual field deficit.
Automated or tangent screen visual field testing demonstrates a superior
visual field deficit of at least 12 degrees, or loss of at least 24 percent
of the superior field, attributable to the eyelid position.
""",
        """
Criterion 2 -- Improvement on elevation.
Repeat visual field testing performed with the eyelid manually elevated or
taped demonstrates improvement of at least 12 degrees relative to the
untaped field, establishing that the deficit is attributable to lid position
rather than to another cause.
""",
        """
Criterion 3 -- Anatomic measurement.
External photographs document a margin-to-reflex distance of 2.0 mm or less,
or dermatochalasis resting on the lashes, in the affected eye.
""",
        """
Criterion 4 -- Functional complaint.
The record documents a functional consequence attributable to the lid
position, such as interference with reading or driving, or compensatory brow
elevation with associated frontal headache.
""",
    ],
)


MP_ONC_001 = PolicyDoc(
    document_id="MP-ONC-001",
    title="Medical Policy MP-ONC-001: Rituximab",
    doc_type="medical_policy",
    version="2026.3",
    preamble="""
This policy applies to HCPCS J9310 (injection, rituximab, 100 mg).

Requests for rituximab are reviewed by a medical director in all cases,
without exception, irrespective of how completely the criteria below are
documented. Automated release is not permitted for this agent.
""",
    criteria=[
        """
Criterion 1 -- Diagnosis.
The record documents a diagnosis for which rituximab is indicated, including
CD20-positive B-cell non-Hodgkin lymphoma, chronic lymphocytic leukaemia,
or a specified autoimmune indication.
""",
        """
Criterion 2 -- Regimen and dosing.
The record specifies the treatment regimen, the planned dose and schedule,
and the cycle number, consistent with an accepted protocol.
""",
        """
Criterion 3 -- Baseline screening.
Hepatitis B surface antigen and core antibody screening has been performed
prior to initiation, given the risk of viral reactivation.
""",
    ],
)


#: Shorter policies for procedures the case mix touches less often. They exist
#: so the retriever has plausible near-neighbours to be wrong about -- a
#: corpus containing only the right answer does not test retrieval.
SUPPORTING_POLICIES = [
    PolicyDoc(
        document_id="MP-IMG-002",
        title="Medical Policy MP-IMG-002: Magnetic Resonance Imaging of the Brain",
        doc_type="medical_policy",
        version="2026.1",
        preamble=(
            "This policy applies to CPT 70553 (MRI brain with and without "
            "contrast) for members presenting with headache, neurologic "
            "deficit, or suspected intracranial pathology."
        ),
        criteria=[
            "Criterion 1 -- Headache with an atypical feature, a new focal "
            "neurologic deficit, or a change in an established headache "
            "pattern is documented.",
            "Criterion 2 -- A trial of appropriate abortive or prophylactic "
            "therapy has been undertaken where the presentation is migraine "
            "without red-flag features.",
            "Criterion 3 -- The record identifies how the result will alter "
            "management.",
        ],
    ),
    PolicyDoc(
        document_id="MP-IMG-003",
        title="Medical Policy MP-IMG-003: CT of the Abdomen and Pelvis",
        doc_type="medical_policy",
        version="2026.1",
        preamble=(
            "This policy applies to CPT 74177 (CT abdomen and pelvis with "
            "contrast) for evaluation of abdominal pain."
        ),
        criteria=[
            "Criterion 1 -- Abdominal pain with an objective finding on "
            "examination, laboratory testing, or prior imaging is documented.",
            "Criterion 2 -- Where the presentation is chronic and "
            "non-specific, an initial evaluation including laboratory "
            "testing has been completed.",
        ],
    ),
    PolicyDoc(
        document_id="MP-ORT-002",
        title="Medical Policy MP-ORT-002: Knee Arthroscopy with Meniscectomy",
        doc_type="medical_policy",
        version="2026.1",
        preamble=(
            "This policy applies to CPT 29881 (knee arthroscopy with medial "
            "meniscectomy). Arthroscopic debridement for degenerative "
            "arthritis without mechanical symptoms is not covered."
        ),
        criteria=[
            "Criterion 1 -- Mechanical symptoms are documented: locking, "
            "catching, or giving way attributable to a meniscal tear.",
            "Criterion 2 -- MRI or arthrography confirms a meniscal tear "
            "consistent with the reported symptoms.",
            "Criterion 3 -- A trial of conservative management of at least "
            "six weeks has been completed, unless the knee is locked.",
        ],
    ),
    PolicyDoc(
        document_id="MP-SPN-001",
        title="Medical Policy MP-SPN-001: Anterior Cervical Discectomy and Fusion",
        doc_type="medical_policy",
        version="2026.1",
        preamble="This policy applies to CPT 22551 (single-level ACDF).",
        criteria=[
            "Criterion 1 -- Radiculopathy or myelopathy is documented on "
            "examination and corroborated by advanced imaging at a "
            "concordant level.",
            "Criterion 2 -- At least six weeks of conservative management "
            "has been completed, unless progressive myelopathy is present.",
        ],
    ),
    PolicyDoc(
        document_id="MP-CAR-001",
        title="Medical Policy MP-CAR-001: Coronary Artery Bypass Grafting",
        doc_type="medical_policy",
        version="2026.1",
        preamble=(
            "This policy applies to CPT 33533. All requests are reviewed by a "
            "medical director; automated release is not permitted."
        ),
        criteria=[
            "Criterion 1 -- Coronary angiography documents disease of a "
            "severity for which surgical revascularisation is indicated.",
            "Criterion 2 -- A heart team assessment or equivalent "
            "documentation of surgical candidacy is present.",
        ],
    ),
    PolicyDoc(
        document_id="MP-COS-002",
        title="Medical Policy MP-COS-002: Reduction Mammaplasty",
        doc_type="medical_policy",
        version="2026.1",
        preamble=(
            "This policy applies to CPT 19318. Where a member's plan excludes "
            "the cosmetic benefit category, that exclusion is determined "
            "before this policy is reached."
        ),
        criteria=[
            "Criterion 1 -- Persistent symptoms attributable to breast "
            "weight are documented for at least six months.",
            "Criterion 2 -- A trial of conservative measures including "
            "supportive garments and physical therapy has been completed.",
        ],
    ),
]


# ==========================================================================
# Certificates of coverage
# ==========================================================================


def _coc(plan_id: str, name: str, waiting: int, in_network: bool, states: list[str]) -> PolicyDoc:
    network_text = (
        "Services must be furnished by a participating provider. Services "
        "furnished by a non-participating provider are not covered except "
        "for emergency care and for services pre-authorized as unavailable "
        "in network."
        if in_network
        else "Services furnished by non-participating providers are covered at "
        "a reduced benefit level."
    )
    waiting_text = (
        f"No benefits are payable for services furnished within {waiting} days "
        "of the member's effective date, other than emergency care and "
        "preventive services required to be covered without cost sharing."
        if waiting
        else "No waiting period applies to this plan."
    )
    return PolicyDoc(
        document_id=f"COC-{plan_id.replace('PLN-', '')}",
        title=f"Certificate of Coverage: {name}",
        doc_type="coverage_certificate",
        version="2026",
        preamble=(
            f"This certificate describes the benefits available under {name} "
            "for the 2026 plan year. Where this certificate and a medical "
            "policy conflict, this certificate controls."
        ),
        criteria=[
            f"Article 3 -- Waiting period.\n{waiting_text}",
            f"Article 4 -- Provider network.\n{network_text}",
            (
                "Article 5 -- Service area.\nBenefits are payable for "
                f"services furnished within the plan service area, comprising: "
                f"{', '.join(states)}. Services furnished outside the service "
                "area are not covered except for emergency and urgent care."
            ),
            (
                "Article 6 -- General exclusions.\nNo benefits are payable "
                "for: cosmetic surgery and procedures performed primarily to "
                "improve appearance; services that are investigational or "
                "experimental; custodial care; services furnished before the "
                "effective date or after the termination date of coverage; "
                "and services for which the member has no financial "
                "liability."
            ),
            (
                "Article 9 -- Benefit maximums.\nAnnual maximums apply "
                "separately to the inpatient, outpatient and imaging benefit "
                "categories. Where a requested service exceeds the remaining "
                "balance in the applicable category, benefits are payable to "
                "the remaining balance and the member is responsible for the "
                "excess."
            ),
            (
                "Article 12 -- Appeal rights.\nA member or the member's "
                "authorized representative may appeal an adverse benefit "
                "determination within 180 days of receiving notice. Appeals "
                "are reviewed by a clinician who was not involved in the "
                "initial determination. Expedited review is available where "
                "the standard timeframe would seriously jeopardise the "
                "member's life, health, or ability to regain maximum "
                "function."
            ),
        ],
    )


COVERAGE_CERTIFICATES = [
    _coc("PLN-PPO-GOLD", "Meridian PPO Gold", 0, False, ["OH", "MI", "IN", "KY", "PA", "WV"]),
    _coc("PLN-HMO-CORE", "Meridian HMO Core", 90, True, ["OH"]),
    _coc("PLN-EPO-VALUE", "Meridian EPO Value", 30, True, ["OH", "MI"]),
]


ALL_DOCUMENTS: list[PolicyDoc] = [
    MP_IMG_001,
    MP_ORT_001,
    MP_PAI_001,
    MP_COS_001,
    MP_ONC_001,
    *SUPPORTING_POLICIES,
    *COVERAGE_CERTIFICATES,
]
