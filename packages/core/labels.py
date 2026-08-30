"""Ground truth for evaluation cases.

Labels are emitted by the generator from the record state it just created,
independently of the policy prose the retriever will later see. When the two
disagree, that is a finding worth reporting -- not a bug to paper over.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from packages.core.models import DegradationTier, Verdict


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
