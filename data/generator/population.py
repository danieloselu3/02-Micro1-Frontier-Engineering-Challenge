"""Synthetic member, provider and reviewer population.

Everything here is fabricated. Names come from Faker, identifiers follow the
shape of the real thing (10-digit NPI, member ids) without colliding with any
live registry -- NPIs are generated in the 9xxxxxxxxx block, which is not
issued.

The population is built from a seeded Random so a given seed always produces
byte-identical output. That is what makes extraction and adjudication scores
comparable across runs, and it is the whole reason the evaluation can be
replayed by someone else.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from faker import Faker

from data.generator.reference import BENEFIT_LIMITS, PLANS, PROCEDURES
from packages.core.records import (
    Accumulator,
    Member,
    MemberStatus,
    NetworkTier,
    Provider,
    Reviewer,
)

PLAN_YEAR = 2026

SPECIALTIES = [
    "Orthopedic Surgery",
    "Neurology",
    "Diagnostic Radiology",
    "Family Medicine",
    "Physical Medicine and Rehabilitation",
    "Gastroenterology",
    "Medical Oncology",
    "Cardiothoracic Surgery",
    "Plastic Surgery",
    "Pain Medicine",
]

FACILITY_SUFFIXES = [
    "Regional Medical Center",
    "Orthopedic Associates",
    "Imaging Partners",
    "Surgical Institute",
    "Health Group",
    "Specialty Clinic",
]


class Population:
    """A seeded payer population: members, providers, accumulators, reviewers."""

    def __init__(self, seed: int, n_members: int = 240, n_providers: int = 60) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.faker = Faker("en_US")
        self.faker.seed_instance(seed)

        self.members: list[Member] = []
        self.providers: list[Provider] = []
        self.accumulators: list[Accumulator] = []
        self.reviewers: list[Reviewer] = self._build_reviewers()

        self._build_members(n_members)
        self._build_providers(n_providers)

    # -- members ------------------------------------------------------------

    def _build_members(self, n: int) -> None:
        for i in range(n):
            plan = self.rng.choice(PLANS)
            # Enrolment spread across the prior two years so waiting-period
            # and pre-existing windows land in a realistic mix of states.
            enrolled = date(PLAN_YEAR - 1, 1, 1) + timedelta(
                days=self.rng.randint(0, 600)
            )
            effective = enrolled
            sex = self.rng.choice(["M", "F"])
            member = Member(
                member_id=f"MBR-{100000 + i}",
                first_name=(
                    self.faker.first_name_male() if sex == "M" else self.faker.first_name_female()
                ),
                last_name=self.faker.last_name(),
                date_of_birth=self.faker.date_of_birth(minimum_age=19, maximum_age=78),
                sex=sex,
                plan_id=plan.plan_id,
                group_id=f"GRP-{self.rng.randint(1000, 1099)}",
                status=MemberStatus.ACTIVE,
                effective_date=effective,
                termination_date=None,
                premium_paid_through=date(PLAN_YEAR, 12, 31),
                state=self.rng.choice(plan.covered_states),
                enrolled_at=enrolled,
            )
            self.members.append(member)
            self._build_accumulators_for(member)

    def _build_accumulators_for(self, member: Member) -> None:
        """Give each member a plausible amount of the year already spent."""
        for category, limit in BENEFIT_LIMITS[member.plan_id].items():
            # Most members have used a little; a long tail have used a lot.
            fraction = self.rng.choice(
                [0.0, 0.05, 0.1, 0.2, 0.3, 0.45, 0.6, 0.75, 0.9]
            )
            consumed = (limit * Decimal(str(fraction))).quantize(Decimal("0.01"))
            self.accumulators.append(
                Accumulator(
                    member_id=member.member_id,
                    plan_year=PLAN_YEAR,
                    category=category,
                    limit_amount=limit,
                    consumed_amount=consumed,
                )
            )

    # -- providers ----------------------------------------------------------

    def _build_providers(self, n: int) -> None:
        all_codes = [p.code for p in PROCEDURES]
        for _ in range(n):
            specialty = self.rng.choice(SPECIALTIES)
            # Most providers are contracted and in good standing; the
            # scenarios that need a bad one construct it explicitly rather
            # than relying on chance, so the case mix stays deterministic.
            self.providers.append(
                Provider(
                    npi=f"9{self.rng.randint(100000000, 999999999)}"[:10],
                    name=f"{self.faker.last_name()} {self.rng.choice(FACILITY_SUFFIXES)}",
                    specialty=specialty,
                    network_tier=NetworkTier.IN_NETWORK,
                    license_state=self.rng.choice(["OH", "MI", "IN", "KY", "PA"]),
                    license_expiry=date(PLAN_YEAR + 1, 6, 30),
                    contract_start=date(PLAN_YEAR - 3, 1, 1),
                    contract_end=None,
                    sanctioned=False,
                    # Credentialed for most of the catalogue, so R6 failures
                    # come from the scenarios rather than from noise.
                    credentialed_procedures=all_codes,
                )
            )

    # -- reviewers ----------------------------------------------------------

    def _build_reviewers(self) -> list[Reviewer]:
        """A small fixed roster. Fixed rather than generated because these
        names appear on issued determination letters and in the audit trail,
        and they should not move between runs."""
        return [
            Reviewer(
                reviewer_id="RVW-001",
                name="Amara Okonkwo",
                role="um_nurse",
                credentials="RN, BSN",
                license_number="RN-OH-448120",
            ),
            Reviewer(
                reviewer_id="RVW-002",
                name="Daniel Reyes",
                role="um_nurse",
                credentials="RN, MSN",
                license_number="RN-OH-451903",
            ),
            Reviewer(
                reviewer_id="RVW-003",
                name="Priya Raghunathan",
                role="medical_director",
                credentials="MD, Internal Medicine",
                license_number="MD-OH-102774",
            ),
        ]

    # -- selection helpers used by the scenario builders --------------------

    def member_on_plan(
        self,
        plan_id: str,
        exclude: set[str] | None = None,
        age_range: tuple[int, int] | None = None,
        on: date | None = None,
    ) -> Member:
        return self._pick_member(
            exclude, age_range, on, predicate=lambda m: m.plan_id == plan_id,
            what=f"plan {plan_id}",
        )

    def any_member(
        self,
        exclude: set[str] | None = None,
        age_range: tuple[int, int] | None = None,
        on: date | None = None,
    ) -> Member:
        return self._pick_member(exclude, age_range, on, predicate=lambda m: True, what="pool")

    def _pick_member(self, exclude, age_range, on, predicate, what: str) -> Member:
        """Choose an unused member, optionally constrained by age.

        The age window matters because the clinical narrative is written for
        a plausible patient -- a knee replacement request for a 22-year-old
        would contradict its own justification text and give the adjudicator
        a spurious signal to reason from.
        """
        exclude = exclude or set()
        on = on or date(PLAN_YEAR, 8, 14)
        candidates = [
            m for m in self.members if m.member_id not in exclude and predicate(m)
        ]
        if age_range:
            lo, hi = age_range
            fitted = [m for m in candidates if lo <= m.age_on(on) <= hi]
            if fitted:
                candidates = fitted
        if not candidates:
            raise LookupError(f"no unused member remains in {what}")
        return self.rng.choice(candidates)

    def any_provider(self, specialties: list[str] | None = None) -> Provider:
        """Pick a provider, preferring one whose specialty fits the request."""
        candidates = self.providers
        if specialties:
            fitted = [p for p in candidates if p.specialty in specialties]
            if fitted:
                candidates = fitted
        return self.rng.choice(candidates)

    def accumulator(self, member_id: str, category: str) -> Accumulator:
        for a in self.accumulators:
            if a.member_id == member_id and a.category == category:
                return a
        raise LookupError(f"no {category} accumulator for {member_id}")

    def replace_member(self, member: Member) -> None:
        """Swap in a mutated copy, keeping the list authoritative."""
        for i, m in enumerate(self.members):
            if m.member_id == member.member_id:
                self.members[i] = member
                return
        raise LookupError(f"unknown member {member.member_id}")

    def replace_provider(self, provider: Provider) -> None:
        for i, p in enumerate(self.providers):
            if p.npi == provider.npi:
                self.providers[i] = provider
                return
        raise LookupError(f"unknown provider {provider.npi}")

    def set_consumed(self, member_id: str, category: str, consumed: Decimal) -> None:
        self.accumulator(member_id, category).consumed_amount = consumed
