"""The verifier: an adversarial pass over the finished packet.

It runs in a fresh context with no memory of why the adjudicator believed
anything. That is the entire point -- an auditor who watched the reasoning
happen inherits its assumptions. This one sees only the claims and the
evidence, and asks whether the second supports the first.

A blocking finding does not overturn the determination. It routes the case
to a human, which is the correct response to "we cannot show our work".
"""

from __future__ import annotations

from pathlib import Path

from agents.client import ModelClient, extract_json
from packages.core.config import CRITIC_MODEL
from packages.core.models import (
    CriticFinding,
    CriticReport,
    NecessityJudgment,
    PolicyClause,
    RuleReport,
)
from packages.observability.ledger import CostLedger

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

STAGE = "verify"


def verify(
    *,
    client: ModelClient,
    ledger: CostLedger,
    rationale: str,
    rules: RuleReport,
    clauses: list[PolicyClause],
    necessity: NecessityJudgment | None,
    narrative: str,
    model: str = CRITIC_MODEL,
) -> CriticReport:
    user = _render(rationale, rules, clauses, necessity, narrative)
    raw = client.complete(
        stage=STAGE,
        model=model,
        system=PROMPT,
        messages=[{"role": "user", "content": user}],
        ledger=ledger,
        max_tokens=4000,
    )

    try:
        data = extract_json(raw)
    except ValueError:
        # A verifier that cannot be parsed must not read as "all clear".
        return CriticReport(
            findings=[
                CriticFinding(
                    severity="blocking",
                    claim="(verification output)",
                    problem="The verification pass returned unparseable output.",
                )
            ]
        )

    findings: list[CriticFinding] = []
    for item in data.get("findings", []):
        severity = str(item.get("severity", "advisory")).strip().lower()
        findings.append(
            CriticFinding(
                severity="blocking" if severity == "blocking" else "advisory",
                claim=str(item.get("claim", "")).strip()[:500],
                problem=str(item.get("problem", "")).strip()[:800],
            )
        )
    return CriticReport(findings=findings)


def _render(
    rationale: str,
    rules: RuleReport,
    clauses: list[PolicyClause],
    necessity: NecessityJudgment | None,
    narrative: str,
) -> str:
    rule_lines = []
    for r in rules.results:
        evidence = ", ".join(
            f"{k}={v}" for k, v in r.evidence.items() if v is not None
        )
        rule_lines.append(
            f"[{r.rule_id}] {r.name}: {r.outcome.value.upper()}\n"
            f"    {r.summary}\n"
            f"    evidence: {evidence or '(none)'}"
        )

    clause_block = "\n\n".join(f"[{c.clause_id}]\n{c.text}" for c in clauses) or "(none)"

    if necessity and necessity.assessments:
        nec_lines = [
            f"[{a.clause_id}] {a.status.value.upper()} -- {a.rationale}"
            for a in necessity.assessments
        ]
        nec_block = "\n".join(nec_lines)
    else:
        nec_block = "(no medical necessity assessment was made)"

    return f"""\
## Draft rationale under audit

{rationale.strip()}

## Deterministic rule results and the record values they read

{chr(10).join(rule_lines)}

## Policy clauses that were retrieved

{clause_block}

## Medical necessity assessment supplied

{nec_block}

## Clinical narrative as submitted

{narrative.strip()}

## Task

Audit the draft rationale against the evidence above. Return the JSON object
described in your instructions and nothing else."""
