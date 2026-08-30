"""Scoring.

One decision shapes this whole module: **there is no single accuracy number.**

False approvals and false denials are not interchangeable. A wrong approval
costs the payer money and is recoverable at the claims stage. A wrong denial
delays someone's treatment, starts an appeal that takes weeks, and is not
recoverable in any sense that matters to the member. Reporting one blended
figure lets a system trade the second for the first invisibly -- and because
approvals are the majority class in the real world, that is exactly the trade
an optimiser will make.

So the two are always reported separately, and the report leads with the one
that harms people.

The second decision: a right verdict reached by citing the wrong rule scores
as a miss. In prior authorization the reason is the product. A denial that
cites the wrong clause will not survive appeal, and a member cannot act on a
determination whose stated basis is false.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from agents.intake_extractor.agent import CRITICAL_FIELDS
from packages.core.labels import GeneratedCase
from packages.core.models import ExtractedRequest, Verdict

#: Verdicts that authorize care, in whole or in part.
PERMISSIVE = {Verdict.APPROVED, Verdict.PARTIALLY_APPROVED, Verdict.NO_AUTH_REQUIRED}


@dataclass
class CaseScore:
    case_id: str
    scenario: str
    degradation: str
    adversarial: bool

    expected_verdict: str
    actual_verdict: str
    expected_rule: str
    actual_rule: str

    verdict_correct: bool
    rule_correct: bool
    false_approval: bool
    false_denial: bool

    fields_correct: int = 0
    fields_total: int = 0
    field_errors: list[str] = field(default_factory=list)

    expected_human_review: bool = True
    actual_human_review: bool = True

    blocking_findings: int = 0
    cost_usd: str = "0"
    latency_s: float = 0.0
    model_calls: int = 0
    exit_stage: str = "complete"
    error: str | None = None


def score_case(
    *,
    case: GeneratedCase,
    verdict: Verdict,
    governing_rule: str,
    extraction: ExtractedRequest | None = None,
    requires_human_review: bool = True,
    blocking_findings: int = 0,
    cost_usd: Decimal = Decimal("0"),
    latency_s: float = 0.0,
    model_calls: int = 0,
    exit_stage: str = "complete",
    error: str | None = None,
) -> CaseScore:
    gold = case.label
    verdict_correct = verdict == gold.verdict

    # A denial issued where the gold verdict authorizes care, pends for
    # information, or needs no authorization at all.
    false_denial = verdict == Verdict.DENIED and gold.verdict != Verdict.DENIED

    # Care authorized where the gold verdict denies it.
    false_approval = verdict in PERMISSIVE and gold.verdict == Verdict.DENIED

    correct_fields, total_fields, errors = _score_fields(case, extraction)

    return CaseScore(
        case_id=case.case_id,
        scenario=case.scenario,
        degradation=gold.degradation.value,
        adversarial=gold.is_adversarial,
        expected_verdict=gold.verdict.value,
        actual_verdict=verdict.value,
        expected_rule=gold.governing_rule,
        actual_rule=governing_rule,
        verdict_correct=verdict_correct,
        rule_correct=verdict_correct and governing_rule == gold.governing_rule,
        false_approval=false_approval,
        false_denial=false_denial,
        fields_correct=correct_fields,
        fields_total=total_fields,
        field_errors=errors,
        expected_human_review=gold.requires_human_review,
        actual_human_review=requires_human_review,
        blocking_findings=blocking_findings,
        cost_usd=str(cost_usd),
        latency_s=round(latency_s, 2),
        model_calls=model_calls,
        exit_stage=exit_stage,
        error=error,
    )


def _score_fields(
    case: GeneratedCase, extraction: ExtractedRequest | None
) -> tuple[int, int, list[str]]:
    """Exact match on the six fields that drive the decision.

    Case and surrounding whitespace are normalised; nothing else is. A member
    id off by one character is wrong, because it resolves to a different
    person or to nobody.
    """
    if extraction is None:
        return 0, 0, []

    correct = 0
    errors: list[str] = []
    expected = case.label.expected_fields

    for name in CRITICAL_FIELDS:
        want = (expected.get(name) or "").strip()
        if not want:
            continue
        got = (extraction.value(name) or "").strip()
        if got.casefold() == want.casefold():
            correct += 1
        else:
            errors.append(f"{name}: expected {want!r}, read {got!r}")

    total = sum(1 for n in CRITICAL_FIELDS if (expected.get(n) or "").strip())
    return correct, total, errors


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def summarise(scores: list[CaseScore]) -> dict:
    n = len(scores)
    if not n:
        return {}

    fields_correct = sum(s.fields_correct for s in scores)
    fields_total = sum(s.fields_total for s in scores)

    escalated = [s for s in scores if s.actual_human_review]
    needed = [s for s in scores if s.expected_human_review]
    correctly_escalated = [s for s in escalated if s.expected_human_review]

    return {
        "cases": n,
        "verdict_accuracy": _pct(sum(s.verdict_correct for s in scores), n),
        "reason_accuracy": _pct(sum(s.rule_correct for s in scores), n),
        "false_denial_rate": _pct(sum(s.false_denial for s in scores), n),
        "false_denials": sum(s.false_denial for s in scores),
        "false_approval_rate": _pct(sum(s.false_approval for s in scores), n),
        "false_approvals": sum(s.false_approval for s in scores),
        "field_accuracy": _pct(fields_correct, fields_total) if fields_total else None,
        "fields_correct": fields_correct,
        "fields_total": fields_total,
        "escalation_precision": (
            _pct(len(correctly_escalated), len(escalated)) if escalated else None
        ),
        "escalation_recall": _pct(len(correctly_escalated), len(needed)) if needed else None,
        "auto_released": sum(1 for s in scores if not s.actual_human_review),
        "blocking_findings": sum(s.blocking_findings for s in scores),
        "total_cost_usd": round(sum(float(s.cost_usd) for s in scores), 4),
        "mean_cost_usd": round(sum(float(s.cost_usd) for s in scores) / n, 6),
        "mean_latency_s": round(sum(s.latency_s for s in scores) / n, 2),
        "total_model_calls": sum(s.model_calls for s in scores),
        "cases_with_no_model_call": sum(1 for s in scores if s.model_calls == 0),
        "errors": sum(1 for s in scores if s.error),
    }


def by_scenario(scores: list[CaseScore]) -> dict[str, dict]:
    groups: dict[str, list[CaseScore]] = {}
    for s in scores:
        groups.setdefault(s.scenario, []).append(s)
    return {
        name: {
            "cases": len(group),
            "verdict_accuracy": _pct(sum(s.verdict_correct for s in group), len(group)),
            "reason_accuracy": _pct(sum(s.rule_correct for s in group), len(group)),
            "false_denials": sum(s.false_denial for s in group),
            "false_approvals": sum(s.false_approval for s in group),
        }
        for name, group in sorted(groups.items())
    }


def by_degradation(scores: list[CaseScore]) -> dict[str, dict]:
    """Extraction accuracy per document tier.

    Reported separately because a single averaged figure hides which document
    condition the system actually falls over on -- which is the number an
    operations team would use to decide whether to keep accepting faxes.
    """
    groups: dict[str, list[CaseScore]] = {}
    for s in scores:
        groups.setdefault(s.degradation, []).append(s)

    out = {}
    for name, group in sorted(groups.items()):
        correct = sum(s.fields_correct for s in group)
        total = sum(s.fields_total for s in group)
        out[name] = {
            "cases": len(group),
            "field_accuracy": _pct(correct, total) if total else None,
            "fields_correct": correct,
            "fields_total": total,
            "verdict_accuracy": _pct(sum(s.verdict_correct for s in group), len(group)),
        }
    return out


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 1) if denominator else 0.0
