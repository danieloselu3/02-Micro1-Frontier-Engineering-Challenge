"""Ground truth for evaluation cases.

Labels are emitted by the generator from the record state it just created,
independently of the policy prose the retriever will later see. When the two
disagree, that is a finding worth reporting -- not a bug to paper over.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from packages.core.models import DegradationTier, Verdict
from packages.core.records import Member, Provider


class GoldLabel(BaseModel):
    case_id: str
    verdict: Verdict
    governing_rule: str
    rationale: str

    #: The scenario this case was built to exercise, e.g. "terminated_policy".
    #: Lets the report break accuracy down by failure mode rather than
    #: reporting one average that hides which category is broken.
    scenario: str
    is_adversarial: bool = False

    #: Field name -> exact value as printed on the form. Scores extraction
    #: independently of whether the final verdict happened to come out right.
    expected_fields: dict[str, str] = Field(default_factory=dict)
    degradation: DegradationTier = DegradationTier.CLEAN

    #: For pends: what the agent should have identified as missing.
    expected_missing_information: list[str] = Field(default_factory=list)

    #: True when a correct system must route this to a human regardless of
    #: verdict -- denials, always-review procedures, unresolvable ambiguity.
    requires_human_review: bool = True

    @property
    def requires_necessity_judgment(self) -> bool:
        """True when the deterministic rules alone cannot reach this verdict.

        Approvals always need one: nothing may be authorized without a
        clinical assessment. Partial approvals need one too -- the benefit
        cap only applies to a request that was going to be approved, so a
        case capped by R7 is still gated on medical necessity first.

        Everything else -- hard-stop denials, coding pends, the no-auth fast
        path -- is settled by the rules with no model in the loop.
        """
        return (
            self.verdict in (Verdict.APPROVED, Verdict.PARTIALLY_APPROVED)
            or self.governing_rule.startswith("MP-")
        )


class GeneratedCase(BaseModel):
    """One evaluation case: the request, the records behind it, and the truth.

    `form_*` fields are what is printed on the paper, which is deliberately
    allowed to disagree with the database record -- a misspelled surname or a
    smudged member id is the entity-resolution problem we want to measure.
    """

    case_id: str
    scenario: str
    member: Member
    provider: Provider
    procedure_code: str
    diagnosis_codes: list[str]
    date_of_service: date
    units_requested: int = 1
    clinical_narrative: str

    form_member_name: str
    form_member_id: str
    form_provider_npi: str
    form_date_of_service: str

    label: GoldLabel
