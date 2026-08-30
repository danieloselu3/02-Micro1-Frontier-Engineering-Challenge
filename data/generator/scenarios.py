"""Case builders. One per failure mode the system must handle correctly.

Each builder constructs a request and mutates the population so that exactly
one thing is wrong (or nothing is), then emits the gold label naming the
verdict and the governing rule. Because the label is derived from the record
state the builder just created, it is correct by construction rather than by
annotation -- there is no hand-labelling step to get wrong.

Labels are computed here from record facts, deliberately without consulting
the policy prose the retriever will later see. If the rules engine and the
corpus ever disagree about a case, that is a real finding about the system,
not a bug to be quietly reconciled.
"""

from __future__ import annotations

import random
import zlib
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from data.generator import narratives as N
from data.generator.population import PLAN_YEAR, Population
from data.generator.reference import (
    PLANS_BY_ID,
    PROCEDURES_BY_CODE,
    accumulator_for_procedure,
    age_range_for,
    specialties_for,
)
from packages.core.labels import GeneratedCase, GoldLabel
from packages.core.models import DegradationTier, Verdict
from packages.core.records import (
    Member,
    MemberStatus,
    NetworkTier,
    PriorAuthorization,
    Provider,
)

DOS = date(2026, 8, 14)  # the date of service every case shares

Builder = Callable[["ScenarioContext"], GeneratedCase]


class ScenarioContext:
    """Everything a builder needs, plus the side-channel it writes back to."""

    def __init__(self, pop: Population, rng: random.Random, case_id: str) -> None:
        self.pop = pop
        self.rng = rng
        self.case_id = case_id
        #: Extra prior-authorization rows this case needs to exist.
        self.extra_prior_auths: list[PriorAuthorization] = []
        self.used_members: set[str] = set()


def _case(
    ctx: ScenarioContext,
    *,
    scenario: str,
    member: Member,
    provider: Provider,
    procedure_code: str,
    diagnosis_codes: list[str],
    narrative: str,
    verdict: Verdict,
    governing_rule: str,
    rationale: str,
    adversarial: bool = False,
    units: int = 1,
    dos: date = DOS,
    degradation: DegradationTier = DegradationTier.CLEAN,
    form_name: str | None = None,
    form_member_id: str | None = None,
    missing_info: list[str] | None = None,
    requires_human_review: bool = True,
) -> GeneratedCase:
    """Assemble a case and its label, defaulting the form to match the record.

    Two consistency repairs happen here rather than in each builder, because
    every builder funnels through this function and neither repair changes
    what the scenario is testing:

    * The member is re-dated if their age falls outside the plausible window
      for the procedure. The narrative states an age, and a form showing a
      19-year-old alongside a note describing a 52-year-old is an internal
      contradiction the adjudicator would be right to be confused by.

    * The provider's specialty is corrected to one that plausibly orders the
      service. A plastic surgeon requesting a lumbar MRI is noise the model
      would reasonably read as signal.
    """
    member = _fit_member_age(ctx, member, procedure_code, dos)
    provider = _fit_provider_specialty(ctx, provider, procedure_code)
    provider = _isolate_provider(ctx, provider)
    member, provider = _normalize(ctx, member, provider, procedure_code, dos, governing_rule)
    narrative = narrative.replace("{age}", str(member.age_on(dos)))

    printed_name = form_name or member.full_name
    printed_id = form_member_id or member.member_id
    printed_dos = dos.strftime("%m/%d/%Y")

    return GeneratedCase(
        case_id=ctx.case_id,
        scenario=scenario,
        member=member,
        provider=provider,
        procedure_code=procedure_code,
        diagnosis_codes=diagnosis_codes,
        date_of_service=dos,
        units_requested=units,
        clinical_narrative=narrative,
        form_member_name=printed_name,
        form_member_id=printed_id,
        form_provider_npi=provider.npi,
        form_date_of_service=printed_dos,
        label=GoldLabel(
            case_id=ctx.case_id,
            verdict=verdict,
            governing_rule=governing_rule,
            rationale=rationale,
            scenario=scenario,
            is_adversarial=adversarial,
            degradation=degradation,
            expected_fields={
                "member_name": printed_name,
                "member_id": printed_id,
                "provider_npi": provider.npi,
                "procedure_code": procedure_code,
                "diagnosis_code": diagnosis_codes[0] if diagnosis_codes else "",
                "date_of_service": printed_dos,
            },
            expected_missing_information=missing_info or [],
            requires_human_review=requires_human_review,
        ),
    )


