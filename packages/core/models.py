"""Domain contracts for prior-authorization adjudication.

Every stage of the pipeline reads and writes these types. They are the only
thing the rules engine, the agents, the MCP servers, and the two web apps
agree on, so they change deliberately.

Vocabulary follows US commercial prior authorization: CPT/HCPCS procedure
codes, ICD-10-CM diagnosis codes, NPI provider identifiers, and the
utilization-management verdicts a payer is permitted to issue.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Verdict(str, Enum):
    """The determinations a payer may issue on a prior-authorization request.

    NO_AUTH_REQUIRED is deliberately distinct from APPROVED. If a procedure
    never needed authorization, the payer has not adjudicated medical
    necessity and must not create a record implying it did -- a phantom
    authorization can be cited in a later claims dispute as though the payer
    reviewed and blessed the service. The provider is told they may proceed;
    they are not told they hold an authorization.
    """

    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    DENIED = "denied"
    PENDED = "pended"
    NO_AUTH_REQUIRED = "no_auth_required"


class RuleOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class CriterionStatus(str, Enum):
    """How a single medical-policy criterion fared against the narrative.

    NO_EVIDENCE is not the same as UNMET. Unmet means the record affirmatively
    contradicts the criterion; no-evidence means the submitted documentation is
    silent. The first supports a denial, the second supports a pend requesting
    the missing documentation -- conflating them is how payers deny care for
    paperwork reasons.
    """

    MET = "met"
    UNMET = "unmet"
    NO_EVIDENCE = "no_evidence"


class SubmissionChannel(str, Enum):
    PORTAL = "portal"
    FAX = "fax"
    API = "api"


class DegradationTier(str, Enum):
    """How badly the source document was mangled before it reached us.

    Held on the submission so extraction accuracy can be reported per tier
    rather than as a single misleading average.
    """

    CLEAN = "clean"
    SCAN = "scan"
    FAX = "fax"
    PHOTO = "photo"
    HANDWRITTEN = "handwritten"


class ReviewDecision(str, Enum):
    CONFIRM = "confirm"
    OVERRIDE = "override"
    PEND = "pend"
    ESCALATE = "escalate"


class ReviewerRole(str, Enum):
    NURSE = "um_nurse"
    MEDICAL_DIRECTOR = "medical_director"


# --------------------------------------------------------------------------
# Intake and extraction
# --------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """Normalised 0-1 coordinates, so overlays survive any render scale."""

    page: int = 0
    x: float
    y: float
    width: float
    height: float


class ExtractedField(BaseModel):
    """One field read off the form, with everything needed to audit it.

    `source` is what makes the reviewer console's click-through provenance
    possible: every value on screen can be traced back to the pixels it came
    from. A field with no source is a field the model invented.
    """

    name: str
    value: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    source: BoundingBox | None = None
    reread: bool = False  # true if a targeted second pass produced this value


class Submission(BaseModel):
    submission_id: str
    channel: SubmissionChannel
    received_at: datetime
    document_uri: str
    degradation: DegradationTier = DegradationTier.CLEAN
    case_id: str | None = None  # set for generated evaluation cases only


class ExtractedRequest(BaseModel):
    """The form, read. Values are still raw strings as they appeared on paper.

    Resolution to real database identifiers happens in a separate stage so an
    extraction error and a matching error stay distinguishable in evaluation.
    """

    submission_id: str
    fields: dict[str, ExtractedField]
    clinical_narrative: str = ""
    overall_confidence: float = Field(ge=0.0, le=1.0)

    def value(self, name: str) -> str | None:
        field = self.fields.get(name)
        return field.value if field else None

    def low_confidence(self, threshold: float) -> list[str]:
        return [n for n, f in self.fields.items() if f.confidence < threshold]


class ResolvedEntities(BaseModel):
    """Extracted strings matched against real records.

    Match confidence is carried separately from extraction confidence: a
    perfectly-read member name that matches three people is a different
    problem from a smudged one that matches exactly one.
    """

    member_id: str | None = None
    member_match_confidence: float = 0.0
    provider_npi: str | None = None
    provider_match_confidence: float = 0.0
    procedure_code: str | None = None
    diagnosis_codes: list[str] = Field(default_factory=list)
    date_of_service: date | None = None
    units_requested: int = 1
    place_of_service: str | None = None
    ambiguities: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Deterministic rule evaluation
# --------------------------------------------------------------------------


RuleId = Literal["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9"]


class RuleResult(BaseModel):
    """The outcome of one deterministic check.

    `evidence` holds the actual record identifiers and values consulted, so
    the reviewer console can render "policy P-4471, term_date 2026-07-31"
    rather than an unfalsifiable assertion. A rule that cannot name its
    evidence returns UNKNOWN, never PASS.
    """

    rule_id: RuleId
    name: str
    outcome: RuleOutcome
    summary: str
    evidence: dict[str, str | int | float | None] = Field(default_factory=dict)
    is_hard_stop: bool = False


class RuleReport(BaseModel):
    results: list[RuleResult]

    @property
    def failures(self) -> list[RuleResult]:
        return [r for r in self.results if r.outcome == RuleOutcome.FAIL]

    @property
    def unknowns(self) -> list[RuleResult]:
        return [r for r in self.results if r.outcome == RuleOutcome.UNKNOWN]

    @property
    def hard_stop(self) -> RuleResult | None:
        return next(
            (r for r in self.failures if r.is_hard_stop),
            None,
        )

    def get(self, rule_id: str) -> RuleResult | None:
        return next((r for r in self.results if r.rule_id == rule_id), None)


# --------------------------------------------------------------------------
# Retrieval and medical necessity
# --------------------------------------------------------------------------


class PolicyClause(BaseModel):
    """A retrieved chunk. Chunks are split on criterion boundaries, never on
    token counts, so a retrieved clause is always a complete quotable rule."""

    clause_id: str
    document_id: str
    document_title: str
    version: str
    text: str
    score: float = 0.0


class CriterionAssessment(BaseModel):
    clause_id: str
    criterion_text: str
    status: CriterionStatus
    rationale: str
    narrative_support: str | None = None  # verbatim sentence that satisfied it


class NecessityJudgment(BaseModel):
    """The only opinion a model is allowed to form about the outcome.

    It deliberately carries no verdict. The verdict is assembled in code from
    this plus the rule report, under an explicit precedence order.
    """

    assessments: list[CriterionAssessment]
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainties: list[str] = Field(default_factory=list)

    @property
    def all_met(self) -> bool:
        return bool(self.assessments) and all(
            a.status == CriterionStatus.MET for a in self.assessments
        )

    @property
    def any_unmet(self) -> bool:
        return any(a.status == CriterionStatus.UNMET for a in self.assessments)

    @property
    def missing_evidence(self) -> list[CriterionAssessment]:
        return [a for a in self.assessments if a.status == CriterionStatus.NO_EVIDENCE]


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------


class CriticFinding(BaseModel):
    severity: Literal["blocking", "advisory"]
    claim: str
    problem: str


class CriticReport(BaseModel):
    findings: list[CriticFinding] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not any(f.severity == "blocking" for f in self.findings)


# --------------------------------------------------------------------------
# Determination
# --------------------------------------------------------------------------


class Determination(BaseModel):
    """The assembled outcome, before and after human review.

    `governing_rule` is the single reason that decided this case -- a rule id,
    a policy clause id, or the sentinel used when no authorization was needed.
    Evaluation scores it separately from the verdict, because a right answer
    reached for the wrong reason will not survive an appeal.
    """

    determination_id: str
    submission_id: str
    verdict: Verdict
    governing_rule: str
    reason: str
    approved_units: int | None = None
    approved_amount: Decimal | None = None
    missing_information: list[str] = Field(default_factory=list)

    rule_report: RuleReport | None = None
    necessity: NecessityJudgment | None = None
    critic: CriticReport | None = None
    retrieved_clauses: list[PolicyClause] = Field(default_factory=list)

    auto_released: bool = False
    requires_human_review: bool = True
    escalation_reasons: list[str] = Field(default_factory=list)

    created_at: datetime
    model_cost_usd: Decimal = Decimal("0")
    elapsed_seconds: float = 0.0


class ReviewAction(BaseModel):
    """Who did what. This record is both the audit trail and the signature
    block on the letter -- nothing is issued without one."""

    action_id: str
    determination_id: str
    reviewer_id: str
    reviewer_name: str
    reviewer_role: ReviewerRole
    decision: ReviewDecision
    final_verdict: Verdict
    reason: str
    field_corrections: dict[str, str] = Field(default_factory=dict)
    seconds_spent: float = 0.0
    acted_at: datetime
