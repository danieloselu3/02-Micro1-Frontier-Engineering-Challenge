"""Generator tests.

Two things are being protected here. The first is determinism: if a seed
stops producing identical output, every committed evaluation number becomes
unreproducible and the whole measured-improvement claim collapses.

The second is internal consistency of the synthetic world. A form showing a
19-year-old beside a narrative describing a 52-year-old, or a plastic surgeon
ordering a lumbar MRI, gives the adjudicator contradictory signal and makes
the data read as obviously fabricated.
"""

from __future__ import annotations

import re

import pytest

from data.generator.build import generate
from data.generator.reference import (
    PROCEDURES_BY_CODE,
    age_range_for,
    specialties_for,
)
from data.generator.scenarios import DOS, SCENARIOS
from packages.core.models import Verdict

SEED = 20260830


@pytest.fixture(scope="module")
def built():
    return generate(SEED)


class TestDeterminism:
    def test_same_seed_produces_identical_labels(self):
        _, a, _ = generate(SEED)
        _, b, _ = generate(SEED)
        assert [c.model_dump_json() for c in a] == [c.model_dump_json() for c in b]

    def test_different_seed_produces_different_population(self):
        _, a, _ = generate(SEED)
        _, b, _ = generate(SEED + 1)
        assert [c.member.member_id for c in a] != [c.member.member_id for c in b]

    def test_case_ids_are_stable_and_unique(self, built):
        _, cases, _ = built
        ids = [c.case_id for c in cases]
        assert len(ids) == len(set(ids))
        assert ids[0] == "CASE-001"


class TestInternalConsistency:
    def test_narrative_age_matches_the_form_date_of_birth(self, built):
        """The clinical note states an age; the form states a date of birth.
        A reviewer reading both would spot a contradiction immediately."""
        _, cases, _ = built
        checked = 0
        for case in cases:
            m = re.search(r"(\d{2})-year-old", case.clinical_narrative)
            if not m:
                continue
            checked += 1
            assert int(m.group(1)) == case.member.age_on(case.date_of_service), (
                f"{case.case_id}: narrative says {m.group(1)}, "
                f"record implies {case.member.age_on(case.date_of_service)}"
            )
        assert checked > 15, "expected most narratives to state an age"

    def test_no_unfilled_template_placeholders(self, built):
        _, cases, _ = built
        for case in cases:
            assert "{age}" not in case.clinical_narrative, case.case_id

    def test_member_age_suits_the_procedure(self, built):
        _, cases, _ = built
        for case in cases:
            lo, hi = age_range_for(case.procedure_code)
            age = case.member.age_on(case.date_of_service)
            assert lo <= age <= hi, f"{case.case_id}: age {age} outside {lo}-{hi}"

    def test_provider_specialty_suits_the_procedure(self, built):
        _, cases, _ = built
        for case in cases:
            assert case.provider.specialty in specialties_for(case.procedure_code), (
                f"{case.case_id}: {case.provider.specialty} ordering "
                f"{case.procedure_code}"
            )

    def test_each_case_uses_a_distinct_member(self, built):
        """Scenarios mutate their member -- a termination date, a drained
        accumulator. Sharing a member would leak one case's setup into
        another case's expected verdict."""
        _, cases, _ = built
        ids = [c.member.member_id for c in cases]
        assert len(ids) == len(set(ids))

    def test_form_fields_agree_with_the_record_unless_deliberate(self, built):
        _, cases, _ = built
        deliberate = {"name_mismatch"}
        for case in cases:
            if case.scenario in deliberate:
                assert case.form_member_name != case.member.full_name
            else:
                assert case.form_member_name == case.member.full_name, case.case_id


