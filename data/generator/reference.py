"""Curated reference data: plans, procedures, diagnoses, and valid code pairs.

Codes are real CPT/HCPCS and ICD-10-CM values with their actual descriptions.
Nothing here is patient data -- it is the public code vocabulary a payer
operates on. Members, providers and clinical narratives are all synthetic.

The pre-auth requirement flags reflect how these services are typically
handled by US commercial payers: advanced imaging, elective orthopaedics and
specialty drugs need authorization; office visits, basic labs and plain films
do not. That split is what makes the R1 fast path worth having.
"""

from __future__ import annotations

from decimal import Decimal

from packages.core.records import Diagnosis, Plan, Procedure

# --------------------------------------------------------------------------
# Procedures
# --------------------------------------------------------------------------

PROCEDURES: list[Procedure] = [
    # -- advanced imaging: authorization required -------------------------
    Procedure(
        code="72148",
        description="MRI lumbar spine without contrast",
        category="advanced_imaging",
        requires_preauth=True,
        unit_cost=Decimal("1450.00"),
        policy_document_id="MP-IMG-001",
    ),
    Procedure(
        code="70553",
        description="MRI brain with and without contrast",
        category="advanced_imaging",
        requires_preauth=True,
        unit_cost=Decimal("2180.00"),
        policy_document_id="MP-IMG-002",
    ),
    Procedure(
        code="74177",
        description="CT abdomen and pelvis with contrast",
        category="advanced_imaging",
        requires_preauth=True,
        unit_cost=Decimal("1320.00"),
        policy_document_id="MP-IMG-003",
    ),
    # -- elective orthopaedics: authorization required ---------------------
    Procedure(
        code="27447",
        description="Total knee arthroplasty",
        category="orthopedic_surgery",
        requires_preauth=True,
        unit_cost=Decimal("32800.00"),
        policy_document_id="MP-ORT-001",
    ),
    Procedure(
        code="29881",
        description="Knee arthroscopy with medial meniscectomy",
        category="orthopedic_surgery",
        requires_preauth=True,
        unit_cost=Decimal("7400.00"),
        policy_document_id="MP-ORT-002",
    ),
    Procedure(
        code="22551",
        description="Anterior cervical discectomy and fusion, single level",
        category="spine_surgery",
        requires_preauth=True,
        unit_cost=Decimal("41250.00"),
        policy_document_id="MP-SPN-001",
    ),
    Procedure(
        code="64483",
        description="Transforaminal epidural steroid injection, lumbar, single level",
        category="pain_management",
        requires_preauth=True,
        unit_cost=Decimal("1850.00"),
        policy_document_id="MP-PAI-001",
    ),
    # -- cosmetic-adjacent: covered only on functional grounds -------------
    Procedure(
        code="15823",
        description="Blepharoplasty, upper eyelid",
        category="cosmetic",
        requires_preauth=True,
        unit_cost=Decimal("4600.00"),
        policy_document_id="MP-COS-001",
    ),
    Procedure(
        code="19318",
        description="Breast reduction mammaplasty",
        category="cosmetic",
        requires_preauth=True,
        unit_cost=Decimal("14900.00"),
        policy_document_id="MP-COS-002",
    ),
    # -- always routed to a medical director -------------------------------
    Procedure(
        code="J9310",
        description="Injection, rituximab, 100 mg",
        category="specialty_drug",
        requires_preauth=True,
        unit_cost=Decimal("5320.00"),
        always_review=True,
        policy_document_id="MP-ONC-001",
    ),
    Procedure(
        code="33533",
        description="Coronary artery bypass, single arterial graft",
        category="cardiac_surgery",
        requires_preauth=True,
        unit_cost=Decimal("98400.00"),
        always_review=True,
        policy_document_id="MP-CAR-001",
    ),
    # -- no authorization required: the R1 fast path -----------------------
    Procedure(
        code="99213",
        description="Office visit, established patient, low complexity",
        category="office_visit",
        requires_preauth=False,
        unit_cost=Decimal("135.00"),
    ),
    Procedure(
        code="71046",
        description="Radiologic examination, chest, 2 views",
        category="basic_imaging",
        requires_preauth=False,
        unit_cost=Decimal("210.00"),
    ),
    Procedure(
        code="80053",
        description="Comprehensive metabolic panel",
        category="laboratory",
        requires_preauth=False,
        unit_cost=Decimal("48.00"),
    ),
    Procedure(
        code="97110",
        description="Therapeutic exercise, each 15 minutes",
        category="physical_therapy",
        requires_preauth=False,
        unit_cost=Decimal("92.00"),
    ),
    Procedure(
        code="45378",
        description="Colonoscopy, diagnostic, with or without collection of specimen",
        category="endoscopy",
        requires_preauth=False,
        unit_cost=Decimal("2240.00"),
    ),
]