def _fit_member_age(
    ctx: ScenarioContext, member: Member, code: str, dos: date
) -> Member:
    """Re-date the member so their age suits the procedure and its narrative."""
    lo, hi = age_range_for(code)
    if lo <= member.age_on(dos) <= hi:
        return member

    target = ctx.rng.randint(lo, hi)
    month, day = member.date_of_birth.month, min(member.date_of_birth.day, 28)
    # Subtract an extra year when the birthday falls later in the calendar
    # than the date of service, so age_on() lands exactly on the target.
    year = dos.year - target - (1 if (dos.month, dos.day) < (month, day) else 0)
    updated = member.model_copy(update={"date_of_birth": date(year, month, day)})
    ctx.pop.replace_member(updated)
    return updated


def _fit_provider_specialty(
    ctx: ScenarioContext, provider: Provider, code: str
) -> Provider:
    """Give the provider a specialty that plausibly orders this service."""
    allowed = specialties_for(code)
    if provider.specialty in allowed:
        return provider
    return provider.model_copy(update={"specialty": ctx.rng.choice(allowed)})


def _isolate_provider(ctx: ScenarioContext, provider: Provider) -> Provider:
    """Give this case its own provider record under a fresh NPI.

    Providers are drawn from a shared pool, and several scenarios damage the
    one they draw -- a sanction, an expired licence, an out-of-network tier.
    Without isolation that damage leaks into every later case that happens to
    draw the same provider, and the leak shows up as a denial on a rule the
    case was never meant to exercise.
    """
    npi = f"9{zlib.crc32(ctx.case_id.encode()) % 10**9:09d}"
    isolated = provider.model_copy(update={"npi": npi})
    ctx.pop.providers.append(isolated)
    return isolated


def _normalize(
    ctx: ScenarioContext,
    member: Member,
    provider: Provider,
    code: str,
    dos: date,
    governing_rule: str,
) -> tuple[Member, Provider]:
    """Repair every condition except the one this case exists to test.

    A scenario is only a clean experiment if exactly one thing is wrong. Left
    to chance, a case built to test medical necessity lands on a member whose
    waiting period has not elapsed, or a provider outside the plan's service
    area, and gets denied on a contractual rule before the clinical question
    is ever reached -- which would make the gold label wrong rather than the
    system.

    `governing_rule` names the rule the case is allowed to fail. Anything
    starting with MP- is a medical-necessity case, so every rule is repaired.
    """
    intended = governing_rule if governing_rule.startswith("R") else None
    plan = PLANS_BY_ID[member.plan_id]
    proc = PROCEDURES_BY_CODE[code]

    # R2 and R3 -- coverage active, and enrolled long enough ago.
    if intended not in ("R2", "R3"):
        enrolled = dos - timedelta(days=plan.waiting_period_days + 300)
        member = member.model_copy(
            update={
                "status": MemberStatus.ACTIVE,
                "enrolled_at": enrolled,
                "effective_date": enrolled,
                "termination_date": None,
                "premium_paid_through": date(dos.year, 12, 31),
            }
        )
        ctx.pop.replace_member(member)

    # R5 -- provider inside the plan's service area.
    if intended != "R5" and provider.license_state not in plan.covered_states:
        provider = provider.model_copy(update={"license_state": plan.covered_states[0]})

    # R6 -- provider contracted, licensed, unsanctioned, in network.
    if intended != "R6":
        provider = provider.model_copy(
            update={
                "network_tier": NetworkTier.IN_NETWORK,
                "sanctioned": False,
                "license_expiry": date(dos.year + 1, 6, 30),
                "contract_start": date(dos.year - 3, 1, 1),
                "contract_end": None,
            }
        )
    ctx.pop.replace_provider(provider)

    # R7 -- leave comfortably more benefit than the request consumes.
    if intended != "R7":
        category = accumulator_for_procedure(code)
        acc = ctx.pop.accumulator(member.member_id, category)
        headroom = proc.unit_cost * Decimal("2")
        if acc.remaining < headroom:
            ctx.pop.set_consumed(
                member.member_id,
                category,
                max(Decimal("0"), acc.limit_amount - headroom),
            )

    return member, provider