class TestLabels:
    def test_every_scenario_is_represented(self, built):
        _, cases, _ = built
        produced = {c.scenario for c in cases}
        assert len(produced) == len(SCENARIOS)

    def test_no_auth_cases_use_a_procedure_that_needs_no_auth(self, built):
        """The R1 fast path is only correct if the underlying procedure
        genuinely does not require authorization."""
        _, cases, _ = built
        for case in cases:
            if case.label.verdict == Verdict.NO_AUTH_REQUIRED:
                assert not PROCEDURES_BY_CODE[case.procedure_code].requires_preauth
                assert case.label.governing_rule == "R1"

    def test_auth_required_cases_use_a_procedure_that_needs_auth(self, built):
        _, cases, _ = built
        for case in cases:
            if case.label.verdict != Verdict.NO_AUTH_REQUIRED:
                assert PROCEDURES_BY_CODE[case.procedure_code].requires_preauth, (
                    f"{case.case_id} adjudicates {case.procedure_code}, which "
                    "does not require prior authorization"
                )

    def test_denials_always_require_human_review(self, built):
        """A denial affects someone's care and carries a clinician's name.
        No gold label may say otherwise."""
        _, cases, _ = built
        for case in cases:
            if case.label.verdict == Verdict.DENIED:
                assert case.label.requires_human_review, case.case_id

    def test_no_auth_required_never_needs_a_clinician(self, built):
        _, cases, _ = built
        fast = [c for c in cases if c.label.verdict == Verdict.NO_AUTH_REQUIRED]
        assert fast
        for case in fast:
            assert not case.label.requires_human_review

    def test_pends_name_what_is_missing(self, built):
        """A pend that does not say what it wants is just a slow denial."""
        _, cases, _ = built
        pends = [c for c in cases if c.label.verdict == Verdict.PENDED]
        assert pends
        # necessity_borderline pends for ambiguity rather than a missing
        # document, so it is the one case allowed to have no list.
        for case in pends:
            if case.scenario != "necessity_borderline":
                assert case.label.expected_missing_information, case.case_id

    def test_expected_fields_match_what_is_printed(self, built):
        _, cases, _ = built
        for case in cases:
            ef = case.label.expected_fields
            assert ef["member_id"] == case.form_member_id
            assert ef["member_name"] == case.form_member_name
            assert ef["procedure_code"] == case.procedure_code
            assert ef["date_of_service"] == case.form_date_of_service

    def test_governing_rules_are_known(self, built):
        _, cases, _ = built
        valid_rules = {f"R{i}" for i in range(1, 10)}
        for case in cases:
            gr = case.label.governing_rule
            assert gr in valid_rules or gr.startswith("MP-"), f"{case.case_id}: {gr}"

    def test_the_case_mix_covers_every_verdict(self, built):
        _, cases, _ = built
        produced = {c.label.verdict for c in cases}
        assert produced == set(Verdict)


class TestScenarioSetup:
    """Spot-checks that the scenario actually created the condition it claims."""

    def _one(self, cases, scenario):
        return next(c for c in cases if c.scenario == scenario)

    def test_terminated_policy_really_terminated_before_service(self, built):
        _, cases, _ = built
        case = self._one(cases, "terminated_policy")
        assert case.member.termination_date is not None
        assert case.member.termination_date < DOS
        assert not case.member.is_active_on(DOS)

    def test_limit_exhausted_leaves_no_balance(self, built):
        pop, cases, _ = built
        case = self._one(cases, "limit_exhausted")
        acc = pop.accumulator(case.member.member_id, "imaging")
        assert acc.remaining == 0

    def test_limit_partial_leaves_some_but_not_enough(self, built):
        pop, cases, _ = built
        case = self._one(cases, "limit_partial")
        acc = pop.accumulator(case.member.member_id, "imaging")
        cost = PROCEDURES_BY_CODE[case.procedure_code].unit_cost
        assert 0 < acc.remaining < cost

    def test_duplicate_scenario_creates_a_live_authorization(self, built):
        _, cases, auths = built
        case = self._one(cases, "duplicate_authorization")
        match = [a for a in auths if a.member_id == case.member.member_id]
        assert match and match[0].covers(DOS, case.procedure_code)

    def test_code_mismatch_uses_an_unpaired_diagnosis(self, built):
        from data.generator.reference import CODE_PAIRS

        _, cases, _ = built
        case = self._one(cases, "code_mismatch")
        assert case.diagnosis_codes[0] not in CODE_PAIRS[case.procedure_code]

    def test_out_of_network_provider_is_actually_out_of_network(self, built):
        from packages.core.records import NetworkTier

        _, cases, _ = built
        case = self._one(cases, "out_of_network")
        assert case.provider.network_tier == NetworkTier.OUT_OF_NETWORK
