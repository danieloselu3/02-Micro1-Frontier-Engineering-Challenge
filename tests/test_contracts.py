"""Contract tests.

These guard the invariants the rest of the system assumes, so a careless edit
to the domain models fails here rather than three stages downstream.
"""

from datetime import date
from decimal import Decimal

from packages.core.models import (
    CriterionAssessment,
    CriterionStatus,
    CriticFinding,
    CriticReport,
    NecessityJudgment,
    RuleOutcome,
    RuleReport,
    RuleResult,
    Verdict,
)
from packages.core.records import Accumulator, Member, MemberStatus


def _member(**overrides) -> Member:
    base = dict(
        member_id="M-0001",
        first_name="Dolores",
        last_name="Whitfield",
        date_of_birth=date(1974, 3, 18),
        sex="F",
        plan_id="P-100",
        group_id="G-1",
        status=MemberStatus.ACTIVE,
        effective_date=date(2026, 1, 1),
        state="OH",
        enrolled_at=date(2026, 1, 1),
    )
    return Member(**(base | overrides))


class TestMemberEligibility:
    def test_active_within_window(self):
        assert _member().is_active_on(date(2026, 8, 14))

    def test_inactive_before_effective_date(self):
        assert not _member().is_active_on(date(2025, 12, 31))

    def test_terminated_the_day_after_termination(self):
        m = _member(termination_date=date(2026, 7, 31))
        assert m.is_active_on(date(2026, 7, 31))
        assert not m.is_active_on(date(2026, 8, 1))

    def test_suspended_member_is_not_active(self):
        assert not _member(status=MemberStatus.SUSPENDED).is_active_on(date(2026, 8, 14))

    def test_age_respects_birthday_not_yet_reached(self):
        m = _member()
        assert m.age_on(date(2026, 3, 17)) == 51
        assert m.age_on(date(2026, 3, 18)) == 52


class TestAccumulator:
    def test_remaining_is_derived(self):
        acc = Accumulator(
            member_id="M-0001",
            plan_year=2026,
            category="outpatient",
            limit_amount=Decimal("15000"),
            consumed_amount=Decimal("4200"),
        )
        assert acc.remaining == Decimal("10800")

    def test_overspend_floors_at_zero_never_negative(self):
        acc = Accumulator(
            member_id="M-0001",
            plan_year=2026,
            category="outpatient",
            limit_amount=Decimal("1000"),
            consumed_amount=Decimal("1400"),
        )
        assert acc.remaining == Decimal("0")


class TestRuleReport:
    def test_hard_stop_is_found_among_failures(self):
        report = RuleReport(
            results=[
                RuleResult(
                    rule_id="R2",
                    name="Eligibility",
                    outcome=RuleOutcome.FAIL,
                    summary="Policy terminated before date of service",
                    is_hard_stop=True,
                ),
                RuleResult(
                    rule_id="R7",
                    name="Benefit limits",
                    outcome=RuleOutcome.FAIL,
                    summary="Insufficient remaining balance",
                ),
            ]
        )
        assert report.hard_stop is not None
        assert report.hard_stop.rule_id == "R2"
        assert len(report.failures) == 2

    def test_no_hard_stop_when_only_soft_failures(self):
        report = RuleReport(
            results=[
                RuleResult(
                    rule_id="R7",
                    name="Benefit limits",
                    outcome=RuleOutcome.FAIL,
                    summary="Partial balance remains",
                )
            ]
        )
        assert report.hard_stop is None


class TestNecessityJudgment:
    def _judgment(self, *statuses: CriterionStatus) -> NecessityJudgment:
        return NecessityJudgment(
            assessments=[
                CriterionAssessment(
                    clause_id=f"C-{i}",
                    criterion_text="criterion",
                    status=s,
                    rationale="because",
                )
                for i, s in enumerate(statuses)
            ],
            summary="",
            confidence=0.9,
        )

    def test_all_met(self):
        assert self._judgment(CriterionStatus.MET, CriterionStatus.MET).all_met

    def test_empty_assessment_is_not_all_met(self):
        """An empty judgment must never read as satisfied -- that would let a
        retrieval failure silently approve care."""
        assert not self._judgment().all_met

    def test_no_evidence_is_distinct_from_unmet(self):
        j = self._judgment(CriterionStatus.MET, CriterionStatus.NO_EVIDENCE)
        assert not j.any_unmet
        assert len(j.missing_evidence) == 1


class TestCriticReport:
    def test_advisory_findings_do_not_block(self):
        report = CriticReport(
            findings=[CriticFinding(severity="advisory", claim="x", problem="y")]
        )
        assert report.is_clean

    def test_blocking_finding_is_not_clean(self):
        report = CriticReport(
            findings=[CriticFinding(severity="blocking", claim="x", problem="y")]
        )
        assert not report.is_clean


class TestVerdictVocabulary:
    def test_no_auth_required_is_not_an_approval(self):
        """A procedure that never needed authorization has not been
        adjudicated. Collapsing it into APPROVED would create a phantom
        authorization citable in a later claims dispute."""
        assert Verdict.NO_AUTH_REQUIRED != Verdict.APPROVED
        assert Verdict.NO_AUTH_REQUIRED.value == "no_auth_required"