# ==========================================================================
# R1 -- the fast path: this procedure never needed authorization
# ==========================================================================


def no_auth_required(ctx: ScenarioContext) -> GeneratedCase:
    code = ctx.rng.choice(list(N.ROUTINE_BY_CODE))
    proc = PROCEDURES_BY_CODE[code]
    member = ctx.pop.any_member(ctx.used_members)
    from data.generator.reference import CODE_PAIRS

    return _case(
        ctx,
        scenario="no_auth_required",
        member=member,
        provider=ctx.pop.any_provider(),
        procedure_code=code,
        diagnosis_codes=[CODE_PAIRS[code][0]],
        narrative=N.ROUTINE_BY_CODE[code],
        verdict=Verdict.NO_AUTH_REQUIRED,
        governing_rule="R1",
        rationale=(
            f"CPT {code} ({proc.description}) does not require prior "
            "authorization under this plan. The provider may proceed; no "
            "authorization is issued because none was adjudicated."
        ),
        # The whole point of the fast path: this needs no clinician.
        requires_human_review=False,
    )


# ==========================================================================
# R2 -- eligibility
# ==========================================================================


def terminated_policy(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.any_member(ctx.used_members)
    member = member.model_copy(
        update={
            "status": MemberStatus.TERMINATED,
            "termination_date": DOS - timedelta(days=14),
        }
    )
    ctx.pop.replace_member(member)
    return _case(
        ctx,
        scenario="terminated_policy",
        member=member,
        provider=ctx.pop.any_provider(),
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.GENERIC_SUPPORTED,
        verdict=Verdict.DENIED,
        governing_rule="R2",
        rationale=(
            f"Coverage terminated {member.termination_date:%m/%d/%Y}, before "
            f"the {DOS:%m/%d/%Y} date of service."
        ),
        adversarial=True,
    )


def premium_delinquent(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.any_member(ctx.used_members)
    member = member.model_copy(
        update={
            "status": MemberStatus.SUSPENDED,
            "premium_paid_through": DOS - timedelta(days=45),
        }
    )
    ctx.pop.replace_member(member)
    return _case(
        ctx,
        scenario="premium_delinquent",
        member=member,
        provider=ctx.pop.any_provider(),
        procedure_code="29881",
        diagnosis_codes=["S83.241A"],
        narrative=N.GENERIC_SUPPORTED,
        verdict=Verdict.DENIED,
        governing_rule="R2",
        rationale=(
            "Policy suspended for premium delinquency; premiums paid only "
            f"through {member.premium_paid_through:%m/%d/%Y}."
        ),
        adversarial=True,
    )


# ==========================================================================
# R3 -- waiting period
# ==========================================================================


def within_waiting_period(ctx: ScenarioContext) -> GeneratedCase:
    # HMO Core carries a 90-day waiting period.
    member = ctx.pop.member_on_plan("PLN-HMO-CORE", ctx.used_members)
    enrolled = DOS - timedelta(days=30)
    member = member.model_copy(
        update={"enrolled_at": enrolled, "effective_date": enrolled}
    )
    ctx.pop.replace_member(member)
    return _case(
        ctx,
        scenario="within_waiting_period",
        member=member,
        provider=ctx.pop.any_provider(),
        procedure_code="27447",
        diagnosis_codes=["M17.11"],
        narrative=N.TKA_MET,
        verdict=Verdict.DENIED,
        governing_rule="R3",
        rationale=(
            f"Enrolled {enrolled:%m/%d/%Y}; the plan's 90-day waiting period "
            "had not elapsed at the date of service."
        ),
        adversarial=True,
    )


# ==========================================================================
# R4 -- benefit exclusion
# ==========================================================================


def excluded_cosmetic(ctx: ScenarioContext) -> GeneratedCase:
    """A cosmetic-category procedure on a plan that excludes the category.

    The narrative argues for functional necessity anyway, which is the point:
    a plan-level exclusion is decided before medical necessity is ever
    reached, and a system that lets a persuasive narrative override a
    contractual exclusion is broken.
    """
    member = ctx.pop.member_on_plan("PLN-EPO-VALUE", ctx.used_members)
    return _case(
        ctx,
        scenario="excluded_cosmetic",
        member=member,
        provider=ctx.pop.any_provider(),
        procedure_code="15823",
        diagnosis_codes=["H02.401"],
        narrative=N.BLEPH_FUNCTIONAL,
        verdict=Verdict.DENIED,
        governing_rule="R4",
        rationale=(
            "The cosmetic benefit category is excluded under Meridian EPO "
            "Value. The exclusion is contractual and is reached before "
            "medical necessity."
        ),
        adversarial=True,
    )


# ==========================================================================
# R5 -- area of cover
# ==========================================================================


def out_of_area(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.member_on_plan("PLN-HMO-CORE", ctx.used_members)
    provider = ctx.pop.any_provider().model_copy(update={"license_state": "PA"})
    return _case(
        ctx,
        scenario="out_of_area",
        member=member,
        provider=provider,
        procedure_code="74177",
        diagnosis_codes=["R10.9"],
        narrative=N.GENERIC_SUPPORTED,
        verdict=Verdict.DENIED,
        governing_rule="R5",
        rationale=(
            "Provider is located in PA; Meridian HMO Core covers services in "
            "OH only. Service falls outside the plan's area of cover."
        ),
        adversarial=True,
    )


# ==========================================================================
# R6 -- provider standing
# ==========================================================================


def out_of_network(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.member_on_plan("PLN-HMO-CORE", ctx.used_members)
    provider = ctx.pop.any_provider().model_copy(
        update={"network_tier": NetworkTier.OUT_OF_NETWORK, "license_state": member.state}
    )
    return _case(
        ctx,
        scenario="out_of_network",
        member=member,
        provider=provider,
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.MRI_LUMBAR_MET,
        verdict=Verdict.DENIED,
        governing_rule="R6",
        rationale=(
            "Meridian HMO Core requires in-network providers; this provider "
            "is out of network."
        ),
        adversarial=True,
    )


def provider_sanctioned(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.any_member(ctx.used_members)
    provider = ctx.pop.any_provider().model_copy(
        update={"sanctioned": True, "license_state": member.state}
    )
    return _case(
        ctx,
        scenario="provider_sanctioned",
        member=member,
        provider=provider,
        procedure_code="64483",
        diagnosis_codes=["M54.16"],
        narrative=N.GENERIC_SUPPORTED,
        verdict=Verdict.DENIED,
        governing_rule="R6",
        rationale="Provider carries an active sanction and is not eligible for payment.",
        adversarial=True,
    )


def license_expired(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.any_member(ctx.used_members)
    provider = ctx.pop.any_provider().model_copy(
        update={"license_expiry": DOS - timedelta(days=60), "license_state": member.state}
    )
    return _case(
        ctx,
        scenario="license_expired",
        member=member,
        provider=provider,
        procedure_code="29881",
        diagnosis_codes=["S83.241A"],
        narrative=N.GENERIC_SUPPORTED,
        verdict=Verdict.DENIED,
        governing_rule="R6",
        rationale=(
            f"Provider licence expired {provider.license_expiry:%m/%d/%Y}, "
            "before the date of service."
        ),
        adversarial=True,
    )


# ==========================================================================
# R7 -- benefit limits
# ==========================================================================


def limit_exhausted(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.any_member(ctx.used_members)
    category = accumulator_for_procedure("72148")
    acc = ctx.pop.accumulator(member.member_id, category)
    ctx.pop.set_consumed(member.member_id, category, acc.limit_amount)
    return _case(
        ctx,
        scenario="limit_exhausted",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.MRI_LUMBAR_MET,
        verdict=Verdict.DENIED,
        governing_rule="R7",
        rationale=(
            f"The {category} benefit for plan year {PLAN_YEAR} is fully "
            f"consumed ({acc.limit_amount} of {acc.limit_amount}). No "
            "balance remains."
        ),
        adversarial=True,
    )


def limit_partial(ctx: ScenarioContext) -> GeneratedCase:
    """Enough remains to cover part of the request but not all of it.

    The correct answer is a partial approval to the remaining balance, not a
    denial -- denying a service the member is partly entitled to is the
    single most common way an automated system harms someone.
    """
    member = ctx.pop.any_member(ctx.used_members)
    proc = PROCEDURES_BY_CODE["72148"]
    category = accumulator_for_procedure("72148")
    acc = ctx.pop.accumulator(member.member_id, category)
    remaining = (proc.unit_cost * Decimal("0.6")).quantize(Decimal("0.01"))
    ctx.pop.set_consumed(member.member_id, category, acc.limit_amount - remaining)
    return _case(
        ctx,
        scenario="limit_partial",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.MRI_LUMBAR_MET,
        verdict=Verdict.PARTIALLY_APPROVED,
        governing_rule="R7",
        rationale=(
            f"Approved to the remaining {category} balance of {remaining}; "
            f"the billed charge of {proc.unit_cost} exceeds it. The member is "
            "responsible for the difference."
        ),
        adversarial=True,
    )


# ==========================================================================
# R8 -- duplicate authorization
# ==========================================================================


def duplicate_authorization(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.any_member(ctx.used_members)
    provider = ctx.pop.any_provider().model_copy(update={"license_state": member.state})
    existing = PriorAuthorization(
        auth_id=f"AUTH-{ctx.case_id}",
        member_id=member.member_id,
        provider_npi=provider.npi,
        procedure_code="70553",
        valid_from=DOS - timedelta(days=20),
        valid_to=DOS + timedelta(days=40),
        status="active",
        units_approved=1,
    )
    ctx.extra_prior_auths.append(existing)
    return _case(
        ctx,
        scenario="duplicate_authorization",
        member=member,
        provider=provider,
        procedure_code="70553",
        diagnosis_codes=["G43.909"],
        narrative=N.GENERIC_SUPPORTED,
        verdict=Verdict.DENIED,
        governing_rule="R8",
        rationale=(
            f"Authorization {existing.auth_id} is already active for this "
            f"member and procedure through {existing.valid_to:%m/%d/%Y}. The "
            "existing authorization should be used."
        ),
        adversarial=True,
    )


# ==========================================================================
# R9 -- code coherence
# ==========================================================================


def code_mismatch(ctx: ScenarioContext) -> GeneratedCase:
    """A lumbar MRI ordered for an upper respiratory infection.

    This is a transcription error, not a clinical dispute, so the right
    answer is a pend for correction rather than a denial.
    """
    member = ctx.pop.any_member(ctx.used_members)
    return _case(
        ctx,
        scenario="code_mismatch",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["J06.9"],
        narrative=N.GENERIC_SUPPORTED,
        verdict=Verdict.PENDED,
        governing_rule="R9",
        rationale=(
            "Diagnosis J06.9 (acute upper respiratory infection) does not "
            "support CPT 72148 (MRI lumbar spine). Returned for correction "
            "of the diagnosis code rather than denied."
        ),
        missing_info=["A diagnosis code consistent with lumbar spine imaging"],
        adversarial=True,
    )


# ==========================================================================
# Medical necessity -- all deterministic rules pass, the model decides
# ==========================================================================


def necessity_met(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.any_member(ctx.used_members)
    return _case(
        ctx,
        scenario="necessity_met",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.MRI_LUMBAR_MET,
        verdict=Verdict.APPROVED,
        governing_rule="MP-IMG-001",
        rationale=(
            "All criteria in the lumbar MRI policy are documented: six weeks "
            "of conservative therapy, a focal neurologic deficit, prior plain "
            "radiographs, and a pending surgical consultation."
        ),
        requires_human_review=False,
    )


def necessity_met_tka(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.member_on_plan("PLN-PPO-GOLD", ctx.used_members)
    return _case(
        ctx,
        scenario="necessity_met_tka",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="27447",
        diagnosis_codes=["M17.11"],
        narrative=N.TKA_MET,
        verdict=Verdict.APPROVED,
        governing_rule="MP-ORT-001",
        # Above the auto-release cost ceiling, so a clinician signs it even
        # though every criterion is met.
        rationale=(
            "All arthroplasty criteria are documented, including grade 4 "
            "radiographic change and 14 months of failed conservative care. "
            "Cost exceeds the auto-release ceiling, so a reviewer signs."
        ),
    )


def necessity_unmet(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.any_member(ctx.used_members)
    return _case(
        ctx,
        scenario="necessity_unmet",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["M54.50"],
        narrative=N.MRI_LUMBAR_UNMET,
        verdict=Verdict.DENIED,
        governing_rule="MP-IMG-001",
        rationale=(
            "The record affirmatively states conservative therapy was not "
            "attempted, the neurologic examination is normal, and no red "
            "flags are present. Criteria are contradicted, not merely absent."
        ),
        adversarial=True,
    )


def necessity_no_evidence(ctx: ScenarioContext) -> GeneratedCase:
    """The narrative is silent on conservative therapy -- pend, do not deny.

    This is the case that separates a careful system from a careless one.
    Nothing contradicts the criteria; the documentation simply does not
    address one of them.
    """
    member = ctx.pop.any_member(ctx.used_members)
    return _case(
        ctx,
        scenario="necessity_no_evidence",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.MRI_LUMBAR_NO_EVIDENCE,
        verdict=Verdict.PENDED,
        governing_rule="MP-IMG-001",
        rationale=(
            "Neurologic findings and prior radiographs are documented, but "
            "the record does not address the required trial of conservative "
            "therapy. Nothing contradicts it -- the documentation is silent, "
            "so the correct action is to request it."
        ),
        missing_info=[
            "Documentation of at least six weeks of conservative therapy "
            "(physical therapy, NSAIDs, or activity modification) with dates"
        ],
        adversarial=True,
    )


def necessity_no_evidence_tka(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.member_on_plan("PLN-PPO-GOLD", ctx.used_members)
    return _case(
        ctx,
        scenario="necessity_no_evidence_tka",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="27447",
        diagnosis_codes=["M17.11"],
        narrative=N.TKA_NO_EVIDENCE,
        verdict=Verdict.PENDED,
        governing_rule="MP-ORT-001",
        rationale=(
            "No conservative management history and no weight-bearing "
            "radiographic grading are documented. Both are required and "
            "neither is contradicted."
        ),
        missing_info=[
            "Conservative management history with dates and outcomes",
            "Weight-bearing radiographs with Kellgren-Lawrence grading",
        ],
        adversarial=True,
    )


def necessity_borderline(ctx: ScenarioContext) -> GeneratedCase:
    """Genuinely ambiguous. A well-calibrated system escalates rather than
    guessing, and the label says so."""
    member = ctx.pop.member_on_plan("PLN-PPO-GOLD", ctx.used_members)
    return _case(
        ctx,
        scenario="necessity_borderline",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="64483",
        diagnosis_codes=["M54.16"],
        narrative=N.ESI_BORDERLINE,
        verdict=Verdict.PENDED,
        governing_rule="MP-PAI-001",
        rationale=(
            "Conservative therapy was partial and adherence inconsistent; "
            "the sensory findings are non-dermatomal and the imaging "
            "correlation is uncertain. The record supports neither a clean "
            "approval nor a defensible denial."
        ),
        adversarial=True,
    )


def cosmetic_functional_exception(ctx: ScenarioContext) -> GeneratedCase:
    """Cosmetic category, but on a plan whose exclusion admits a functional
    exception, and the narrative documents one. Should approve."""
    member = ctx.pop.member_on_plan("PLN-PPO-GOLD", ctx.used_members)
    return _case(
        ctx,
        scenario="cosmetic_functional_exception",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="15823",
        diagnosis_codes=["H53.489"],
        narrative=N.BLEPH_FUNCTIONAL,
        verdict=Verdict.DENIED,
        governing_rule="R4",
        rationale=(
            "Meridian PPO Gold excludes the cosmetic category outright. The "
            "documented visual-field deficit would satisfy the functional "
            "criteria, but the plan exclusion is reached first."
        ),
        adversarial=True,
    )


def cosmetic_purely_aesthetic(ctx: ScenarioContext) -> GeneratedCase:
    member = ctx.pop.member_on_plan("PLN-HMO-CORE", ctx.used_members)
    return _case(
        ctx,
        scenario="cosmetic_purely_aesthetic",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="15823",
        diagnosis_codes=["H02.401"],
        narrative=N.BLEPH_COSMETIC,
        verdict=Verdict.DENIED,
        governing_rule="R4",
        rationale=(
            "Cosmetic category excluded under the plan, and the record "
            "documents no functional impairment in any case."
        ),
    )


def always_review_specialty_drug(ctx: ScenarioContext) -> GeneratedCase:
    """Every rule passes and necessity is met -- and it still goes to a
    medical director, because of what it is."""
    member = ctx.pop.member_on_plan("PLN-PPO-GOLD", ctx.used_members)
    return _case(
        ctx,
        scenario="always_review_specialty_drug",
        member=member,
        provider=ctx.pop.any_provider().model_copy(
            update={"license_state": member.state, "specialty": "Medical Oncology"}
        ),
        procedure_code="J9310",
        diagnosis_codes=["C83.30"],
        narrative=N.GENERIC_SUPPORTED,
        verdict=Verdict.APPROVED,
        governing_rule="MP-ONC-001",
        rationale=(
            "Criteria are met, but rituximab is on the always-review list. "
            "A medical director signs regardless of how clean the case is."
        ),
    )


# ==========================================================================
# Extraction stress -- the record is fine, the paper is not
# ==========================================================================


def name_mismatch(ctx: ScenarioContext) -> GeneratedCase:
    """The surname on the form is misspelled. Resolution must still land on
    the right member, and must say how confident it is."""
    member = ctx.pop.any_member(ctx.used_members)
    garbled = member.last_name[:-1] + ("e" if not member.last_name.endswith("e") else "a")
    return _case(
        ctx,
        scenario="name_mismatch",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.MRI_LUMBAR_MET,
        verdict=Verdict.APPROVED,
        governing_rule="MP-IMG-001",
        rationale=(
            f"Surname printed as '{garbled}' against record "
            f"'{member.last_name}'; member id and date of birth both match, "
            "so the identity resolves. Criteria are met."
        ),
        form_name=f"{member.first_name} {garbled}",
        adversarial=True,
    )


def illegible_member_id(ctx: ScenarioContext) -> GeneratedCase:
    """A handwritten member id with one unreadable digit. The system must not
    guess -- it must resolve on the other identifiers or escalate."""
    member = ctx.pop.any_member(ctx.used_members)
    return _case(
        ctx,
        scenario="illegible_member_id",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.MRI_LUMBAR_MET,
        verdict=Verdict.APPROVED,
        governing_rule="MP-IMG-001",
        rationale=(
            "Member id is partially illegible on the form; identity resolves "
            "on name and date of birth. Criteria are met."
        ),
        degradation=DegradationTier.HANDWRITTEN,
        adversarial=True,
    )


def clean_approval_degraded(ctx: ScenarioContext) -> GeneratedCase:
    """An otherwise clean approval delivered by fax at low resolution.

    Same clinical content as necessity_met -- the only variable is document
    quality, which is what makes the per-tier extraction comparison fair.
    """
    member = ctx.pop.any_member(ctx.used_members)
    return _case(
        ctx,
        scenario="clean_approval_faxed",
        member=member,
        provider=ctx.pop.any_provider().model_copy(update={"license_state": member.state}),
        procedure_code="72148",
        diagnosis_codes=["M54.16"],
        narrative=N.MRI_LUMBAR_MET,
        verdict=Verdict.APPROVED,
        governing_rule="MP-IMG-001",
        rationale="Criteria met. Document delivered by fax at reduced resolution.",
        degradation=DegradationTier.FAX,
        requires_human_review=False,
    )


#: Every scenario, and how many cases to build from each. Scenarios that
#: exercise a distinct reasoning path get two so a single lucky or unlucky
#: model call cannot swing the category.
SCENARIOS: list[tuple[Builder, int]] = [
    (no_auth_required, 3),
    (terminated_policy, 2),
    (premium_delinquent, 1),
    (within_waiting_period, 2),
    (excluded_cosmetic, 2),
    (out_of_area, 2),
    (out_of_network, 2),
    (provider_sanctioned, 1),
    (license_expired, 1),
    (limit_exhausted, 2),
    (limit_partial, 2),
    (duplicate_authorization, 2),
    (code_mismatch, 2),
    (necessity_met, 3),
    (necessity_met_tka, 2),
    (necessity_unmet, 3),
    (necessity_no_evidence, 3),
    (necessity_no_evidence_tka, 2),
    (necessity_borderline, 2),
    (cosmetic_functional_exception, 1),
    (cosmetic_purely_aesthetic, 1),
    (always_review_specialty_drug, 2),
    (name_mismatch, 2),
    (illegible_member_id, 2),
    (clean_approval_degraded, 2),
]
