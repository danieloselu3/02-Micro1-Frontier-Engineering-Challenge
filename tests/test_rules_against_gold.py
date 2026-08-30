"""Run the rules engine against every gold case.

This is the load-bearing test for the deterministic half of the system. For
each of the 49 generated cases it gathers real facts from the database and
evaluates all nine rules, then checks two things:

* Cases the gold label says are decided by a rule must produce that exact
  verdict, citing that exact rule. No model is involved, so there is no
  excuse for a miss.

* Cases the gold label says are decided on medical necessity must pass every
  rule cleanly. If a rule hard-stops one of them, the pipeline would never
  reach the necessity judgment and the case would be wrongly denied on
  contractual grounds -- a false denial, the error class that matters most.

The test is skipped rather than failed when Postgres is unreachable, so the
suite still runs in a bare checkout.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from data.generator.reference import accumulator_for_procedure
from packages.core.labels import GeneratedCase
from packages.core.models import (
    CriterionAssessment,
    CriterionStatus,
    CriticFinding,
    CriticReport,
    NecessityJudgment,
    RuleOutcome,
    Verdict,
)
from packages.core.repository import ClaimsRepository, connect
from packages.rules.assemble import assemble
from packages.rules.engine import evaluate

CASE_DIR = Path(__file__).resolve().parents[1] / "eval" / "cases"
PLAN_YEAR = 2026


def _load_cases() -> list[GeneratedCase]:
    files = sorted(p for p in CASE_DIR.glob("CASE-*.json"))
    return [GeneratedCase(**json.loads(p.read_text(encoding="utf-8"))) for p in files]


CASES = _load_cases()


@pytest.fixture(scope="module")
def repo():
    try:
        with connect() as conn:
            yield ClaimsRepository(conn)
    except psycopg.OperationalError:
        pytest.skip("Postgres unavailable -- run `docker compose up -d && make seed`")


def _adjudicate(repo: ClaimsRepository, case: GeneratedCase):
    facts = repo.gather(
        member_id=case.member.member_id,
        provider_npi=case.provider.npi,
        procedure_code=case.procedure_code,
        diagnosis_codes=case.diagnosis_codes,
        date_of_service=case.date_of_service,
        units_requested=case.units_requested,
        plan_year=PLAN_YEAR,
    )
    rules = evaluate(facts, accumulator_for_procedure(case.procedure_code), PLAN_YEAR)
    det = assemble(
        determination_id=f"DET-{case.case_id}",
        submission_id=case.case_id,
        rules=rules,
        facts=facts,
    )
    return facts, rules, det


def _ids(cases):
    return [c.case_id for c in cases]


#: Cases the rules settle on their own -- hard-stop denials, coding pends,
#: and the no-auth fast path. No model is involved, so a miss here is a plain
#: defect rather than a judgment call.
RULE_DECIDED = [c for c in CASES if not c.label.requires_necessity_judgment]

#: Cases that must survive every rule and reach the medical-necessity
#: judgment. Approvals and partial approvals live here too: a benefit cap
#: only applies to a request that was going to be approved.
NECESSITY_DECIDED = [c for c in CASES if c.label.requires_necessity_judgment]


class TestRuleDecidedCases:
    """Everything the rules alone are supposed to settle."""

    @pytest.mark.parametrize("case", RULE_DECIDED, ids=_ids(RULE_DECIDED))
    def test_verdict_matches_gold(self, repo, case):
        _, _, det = _adjudicate(repo, case)
        assert det.verdict == case.label.verdict, (
            f"{case.case_id} ({case.scenario}): expected "
            f"{case.label.verdict.value}, got {det.verdict.value} -- {det.reason}"
        )

    @pytest.mark.parametrize("case", RULE_DECIDED, ids=_ids(RULE_DECIDED))
    def test_cites_the_governing_rule(self, repo, case):
        """A right verdict reached by citing the wrong rule will not survive
        an appeal, so it is scored as a miss."""
        _, _, det = _adjudicate(repo, case)
        assert det.governing_rule == case.label.governing_rule, (
            f"{case.case_id} ({case.scenario}): expected "
            f"{case.label.governing_rule}, cited {det.governing_rule}"
        )

    @pytest.mark.parametrize("case", RULE_DECIDED, ids=_ids(RULE_DECIDED))
    def test_reason_names_actual_evidence(self, repo, case):
        _, rules, det = _adjudicate(repo, case)
        deciding = rules.get(det.governing_rule)
        if deciding and deciding.outcome != RuleOutcome.PASS:
            assert deciding.evidence, (
                f"{case.case_id}: {det.governing_rule} decided the case but "
                "recorded no evidence"
            )


class TestNecessityCasesReachTheModel:
    @pytest.mark.parametrize("case", NECESSITY_DECIDED, ids=_ids(NECESSITY_DECIDED))
    def test_no_rule_hard_stops_a_clinical_case(self, repo, case):
        """If a rule hard-stops here, the case is denied on contractual
        grounds and the necessity judgment never runs -- a false denial."""
        _, rules, _ = _adjudicate(repo, case)
        stop = rules.hard_stop
        assert stop is None, (
            f"{case.case_id} ({case.scenario}) should reach medical necessity, "
            f"but {stop.rule_id} hard-stopped it: {stop.summary}"
        )

    @pytest.mark.parametrize("case", NECESSITY_DECIDED, ids=_ids(NECESSITY_DECIDED))
    def test_nothing_is_undetermined(self, repo, case):
        _, rules, _ = _adjudicate(repo, case)
        assert not rules.unknowns, (
            f"{case.case_id}: undetermined checks "
            f"{[r.rule_id for r in rules.unknowns]}"
        )

    @pytest.mark.parametrize("case", NECESSITY_DECIDED, ids=_ids(NECESSITY_DECIDED))
    def test_pends_without_a_necessity_judgment(self, repo, case):
        """With no judgment supplied, the assembler must pend rather than
        approve. An absent assessment must never read as satisfied."""
        _, _, det = _adjudicate(repo, case)
        assert det.verdict == Verdict.PENDED
        assert det.requires_human_review


def _met_judgment(n: int = 3, confidence: float = 0.95) -> NecessityJudgment:
    """A stand-in for a model that found every criterion documented."""
    return NecessityJudgment(
        assessments=[
            CriterionAssessment(
                clause_id=f"MP-IMG-001#{i}",
                criterion_text=f"Criterion {i}",
                status=CriterionStatus.MET,
                rationale="Documented in the clinical narrative.",
            )
            for i in range(1, n + 1)
        ],
        summary="All criteria documented.",
        confidence=confidence,
    )


class TestVerdictsThatNeedBothHalves:
    """The rules and the judgment have to combine correctly, not just
    individually. These feed a synthetic 'all criteria met' judgment so the
    combination is tested without a model in the loop."""

    def test_partial_balance_caps_an_otherwise_clean_approval(self, repo):
        cases = [c for c in CASES if c.scenario == "limit_partial"]
        assert cases
        for case in cases:
            facts, rules, _ = _adjudicate(repo, case)
            det = assemble(
                determination_id=f"DET-{case.case_id}",
                submission_id=case.case_id,
                rules=rules,
                facts=facts,
                necessity=_met_judgment(),
            )
            assert det.verdict == Verdict.PARTIALLY_APPROVED, case.case_id
            assert det.governing_rule == "R7"
            # Approved to the balance that remains, not the amount requested.
            r7 = rules.get("R7")
            assert det.approved_amount == Decimal(str(r7.evidence["remaining"]))
            assert det.approved_amount < facts.procedure.unit_cost
            assert det.requires_human_review

    def test_clean_approval_when_rules_pass_and_criteria_are_met(self, repo):
        case = next(
            c for c in CASES
            if c.scenario == "necessity_met" and c.label.verdict == Verdict.APPROVED
        )
        facts, rules, _ = _adjudicate(repo, case)
        det = assemble(
            determination_id="DET-X",
            submission_id=case.case_id,
            rules=rules,
            facts=facts,
            necessity=_met_judgment(),
        )
        assert det.verdict == Verdict.APPROVED
        assert det.governing_rule == case.label.governing_rule

    def test_low_confidence_judgment_forces_review(self, repo):
        case = next(c for c in CASES if c.scenario == "necessity_met")
        facts, rules, _ = _adjudicate(repo, case)
        det = assemble(
            determination_id="DET-X",
            submission_id=case.case_id,
            rules=rules,
            facts=facts,
            necessity=_met_judgment(confidence=0.4),
        )
        assert det.verdict == Verdict.APPROVED
        assert det.requires_human_review
        assert any("confidence" in r for r in det.escalation_reasons)

    def test_blocking_critic_finding_forces_review(self, repo):
        case = next(c for c in CASES if c.scenario == "necessity_met")
        facts, rules, _ = _adjudicate(repo, case)
        det = assemble(
            determination_id="DET-X",
            submission_id=case.case_id,
            rules=rules,
            facts=facts,
            necessity=_met_judgment(),
            critic=CriticReport(
                findings=[
                    CriticFinding(
                        severity="blocking",
                        claim="Conservative therapy completed",
                        problem="No clause was retrieved that supports this.",
                    )
                ]
            ),
        )
        assert det.requires_human_review
        assert any("unsupported" in r for r in det.escalation_reasons)


class TestReleaseGate:
    @pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
    def test_denials_never_auto_release(self, repo, case):
        _, _, det = _adjudicate(repo, case)
        if det.verdict == Verdict.DENIED:
            assert det.requires_human_review
            assert not det.auto_released

    def test_no_auth_required_exits_without_a_clinician(self, repo):
        fast = [c for c in CASES if c.label.verdict == Verdict.NO_AUTH_REQUIRED]
        assert fast
        for case in fast:
            _, _, det = _adjudicate(repo, case)
            assert det.verdict == Verdict.NO_AUTH_REQUIRED
            assert det.auto_released
            assert not det.requires_human_review

    def test_always_review_procedures_escalate(self, repo):
        cases = [c for c in CASES if c.scenario == "always_review_specialty_drug"]
        assert cases
        for case in cases:
            facts, _, det = _adjudicate(repo, case)
            assert facts.procedure and facts.procedure.always_review
            assert det.requires_human_review
            assert any("always-review" in r for r in det.escalation_reasons)


class TestFastPathEconomics:
    def test_fast_path_needs_no_clinical_facts(self, repo):
        """The no-auth path must be decidable from the procedure code alone.

        This is what makes it cheap: no retrieval, no model call, and an
        answer in milliseconds for a third of real inbound volume.
        """
        case = next(c for c in CASES if c.label.verdict == Verdict.NO_AUTH_REQUIRED)
        _, rules, _ = _adjudicate(repo, case)
        r1 = rules.get("R1")
        assert r1 and r1.outcome == RuleOutcome.NOT_APPLICABLE
        assert r1.evidence["requires_preauth"] == "false"
