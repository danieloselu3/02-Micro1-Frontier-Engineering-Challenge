"""The adjudicator: the only agent permitted to form an opinion.

It receives the complete criteria list for the governing policy and the
clinical narrative, and returns a per-criterion assessment. It does not
return a verdict -- that is assembled in code from this plus the rule
report, under a precedence order that is written down and tested.

Note what is deliberately absent from its context: the member record, the
benefit balances, the network status, the eligibility dates. Those are
settled before this runs, and feeding them in would invite the model to
re-litigate arithmetic that is already correct, and to let a lapsed policy
colour a clinical judgment that should be independent of it.
"""

from __future__ import annotations

from pathlib import Path

from agents.client import ModelClient, extract_json
from packages.core.config import ADJUDICATION_MODEL
from packages.core.models import (
    CriterionAssessment,
    CriterionStatus,
    NecessityJudgment,
    PolicyClause,
)
from packages.observability.ledger import CostLedger

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

STAGE = "adjudicate"


def judge_necessity(
    *,
    client: ModelClient,
    ledger: CostLedger,
    clauses: list[PolicyClause],
    narrative: str,
    procedure_code: str,
    procedure_description: str,
    diagnosis: str,
    model: str = ADJUDICATION_MODEL,
) -> NecessityJudgment:
    if not clauses:
        # No criteria means no basis to assess, and an empty judgment must
        # never read as satisfied -- the assembler turns this into a pend.
        return NecessityJudgment(
            assessments=[],
            summary="No policy criteria were retrieved for this procedure.",
            confidence=0.0,
            uncertainties=["The governing medical policy could not be identified."],
        )

    user = _render(clauses, narrative, procedure_code, procedure_description, diagnosis)
    raw = client.complete(
        stage=STAGE,
        model=model,
        system=PROMPT,
        messages=[{"role": "user", "content": user}],
        ledger=ledger,
        max_tokens=3000,
    )
    return _parse(raw, clauses)


def _render(
    clauses: list[PolicyClause],
    narrative: str,
    code: str,
    description: str,
    diagnosis: str,
) -> str:
    criteria = "\n\n".join(
        f"[{c.clause_id}]\n{c.text}" for c in clauses
    )
    return f"""\
## Request

Procedure: CPT {code} — {description}
Diagnosis: {diagnosis}

## Governing policy criteria

{criteria}

## Clinical documentation as submitted

{narrative.strip()}

## Task

Assess each criterion above against the documentation. Return the JSON object
described in your instructions and nothing else."""


def _parse(raw: str, clauses: list[PolicyClause]) -> NecessityJudgment:
    """Parse the response, discarding anything not grounded in the criteria.

    A citation to a clause that was never retrieved is dropped rather than
    trusted. This is a hard boundary: the assessment may only speak about
    criteria it was actually shown, and a fabricated clause id would
    otherwise flow straight into a determination letter.
    """
    data = extract_json(raw)
    known = {c.clause_id for c in clauses}

    assessments: list[CriterionAssessment] = []
    for item in data.get("assessments", []):
        clause_id = str(item.get("clause_id", ""))
        if clause_id not in known:
            continue
        try:
            status = CriterionStatus(str(item.get("status", "")).strip().lower())
        except ValueError:
            # An unrecognised status is treated as unassessed rather than
            # guessed at, which pends the case instead of deciding it.
            status = CriterionStatus.NO_EVIDENCE

        support = item.get("narrative_support")
        assessments.append(
            CriterionAssessment(
                clause_id=clause_id,
                criterion_text=str(item.get("criterion_text", ""))[:400],
                status=status,
                rationale=str(item.get("rationale", "")).strip(),
                narrative_support=(
                    str(support).strip() if support and status == CriterionStatus.MET else None
                ),
            )
        )

    confidence = _clamp(data.get("confidence", 0.0))
    uncertainties = [str(u).strip() for u in data.get("uncertainties", []) if str(u).strip()]

    # A criterion the model simply omitted is not satisfied. Fill the gap
    # rather than letting a short response read as a clean bill of health.
    seen = {a.clause_id for a in assessments}
    for clause in clauses:
        if clause.clause_id not in seen:
            assessments.append(
                CriterionAssessment(
                    clause_id=clause.clause_id,
                    criterion_text=clause.text[:200],
                    status=CriterionStatus.NO_EVIDENCE,
                    rationale="The assessment did not address this criterion.",
                )
            )
            uncertainties.append(
                f"Criterion {clause.clause_id} was not assessed and is treated "
                "as unaddressed."
            )

    return NecessityJudgment(
        assessments=assessments,
        summary=str(data.get("summary", "")).strip(),
        confidence=confidence,
        uncertainties=uncertainties,
    )


def _clamp(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
