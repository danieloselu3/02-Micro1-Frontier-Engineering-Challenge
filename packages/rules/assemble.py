"""Turn a rule report and a necessity judgment into a verdict.

The model never picks the verdict. It contributes a structured assessment of
which policy criteria the documentation supports; this module combines that
with the deterministic rule results under a fixed precedence order. The
ordering is the policy, it is written down here, and it is testable.

Precedence, highest first:

  1. No authorization required     -- exit before anything else is considered
  2. Any rule UNKNOWN              -- we do not guess; pend
  3. Any hard-stop rule failure    -- contractual or eligibility denial
  4. Code incoherence              -- pend for correction, never deny
  5. Medical necessity             -- the only place judgment enters
  6. Partial benefit balance       -- caps an otherwise-approved request

Two orderings in there carry most of the safety argument. A contractual
exclusion outranks medical necessity, so a persuasive narrative cannot buy
coverage the plan does not sell. And a coding error outranks a denial, so a
mistyped diagnosis produces a correction request rather than an adverse
determination the member has to appeal.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from packages.core.config import (
    AUTO_RELEASE_COST_CEILING,
    FIELD_CONFIDENCE_FLOOR,
    NECESSITY_CONFIDENCE_FLOOR,
)
from packages.core.models import (
    CriticReport,
    Determination,
    ExtractedRequest,
    NecessityJudgment,
    PolicyClause,
    RuleOutcome,
    RuleReport,
    Verdict,
)
from packages.core.records import CaseFacts

#: Hard stops are reported in this order, so the reviewer sees the most
#: fundamental problem first rather than whichever rule happens to run first.
#: Eligibility precedes everything: if there was no coverage, nothing else
#: about the request matters.
HARD_STOP_PRIORITY = ["R2", "R3", "R4", "R5", "R6", "R8", "R7"]


def assemble(
    *,
    determination_id: str,
    submission_id: str,
    rules: RuleReport,
    facts: CaseFacts,
    necessity: NecessityJudgment | None = None,
    clauses: list[PolicyClause] | None = None,
    critic: CriticReport | None = None,
    extraction: ExtractedRequest | None = None,
    model_cost_usd: Decimal = Decimal("0"),
    elapsed_seconds: float = 0.0,
) -> Determination:
    verdict, governing, reason, missing, units, amount = _decide(rules, facts, necessity)

    det = Determination(
        determination_id=determination_id,
        submission_id=submission_id,
        verdict=verdict,
        governing_rule=governing,
        reason=reason,
        approved_units=units,
        approved_amount=amount,
        missing_information=missing,
        rule_report=rules,
        necessity=necessity,
        critic=critic,
        retrieved_clauses=clauses or [],
        created_at=datetime.now().astimezone(),
        model_cost_usd=model_cost_usd,
        elapsed_seconds=elapsed_seconds,
    )
    apply_release_gate(det, facts, extraction)
    return det


def _decide(
    rules: RuleReport,
    facts: CaseFacts,
    necessity: NecessityJudgment | None,
) -> tuple[Verdict, str, str, list[str], int | None, Decimal | None]:
    # -- 1. no authorization required -------------------------------------
    r1 = rules.get("R1")
    if r1 and r1.outcome == RuleOutcome.NOT_APPLICABLE:
        return (
            Verdict.NO_AUTH_REQUIRED,
            "R1",
            (
                f"{r1.summary} The provider may proceed with the service. No "
                "authorization number is issued, because no authorization was "
                "adjudicated -- this notice confirms none is needed."
            ),
            [],
            None,
            None,
        )

    # -- 2. anything we could not determine -------------------------------
    if rules.unknowns:
        first = rules.unknowns[0]
        return (
            Verdict.PENDED,
            first.rule_id,
            (
                f"{first.summary} The request cannot be adjudicated until this "
                "is resolved."
            ),
            [str(first.evidence.get("missing", "the missing record"))],
            None,
            None,
        )

    # -- 3. hard stops ----------------------------------------------------
    hard = [r for r in rules.failures if r.is_hard_stop]
    if hard:
        chosen = min(hard, key=lambda r: HARD_STOP_PRIORITY.index(r.rule_id))
        return Verdict.DENIED, chosen.rule_id, chosen.summary, [], None, None

    # -- 4. coding errors pend, they do not deny --------------------------
    r9 = rules.get("R9")
    if r9 and r9.outcome == RuleOutcome.FAIL:
        return (
            Verdict.PENDED,
            "R9",
            r9.summary,
            ["A diagnosis code consistent with the requested procedure"],
            None,
            None,
        )

    # -- 5. medical necessity ---------------------------------------------
    policy_id = facts.procedure.policy_document_id if facts.procedure else None
    governing = policy_id or "MP-UNSPECIFIED"

    if necessity is None or not necessity.assessments:
        # No judgment means no basis to approve. An empty assessment must
        # never read as satisfied -- that would let a retrieval failure
        # silently authorize care.
        return (
            Verdict.PENDED,
            governing,
            (
                "Medical necessity could not be assessed against the "
                "applicable policy criteria. Clinical review is required."
            ),
            ["A medical necessity assessment against the applicable policy"],
            None,
            None,
        )

    if necessity.any_unmet:
        unmet = [a for a in necessity.assessments if a.status.value == "unmet"]
        detail = " ".join(a.rationale for a in unmet[:2])
        return (
            Verdict.DENIED,
            unmet[0].clause_id,
            (
                f"The documentation does not meet {len(unmet)} of the "
                f"{len(necessity.assessments)} criteria in {governing}. {detail}"
            ),
            [],
            None,
            None,
        )

    if necessity.missing_evidence:
        gaps = necessity.missing_evidence
        return (
            Verdict.PENDED,
            gaps[0].clause_id,
            (
                f"The record does not address {len(gaps)} of the "
                f"{len(necessity.assessments)} criteria in {governing}. "
                "Nothing in the documentation contradicts them, so the request "
                "is returned for the missing information rather than denied."
            ),
            [a.criterion_text for a in gaps],
            None,
            None,
        )

    # -- 6. approved, possibly capped by the remaining balance ------------
    r7 = rules.get("R7")
    if r7 and r7.outcome == RuleOutcome.FAIL:
        remaining = Decimal(str(r7.evidence.get("remaining", "0")))
        return (
            Verdict.PARTIALLY_APPROVED,
            "R7",
            (
                f"Criteria in {governing} are met. {r7.summary}"
            ),
            [],
            facts.units_requested,
            remaining,
        )

    cost = (
        facts.procedure.unit_cost * Decimal(facts.units_requested)
        if facts.procedure
        else None
    )
    return (
        Verdict.APPROVED,
        governing,
        (
            f"All {len(necessity.assessments)} criteria in {governing} are "
            f"documented. {necessity.summary}".strip()
        ),
        [],
        facts.units_requested,
        cost,
    )


# --------------------------------------------------------------------------
# Release gate
# --------------------------------------------------------------------------


def apply_release_gate(
    det: Determination,
    facts: CaseFacts,
    extraction: ExtractedRequest | None = None,
) -> None:
    """Decide whether this determination may issue without a clinician.

    This is a policy, not a model. It sets `requires_human_review` and
    records every reason it did so, which is what the reviewer console shows
    at the top of the queue.

    The governing asymmetry: a wrong approval costs the payer money, a wrong
    denial delays someone's care. So approvals may auto-release under narrow
    conditions and denials never may.
    """
    reasons: list[str] = []

    # No-auth-required exits without review. Nothing was adjudicated, no
    # benefit was granted, and there is no adverse action to sign.
    if det.verdict == Verdict.NO_AUTH_REQUIRED:
        det.requires_human_review = False
        det.auto_released = True
        det.escalation_reasons = []
        return

    if det.verdict == Verdict.DENIED:
        reasons.append(
            "Denials are always reviewed by a clinician before they are issued."
        )
    if det.verdict == Verdict.PENDED:
        reasons.append("Requests for additional information are confirmed by a reviewer.")
    if det.verdict == Verdict.PARTIALLY_APPROVED:
        reasons.append("Partial approvals are confirmed by a reviewer.")

    if facts.procedure and facts.procedure.always_review:
        reasons.append(
            f"CPT {facts.procedure.code} is on the always-review list "
            "and requires a medical director."
        )

    if det.rule_report and det.rule_report.unknowns:
        names = ", ".join(r.rule_id for r in det.rule_report.unknowns)
        reasons.append(f"Undetermined checks: {names}.")

    if det.necessity and det.necessity.confidence < NECESSITY_CONFIDENCE_FLOOR:
        reasons.append(
            f"Necessity confidence {det.necessity.confidence:.2f} is below the "
            f"{NECESSITY_CONFIDENCE_FLOOR:.2f} threshold."
        )
    if det.necessity and det.necessity.uncertainties:
        reasons.append(
            f"The assessment flagged {len(det.necessity.uncertainties)} "
            "point(s) of uncertainty."
        )

    if det.critic and not det.critic.is_clean:
        blocking = [f for f in det.critic.findings if f.severity == "blocking"]
        reasons.append(
            f"Verification found {len(blocking)} unsupported claim(s) in the rationale."
        )

    if extraction:
        weak = extraction.low_confidence(FIELD_CONFIDENCE_FLOOR)
        if weak:
            reasons.append(
                f"Fields read below the confidence floor: {', '.join(sorted(weak))}."
            )

    if det.approved_amount is not None and det.approved_amount > AUTO_RELEASE_COST_CEILING:
        reasons.append(
            f"Approved amount {det.approved_amount} exceeds the "
            f"{AUTO_RELEASE_COST_CEILING} auto-release ceiling."
        )

    det.escalation_reasons = reasons
    det.requires_human_review = bool(reasons)
    det.auto_released = not reasons