# --------------------------------------------------------------------------
# Diagnoses
# --------------------------------------------------------------------------

DIAGNOSES: list[Diagnosis] = [
    Diagnosis(code="M54.50", description="Low back pain, unspecified"),
    Diagnosis(code="M54.51", description="Vertebrogenic low back pain"),
    Diagnosis(code="M51.26", description="Other intervertebral disc displacement, lumbar region"),
    Diagnosis(code="M54.16", description="Radiculopathy, lumbar region"),
    Diagnosis(code="M17.11", description="Unilateral primary osteoarthritis, right knee"),
    Diagnosis(code="M17.12", description="Unilateral primary osteoarthritis, left knee"),
    Diagnosis(
        code="S83.241A",
        description="Other tear of medial meniscus, right knee, initial encounter",
    ),
    Diagnosis(code="M50.20", description="Other cervical disc displacement, unspecified region"),
    Diagnosis(code="G43.909", description="Migraine, unspecified, not intractable"),
    Diagnosis(code="R51.9", description="Headache, unspecified"),
    Diagnosis(code="G93.1", description="Anoxic brain damage, not elsewhere classified"),
    Diagnosis(code="R10.9", description="Unspecified abdominal pain"),
    Diagnosis(code="K21.9", description="Gastro-esophageal reflux disease without esophagitis"),
    Diagnosis(code="Z12.11", description="Encounter for screening for malignant neoplasm of colon"),
    Diagnosis(code="H02.401", description="Unspecified ptosis of right eyelid"),
    Diagnosis(code="H53.489", description="Other visual field defect, unspecified eye"),
    Diagnosis(code="N64.81", description="Ptosis of breast"),
    Diagnosis(code="M54.6", description="Pain in thoracic spine"),
    Diagnosis(
        code="C50.911",
        description="Malignant neoplasm of unspecified site of right female breast",
    ),
    Diagnosis(code="C83.30", description="Diffuse large B-cell lymphoma, unspecified site"),
    Diagnosis(code="I25.10", description="Atherosclerotic heart disease of native coronary artery"),
    Diagnosis(code="E11.9", description="Type 2 diabetes mellitus without complications"),
    Diagnosis(code="J06.9", description="Acute upper respiratory infection, unspecified"),
]


#: Which diagnoses plausibly justify which procedure. R9 uses this to catch
#: transcription errors and upcoding before a case reaches a reviewer -- a
#: lumbar MRI ordered for a sore throat is a data-entry problem, not a
#: clinical judgment call.
CODE_PAIRS: dict[str, list[str]] = {
    "72148": ["M54.50", "M54.51", "M51.26", "M54.16"],
    "70553": ["G43.909", "R51.9", "G93.1"],
    "74177": ["R10.9", "K21.9"],
    "27447": ["M17.11", "M17.12"],
    "29881": ["S83.241A", "M17.11", "M17.12"],
    "22551": ["M50.20", "M54.6"],
    "64483": ["M54.16", "M51.26", "M54.50"],
    "15823": ["H02.401", "H53.489"],
    "19318": ["N64.81", "M54.6"],
    "J9310": ["C83.30", "C50.911"],
    "33533": ["I25.10"],
    "99213": ["E11.9", "J06.9", "M54.50", "K21.9"],
    "71046": ["J06.9", "I25.10"],
    "80053": ["E11.9"],
    "97110": ["M54.50", "M17.11", "S83.241A"],
    "45378": ["Z12.11", "R10.9", "K21.9"],
}


# --------------------------------------------------------------------------
# Plans
# --------------------------------------------------------------------------

PLANS: list[Plan] = [
    Plan(
        plan_id="PLN-PPO-GOLD",
        name="Meridian PPO Gold",
        waiting_period_days=0,
        preexisting_exclusion_months=0,
        requires_in_network=False,
        covered_states=["OH", "MI", "IN", "KY", "PA", "WV"],
        excluded_categories=["cosmetic"],
        coverage_document_id="COC-PPO-GOLD",
    ),
    Plan(
        plan_id="PLN-HMO-CORE",
        name="Meridian HMO Core",
        waiting_period_days=90,
        preexisting_exclusion_months=6,
        requires_in_network=True,
        covered_states=["OH"],
        excluded_categories=["cosmetic"],
        coverage_document_id="COC-HMO-CORE",
    ),
    Plan(
        plan_id="PLN-EPO-VALUE",
        name="Meridian EPO Value",
        waiting_period_days=30,
        preexisting_exclusion_months=0,
        requires_in_network=True,
        covered_states=["OH", "MI"],
        excluded_categories=["cosmetic", "specialty_drug"],
        coverage_document_id="COC-EPO-VALUE",
    ),
]


