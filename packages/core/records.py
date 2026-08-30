"""Reference records held by the payer.

These mirror the database tables. The rules engine consumes them as plain
objects so it can be unit-tested with no database in the loop.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class NetworkTier(str, Enum):
    IN_NETWORK = "in_network"
    OUT_OF_NETWORK = "out_of_network"
    TERMINATED = "terminated"


class MemberStatus(str, Enum):
    ACTIVE = "active"
    TERMINATED = "terminated"
    SUSPENDED = "suspended"  # premium delinquency


class Member(BaseModel):
    member_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    plan_id: str
    group_id: str
    status: MemberStatus
    effective_date: date
    termination_date: date | None = None
    premium_paid_through: date | None = None
    state: str
    enrolled_at: date

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def age_on(self, when: date) -> int:
        years = when.year - self.date_of_birth.year
        if (when.month, when.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    def is_active_on(self, when: date) -> bool:
        if when < self.effective_date:
            return False
        if self.termination_date and when > self.termination_date:
            return False
        return self.status == MemberStatus.ACTIVE


class Plan(BaseModel):
    plan_id: str
    name: str
    waiting_period_days: int = 0
    preexisting_exclusion_months: int = 0
    requires_in_network: bool = False
    covered_states: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)
    coverage_document_id: str | None = None


class Accumulator(BaseModel):
    """A benefit bucket for one member, one plan year, one category.

    Remaining balance is computed, never stored, so it cannot drift from the
    limit and consumed figures the reviewer sees.
    """

    member_id: str
    plan_year: int
    category: str
    limit_amount: Decimal
    consumed_amount: Decimal

    @property
    def remaining(self) -> Decimal:
        return max(Decimal("0"), self.limit_amount - self.consumed_amount)


class Provider(BaseModel):
    npi: str
    name: str
    specialty: str
    network_tier: NetworkTier
    license_state: str
    license_expiry: date
    contract_start: date
    contract_end: date | None = None
    sanctioned: bool = False
    credentialed_procedures: list[str] = Field(default_factory=list)

    def is_contracted_on(self, when: date) -> bool:
        if when < self.contract_start:
            return False
        if self.contract_end and when > self.contract_end:
            return False
        return self.network_tier != NetworkTier.TERMINATED


class Procedure(BaseModel):
    code: str  # CPT / HCPCS
    description: str
    category: str
    requires_preauth: bool
    unit_cost: Decimal
    always_review: bool = False  # oncology, transplant, experimental
    sex_restriction: str | None = None
    age_min: int | None = None
    age_max: int | None = None
    policy_document_id: str | None = None


class Diagnosis(BaseModel):
    code: str  # ICD-10-CM
    description: str


class PriorAuthorization(BaseModel):
    auth_id: str
    member_id: str
    provider_npi: str
    procedure_code: str
    valid_from: date
    valid_to: date
    status: str
    units_approved: int = 1

    def covers(self, when: date, code: str) -> bool:
        return (
            self.status == "active"
            and self.procedure_code == code
            and self.valid_from <= when <= self.valid_to
        )


class Reviewer(BaseModel):
    reviewer_id: str
    name: str
    role: str
    credentials: str  # "RN, BSN" / "MD, Internal Medicine"
    license_number: str


class CaseFacts(BaseModel):
    """Everything the rules engine needs, gathered in one deterministic pass.

    Assembling this up front rather than letting rules fetch their own data
    keeps the rules pure functions and makes the whole evaluation replayable
    from a fixture.
    """

    member: Member | None = None
    plan: Plan | None = None
    provider: Provider | None = None
    procedure: Procedure | None = None
    diagnoses: list[Diagnosis] = Field(default_factory=list)
    accumulators: list[Accumulator] = Field(default_factory=list)
    prior_auths: list[PriorAuthorization] = Field(default_factory=list)
    valid_diagnosis_codes: list[str] = Field(default_factory=list)
    date_of_service: date | None = None
    units_requested: int = 1

    def accumulator_for(self, category: str, plan_year: int) -> Accumulator | None:
        return next(
            (
                a
                for a in self.accumulators
                if a.category == category and a.plan_year == plan_year
            ),
            None,
        )
