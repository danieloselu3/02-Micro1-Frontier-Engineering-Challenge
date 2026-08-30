"""The nine deterministic rules.

Every function here is pure: facts in, a RuleResult out, no I/O and no model.
That is the whole point. If a language model is asked whether a policy was
active on a date, or how much of a benefit limit remains, it will do date
arithmetic and subtraction in natural language and be wrong some fraction of
the time, fluently and with an explanation attached. In prior authorization
that is not a rounding error -- it is a member denied care because a model
subtracted 4,200 from 15,000 and got 9,800.

So the split is by the nature of the question, not by difficulty. Anything
that is a lookup, a comparison, a date interval or a sum is code. Only
reading prose and forming a judgment goes to a model.

Two conventions hold throughout:

* A rule that cannot find the record it needs returns UNKNOWN, never PASS.
  Absence of evidence is not evidence of eligibility.

* Every result carries the record identifiers and values it consulted in
  `evidence`, so the reviewer console can show "policy PLN-HMO-CORE,
  termination 07/31/2026" instead of an assertion the reviewer has to trust.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from packages.core.models import RuleOutcome, RuleReport, RuleResult
from packages.core.records import CaseFacts, MemberStatus, NetworkTier


def _unknown(rule_id: str, name: str, what: str) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        name=name,
        outcome=RuleOutcome.UNKNOWN,
        summary=f"Cannot evaluate: {what} could not be resolved.",
        evidence={"missing": what},
    )


# --------------------------------------------------------------------------
# R1 -- does this procedure require authorization at all?
# --------------------------------------------------------------------------


def r1_auth_required(facts: CaseFacts) -> RuleResult:
    """The fast path.

    PASS means authorization *is* required and the pipeline should continue.
    NOT_APPLICABLE means it is not, and the request exits here without an
    adjudication -- the provider is told they may proceed, and no
    authorization is created, because none was ever decided.

    Roughly a third of what arrives at a payer is this: a provider
    dutifully requesting authorization for an office visit or a metabolic
    panel that never needed one. Answering those in milliseconds without a
    model call is the cheapest win in the system.
    """
    if facts.procedure is None:
        return _unknown("R1", "Authorization required", "the procedure code")

    if facts.procedure.requires_preauth:
        return RuleResult(
            rule_id="R1",
            name="Authorization required",
            outcome=RuleOutcome.PASS,
            summary=f"CPT {facts.procedure.code} requires prior authorization.",
            evidence={"procedure_code": facts.procedure.code, "requires_preauth": "true"},
        )

    return RuleResult(
        rule_id="R1",
        name="Authorization required",
        outcome=RuleOutcome.NOT_APPLICABLE,
        summary=(
            f"CPT {facts.procedure.code} ({facts.procedure.description}) does "
            "not require prior authorization under this plan."
        ),
        evidence={"procedure_code": facts.procedure.code, "requires_preauth": "false"},
    )


# --------------------------------------------------------------------------
# R2 -- eligibility
# --------------------------------------------------------------------------


def r2_eligibility(facts: CaseFacts) -> RuleResult:
    name = "Member eligibility"
    if facts.member is None or facts.date_of_service is None:
        return _unknown("R2", name, "the member record or date of service")

    m, dos = facts.member, facts.date_of_service
    evidence: dict[str, str | int | float | None] = {
        "member_id": m.member_id,
        "status": m.status.value,
        "effective_date": m.effective_date.isoformat(),
        "termination_date": m.termination_date.isoformat() if m.termination_date else None,
        "date_of_service": dos.isoformat(),
    }

    if dos < m.effective_date:
        return RuleResult(
            rule_id="R2", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"Date of service {dos:%m/%d/%Y} precedes the coverage "
                f"effective date {m.effective_date:%m/%d/%Y}."
            ),
            evidence=evidence,
        )

    if m.termination_date and dos > m.termination_date:
        return RuleResult(
            rule_id="R2", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"Coverage terminated {m.termination_date:%m/%d/%Y}, before the "
                f"{dos:%m/%d/%Y} date of service."
            ),
            evidence=evidence,
        )

    if m.status == MemberStatus.SUSPENDED:
        paid = m.premium_paid_through
        evidence["premium_paid_through"] = paid.isoformat() if paid else None
        return RuleResult(
            rule_id="R2", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                "Policy is suspended for premium delinquency"
                + (f"; premiums paid through {paid:%m/%d/%Y}." if paid else ".")
            ),
            evidence=evidence,
        )

    if m.status != MemberStatus.ACTIVE:
        return RuleResult(
            rule_id="R2", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=f"Member status is {m.status.value}, not active.",
            evidence=evidence,
        )

    return RuleResult(
        rule_id="R2", name=name, outcome=RuleOutcome.PASS,
        summary=f"Coverage active on {dos:%m/%d/%Y}.",
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# R3 -- waiting period
# --------------------------------------------------------------------------


def r3_waiting_period(facts: CaseFacts) -> RuleResult:
    name = "Waiting period"
    if facts.member is None or facts.plan is None or facts.date_of_service is None:
        return _unknown("R3", name, "the member, plan, or date of service")

    m, plan, dos = facts.member, facts.plan, facts.date_of_service
    if plan.waiting_period_days == 0:
        return RuleResult(
            rule_id="R3", name=name, outcome=RuleOutcome.NOT_APPLICABLE,
            summary=f"{plan.name} carries no waiting period.",
            evidence={"plan_id": plan.plan_id, "waiting_period_days": 0},
        )

    elapsed = (dos - m.enrolled_at).days
    satisfied_on = m.enrolled_at + timedelta(days=plan.waiting_period_days)
    evidence: dict[str, str | int | float | None] = {
        "plan_id": plan.plan_id,
        "waiting_period_days": plan.waiting_period_days,
        "enrolled_at": m.enrolled_at.isoformat(),
        "days_elapsed": elapsed,
        "satisfied_on": satisfied_on.isoformat(),
    }

    if elapsed < plan.waiting_period_days:
        return RuleResult(
            rule_id="R3", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"Enrolled {m.enrolled_at:%m/%d/%Y}; only {elapsed} of the "
                f"plan's {plan.waiting_period_days}-day waiting period had "
                f"elapsed at the date of service. Benefits begin "
                f"{satisfied_on:%m/%d/%Y}."
            ),
            evidence=evidence,
        )

    return RuleResult(
        rule_id="R3", name=name, outcome=RuleOutcome.PASS,
        summary=f"Waiting period satisfied {satisfied_on:%m/%d/%Y}.",
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# R4 -- benefit coverage and exclusions
# --------------------------------------------------------------------------


def r4_benefit_coverage(facts: CaseFacts) -> RuleResult:
    """A contractual exclusion is decided here, before medical necessity.

    This ordering is deliberate and it matters: a persuasive clinical
    narrative must not be able to override a category the plan does not
    cover. The narrative may well establish that the service is medically
    appropriate -- it is still not a covered benefit.
    """
    name = "Benefit coverage"
    if facts.plan is None or facts.procedure is None:
        return _unknown("R4", name, "the plan or procedure record")

    plan, proc = facts.plan, facts.procedure
    evidence: dict[str, str | int | float | None] = {
        "plan_id": plan.plan_id,
        "procedure_code": proc.code,
        "category": proc.category,
        "excluded_categories": ", ".join(plan.excluded_categories) or None,
    }

    if proc.category in plan.excluded_categories:
        return RuleResult(
            rule_id="R4", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"The {proc.category.replace('_', ' ')} benefit category is "
                f"excluded under {plan.name}. The exclusion is contractual "
                "and is reached before medical necessity."
            ),
            evidence=evidence,
        )

    return RuleResult(
        rule_id="R4", name=name, outcome=RuleOutcome.PASS,
        summary=(
            f"{proc.category.replace('_', ' ').title()} is a covered category "
            f"under {plan.name}."
        ),
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# R5 -- area of cover
# --------------------------------------------------------------------------


def r5_area_of_cover(facts: CaseFacts) -> RuleResult:
    name = "Area of cover"
    if facts.plan is None or facts.provider is None:
        return _unknown("R5", name, "the plan or provider record")

    plan, prov = facts.plan, facts.provider
    evidence: dict[str, str | int | float | None] = {
        "plan_id": plan.plan_id,
        "provider_npi": prov.npi,
        "provider_state": prov.license_state,
        "covered_states": ", ".join(plan.covered_states),
    }

    if prov.license_state not in plan.covered_states:
        return RuleResult(
            rule_id="R5", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"Provider is located in {prov.license_state}; {plan.name} "
                f"covers services in {', '.join(plan.covered_states)}."
            ),
            evidence=evidence,
        )

    return RuleResult(
        rule_id="R5", name=name, outcome=RuleOutcome.PASS,
        summary=f"Provider state {prov.license_state} is within the plan service area.",
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# R6 -- provider standing
# --------------------------------------------------------------------------


def r6_provider_standing(facts: CaseFacts) -> RuleResult:
    """Sanctions, licensure, contract dates, and network tier.

    Checked in that order because a sanctioned provider is a harder problem
    than an out-of-network one, and the reviewer should see the most serious
    finding first rather than the first one that happened to fail.
    """
    name = "Provider standing"
    if facts.provider is None or facts.plan is None or facts.date_of_service is None:
        return _unknown("R6", name, "the provider, plan, or date of service")

    prov, plan, dos = facts.provider, facts.plan, facts.date_of_service
    evidence: dict[str, str | int | float | None] = {
        "provider_npi": prov.npi,
        "network_tier": prov.network_tier.value,
        "license_expiry": prov.license_expiry.isoformat(),
        "sanctioned": str(prov.sanctioned).lower(),
        "contract_start": prov.contract_start.isoformat(),
        "plan_requires_in_network": str(plan.requires_in_network).lower(),
    }

    if prov.sanctioned:
        return RuleResult(
            rule_id="R6", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary="Provider carries an active sanction and is not eligible for payment.",
            evidence=evidence,
        )

    if prov.license_expiry < dos:
        return RuleResult(
            rule_id="R6", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"Provider licence expired {prov.license_expiry:%m/%d/%Y}, "
                f"before the {dos:%m/%d/%Y} date of service."
            ),
            evidence=evidence,
        )

    if not prov.is_contracted_on(dos):
        return RuleResult(
            rule_id="R6", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=f"Provider was not under contract on {dos:%m/%d/%Y}.",
            evidence=evidence,
        )

    if plan.requires_in_network and prov.network_tier != NetworkTier.IN_NETWORK:
        return RuleResult(
            rule_id="R6", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"{plan.name} requires an in-network provider; this provider "
                f"is {prov.network_tier.value.replace('_', ' ')}."
            ),
            evidence=evidence,
        )

    return RuleResult(
        rule_id="R6", name=name, outcome=RuleOutcome.PASS,
        summary=(
            f"Provider is contracted, licensed through "
            f"{prov.license_expiry:%m/%d/%Y}, and in good standing."
        ),
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# R7 -- benefit limits
# --------------------------------------------------------------------------


def r7_benefit_limits(facts: CaseFacts, category: str, plan_year: int) -> RuleResult:
    """Three outcomes, not two.

    A request that exceeds the remaining balance is not a denial -- the
    member is entitled to the balance that remains. Collapsing partial
    entitlement into a denial is the single most common way an automated
    utilization system harms someone, so the partial case is a distinct,
    non-hard-stop failure that the assembler turns into a partial approval.
    """
    name = "Benefit limits"
    if facts.procedure is None or facts.member is None:
        return _unknown("R7", name, "the procedure or member record")

    acc = facts.accumulator_for(category, plan_year)
    if acc is None:
        return _unknown("R7", name, f"the {category} accumulator for plan year {plan_year}")

    cost = facts.procedure.unit_cost * Decimal(facts.units_requested)
    remaining = acc.remaining
    evidence: dict[str, str | int | float | None] = {
        "category": category,
        "plan_year": plan_year,
        "limit_amount": str(acc.limit_amount),
        "consumed_amount": str(acc.consumed_amount),
        "remaining": str(remaining),
        "requested_amount": str(cost),
    }

    if remaining <= 0:
        return RuleResult(
            rule_id="R7", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"The {category} benefit for plan year {plan_year} is fully "
                f"consumed ({acc.consumed_amount} of {acc.limit_amount}). No "
                "balance remains."
            ),
            evidence=evidence,
        )

    if remaining < cost:
        return RuleResult(
            rule_id="R7", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=False,
            summary=(
                f"Requested {cost} exceeds the remaining {category} balance of "
                f"{remaining}. Payable to the remaining balance; the member is "
                "responsible for the difference."
            ),
            evidence=evidence,
        )

    return RuleResult(
        rule_id="R7", name=name, outcome=RuleOutcome.PASS,
        summary=f"{remaining} remains in the {category} benefit against a request of {cost}.",
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# R8 -- duplicate authorization
# --------------------------------------------------------------------------


def r8_duplicate(facts: CaseFacts) -> RuleResult:
    name = "Duplicate authorization"
    if facts.procedure is None or facts.date_of_service is None:
        return _unknown("R8", name, "the procedure or date of service")

    dos, code = facts.date_of_service, facts.procedure.code
    existing = next((a for a in facts.prior_auths if a.covers(dos, code)), None)

    if existing:
        return RuleResult(
            rule_id="R8", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=True,
            summary=(
                f"Authorization {existing.auth_id} is already active for this "
                f"member and procedure, valid {existing.valid_from:%m/%d/%Y} "
                f"through {existing.valid_to:%m/%d/%Y}. The existing "
                "authorization should be used."
            ),
            evidence={
                "existing_auth_id": existing.auth_id,
                "valid_from": existing.valid_from.isoformat(),
                "valid_to": existing.valid_to.isoformat(),
                "units_approved": existing.units_approved,
            },
        )

    return RuleResult(
        rule_id="R8", name=name, outcome=RuleOutcome.PASS,
        summary="No active authorization covers this procedure and date.",
        evidence={"prior_auths_checked": len(facts.prior_auths)},
    )


# --------------------------------------------------------------------------
# R9 -- code coherence
# --------------------------------------------------------------------------


def r9_code_coherence(facts: CaseFacts) -> RuleResult:
    """Does the diagnosis plausibly support the procedure?

    A failure here is almost always a transcription error rather than a
    clinical dispute, so it is not a hard stop. The assembler turns it into
    a pend for correction, because denying a request over a mistyped
    diagnosis code creates an appeal for no reason.
    """
    name = "Code coherence"
    if facts.procedure is None:
        return _unknown("R9", name, "the procedure record")
    if not facts.diagnoses:
        return _unknown("R9", name, "a diagnosis code")

    submitted = [d.code for d in facts.diagnoses]
    valid = facts.valid_diagnosis_codes
    evidence: dict[str, str | int | float | None] = {
        "procedure_code": facts.procedure.code,
        "submitted_diagnoses": ", ".join(submitted),
        "supporting_diagnoses": ", ".join(valid) if valid else None,
    }

    if not valid:
        return _unknown("R9", name, f"the supported diagnosis list for {facts.procedure.code}")

    if any(code in valid for code in submitted):
        return RuleResult(
            rule_id="R9", name=name, outcome=RuleOutcome.PASS,
            summary=f"Diagnosis {submitted[0]} supports CPT {facts.procedure.code}.",
            evidence=evidence,
        )

    dx = facts.diagnoses[0]
    return RuleResult(
        rule_id="R9", name=name, outcome=RuleOutcome.FAIL, is_hard_stop=False,
        summary=(
            f"Diagnosis {dx.code} ({dx.description}) does not support CPT "
            f"{facts.procedure.code} ({facts.procedure.description}). This is "
            "usually a coding error; returned for correction."
        ),
        evidence=evidence,
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def evaluate(facts: CaseFacts, category: str, plan_year: int) -> RuleReport:
    """Run every rule and return the full report.

    All nine run even when an early one hard-stops. A reviewer looking at a
    denied case still wants to see whether the provider was in network and
    whether the benefit had room -- if the member appeals and wins on the
    eligibility point, the next question is immediately what else was wrong.
    Short-circuiting the *model* calls saves real money; short-circuiting the
    rules saves microseconds and costs the reviewer context.
    """
    return RuleReport(
        results=[
            r1_auth_required(facts),
            r2_eligibility(facts),
            r3_waiting_period(facts),
            r4_benefit_coverage(facts),
            r5_area_of_cover(facts),
            r6_provider_standing(facts),
            r7_benefit_limits(facts, category, plan_year),
            r8_duplicate(facts),
            r9_code_coherence(facts),
        ]
    )