#: Annual benefit ceilings by plan and accumulator category, in dollars.
BENEFIT_LIMITS: dict[str, dict[str, Decimal]] = {
    "PLN-PPO-GOLD": {
        "outpatient": Decimal("25000"),
        "inpatient": Decimal("150000"),
        "imaging": Decimal("12000"),
    },
    "PLN-HMO-CORE": {
        "outpatient": Decimal("15000"),
        "inpatient": Decimal("80000"),
        "imaging": Decimal("6000"),
    },
    "PLN-EPO-VALUE": {
        "outpatient": Decimal("10000"),
        "inpatient": Decimal("50000"),
        "imaging": Decimal("4000"),
    },
}


#: Which accumulator a procedure category draws down.
CATEGORY_TO_ACCUMULATOR: dict[str, str] = {
    "advanced_imaging": "imaging",
    "basic_imaging": "imaging",
    "orthopedic_surgery": "inpatient",
    "spine_surgery": "inpatient",
    "cardiac_surgery": "inpatient",
    "cosmetic": "outpatient",
    "pain_management": "outpatient",
    "specialty_drug": "outpatient",
    "office_visit": "outpatient",
    "laboratory": "outpatient",
    "physical_therapy": "outpatient",
    "endoscopy": "outpatient",
}


# --------------------------------------------------------------------------
# Lookup helpers
# --------------------------------------------------------------------------

PROCEDURES_BY_CODE: dict[str, Procedure] = {p.code: p for p in PROCEDURES}
DIAGNOSES_BY_CODE: dict[str, Diagnosis] = {d.code: d for d in DIAGNOSES}
PLANS_BY_ID: dict[str, Plan] = {p.plan_id: p for p in PLANS}

PREAUTH_REQUIRED_CODES = [p.code for p in PROCEDURES if p.requires_preauth]
NO_PREAUTH_CODES = [p.code for p in PROCEDURES if not p.requires_preauth]


def accumulator_for_procedure(code: str) -> str:
    """Which benefit bucket this procedure draws from."""
    proc = PROCEDURES_BY_CODE[code]
    return CATEGORY_TO_ACCUMULATOR[proc.category]


#: Which specialties plausibly order or perform each category. A plastic
#: surgeon requesting a lumbar MRI is the kind of detail that makes synthetic
#: data read as synthetic, and it would also give the adjudicator a spurious
#: signal to reason from.
CATEGORY_TO_SPECIALTIES: dict[str, list[str]] = {
    "advanced_imaging": ["Diagnostic Radiology", "Neurology", "Orthopedic Surgery",
                         "Family Medicine", "Physical Medicine and Rehabilitation"],
    "basic_imaging": ["Family Medicine", "Diagnostic Radiology"],
    "orthopedic_surgery": ["Orthopedic Surgery"],
    "spine_surgery": ["Orthopedic Surgery", "Neurology"],
    "cardiac_surgery": ["Cardiothoracic Surgery"],
    "cosmetic": ["Plastic Surgery"],
    "pain_management": ["Pain Medicine", "Physical Medicine and Rehabilitation"],
    "specialty_drug": ["Medical Oncology"],
    "office_visit": ["Family Medicine"],
    "laboratory": ["Family Medicine"],
    "physical_therapy": ["Physical Medicine and Rehabilitation", "Orthopedic Surgery"],
    "endoscopy": ["Gastroenterology"],
}


#: Plausible age window for each procedure, used when choosing a member.
#: A knee replacement in a 22-year-old, or a screening colonoscopy in a
#: teenager, is a data error a reviewer would spot immediately.
PROCEDURE_AGE_RANGE: dict[str, tuple[int, int]] = {
    "27447": (52, 82),   # total knee arthroplasty
    "29881": (25, 70),   # arthroscopic meniscectomy
    "22551": (35, 75),   # cervical fusion
    "33533": (48, 80),   # CABG
    "15823": (45, 80),   # blepharoplasty
    "19318": (22, 60),   # reduction mammaplasty
    "45378": (45, 75),   # screening colonoscopy
    "J9310": (30, 78),   # rituximab
    "72148": (28, 75),   # lumbar MRI
    "64483": (30, 72),   # epidural steroid injection
}


def specialties_for(code: str) -> list[str]:
    return CATEGORY_TO_SPECIALTIES[PROCEDURES_BY_CODE[code].category]


def age_range_for(code: str) -> tuple[int, int]:
    return PROCEDURE_AGE_RANGE.get(code, (19, 78))
