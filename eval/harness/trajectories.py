"""Export agent trajectories.

    python -m eval.harness.trajectories

Runs the pipeline in replay mode with the model client instrumented, and
writes one readable trace per representative case to `trajectories/`.

A trajectory here is the whole story of a case, not just the model calls:
the deterministic stages between them are what shape each prompt, so they
are recorded as steps too. Reading one top to bottom should answer "why did
the agent say that" without needing the source.

Costs nothing -- everything comes from the committed response cache.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from agents import client as client_module
from agents.client import ModelClient
from eval.harness.run import document_for, load_cases
from packages.core.labels import GeneratedCase
from packages.core.models import Submission, SubmissionChannel
from packages.core.repository import ClaimsRepository, connect
from packages.observability.ledger import CostLedger
from packages.orchestrator.pipeline import adjudicate, build_retriever

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "trajectories"
console = Console()

#: One case per distinct path through the system. Chosen to cover the
#: branches, the retry, a human checkpoint, and a case the system gets
#: wrong -- a trajectory set that only shows successes is marketing.
REPRESENTATIVE: dict[str, str] = {
    "CASE-001": (
        "Fast path — the procedure needs no authorization. One model call, "
        "exits before retrieval."
    ),
    "CASE-004": (
        "Hard stop — coverage terminated. Extraction only; no adjudication "
        "is ever paid for."
    ),
    "CASE-025": (
        "Full path — every rule passes and the criteria are met, then the "
        "case is escalated on the model's own stated uncertainty."
    ),
    "CASE-021": (
        "A duplicate authorization is already on file. The baseline got "
        "this one wrong."
    ),
    "CASE-033": (
        "The documentation is silent on a criterion, so it pends for the "
        "missing note rather than denying."
    ),
    "CASE-046": (
        "Handwritten member id. Extraction retries, still refuses to guess "
        "the smudged digit, and identity resolves on name and date of birth."
    ),
    "CASE-034": "A case the system gets WRONG: denied where a pend was correct.",
}


@dataclass
class Step:
    n: int
    kind: str  # "model" | "deterministic"
    stage: str
    detail: str
    request: str | None = None
    response: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


@dataclass
class Trace:
    case_id: str
    steps: list[Step] = field(default_factory=list)
    n: int = 0

    def add(self, **kw) -> None:
        self.n += 1
        self.steps.append(Step(n=self.n, **kw))


# --------------------------------------------------------------------------
# Instrumentation
# --------------------------------------------------------------------------


def instrument(trace_holder: dict) -> None:
    """Wrap ModelClient.complete so every exchange lands in the current trace."""
    original = ModelClient.complete

    def wrapped(self, *, stage, model, system, messages, ledger, max_tokens=4096):
        text = original(
            self,
            stage=stage,
            model=model,
            system=system,
            messages=messages,
            ledger=ledger,
            max_tokens=max_tokens,
        )
        trace: Trace | None = trace_holder.get("current")
        if trace is not None:
            call = ledger.calls[-1] if ledger.calls else None
            trace.add(
                kind="model",
                stage=stage,
                detail=_stage_detail(stage),
                request=_render_messages(messages),
                response=text,
                model=model,
                input_tokens=call.input_tokens if call else 0,
                output_tokens=call.output_tokens if call else 0,
                seconds=call.seconds if call else 0.0,
            )
        return text

    ModelClient.complete = wrapped


def _stage_detail(stage: str) -> str:
    return {
        "extract": "intake_extractor reads the page and reports per-field confidence",
        "extract_reread": (
            "RETRY — fields below the confidence threshold are read again, "
            "on an enlarged image"
        ),
        "adjudicate": "adjudicator judges the clinical narrative against the retrieved criteria",
        "verify": "reviewer_critic audits the drafted rationale against the evidence supplied",
        "baseline": "single-prompt comparator",
    }.get(stage, stage)


def _render_messages(messages: list[dict]) -> str:
    """Flatten the message payload, replacing image blobs with a note.

    Inlining a base64 page would make the trace unreadable and enormous
    without telling anyone anything they cannot see by opening the document.
    """
    out: list[str] = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            out.append(content)
            continue
        for block in content:
            if block.get("type") == "image":
                size = len(block["source"]["data"]) * 3 // 4
                out.append(
                    f"[page image, {size // 1024} KB PNG — see the case document]"
                )
            elif block.get("type") == "text":
                out.append(block["text"])
    return "\n\n".join(out)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render(case: GeneratedCase, trace: Trace, result, why: str) -> str:
    det = result.determination
    gold = case.label
    correct = det.verdict == gold.verdict

    L: list[str] = []
    L.append(f"# {case.case_id} — {case.scenario}\n")
    L.append(f"> {why}\n")

    L.append("## Outcome\n")
    L.append("| | |")
    L.append("|---|---|")
    L.append(f"| Produced | **{det.verdict.value}** citing `{det.governing_rule}` |")
    L.append(f"| Gold label | **{gold.verdict.value}** citing `{gold.governing_rule}` |")
    L.append(f"| Correct | {'yes' if correct else '**NO**'} |")
    routed = "yes" if det.requires_human_review else "no — auto-released"
    L.append(f"| Routed to a clinician | {routed} |")
    L.append(f"| Model calls | {len([s for s in trace.steps if s.kind == 'model'])} |")
    L.append(f"| Cost | ${det.model_cost_usd} |")
    L.append(f"| Document condition | {gold.degradation.value} |")
    L.append("")

    if det.escalation_reasons:
        L.append("**Why a human was required**\n")
        for r in det.escalation_reasons:
            L.append(f"- {r}")
        L.append("")

    L.append("## Agent instructions\n")
    L.append(
        "The system prompts are version-controlled and are not repeated here:\n"
    )
    L.append("- `agents/intake_extractor/prompt.md`")
    L.append("- `agents/adjudicator/prompt.md`")
    L.append("- `agents/reviewer_critic/prompt.md`\n")

    L.append("## Trajectory\n")
    for s in trace.steps:
        if s.kind == "model":
            L.append(f"### Step {s.n} — `{s.stage}` (model)\n")
            L.append(f"*{s.detail}*\n")
            L.append(
                f"`{s.model}` · {s.input_tokens} in / {s.output_tokens} out · "
                f"{s.seconds:.1f}s\n"
            )
            L.append("<details><summary>Prompt sent</summary>\n")
            L.append("```text")
            L.append(_clip(s.request or "", 6000))
            L.append("```\n</details>\n")
            L.append("<details open><summary>Response</summary>\n")
            L.append("```json")
            L.append(_clip(s.response or "", 4000))
            L.append("```\n</details>\n")
        else:
            L.append(f"### Step {s.n} — {s.stage} (deterministic)\n")
            L.append(f"*{s.detail}*\n")
            if s.response:
                L.append("```text")
                L.append(_clip(s.response, 3000))
                L.append("```\n")

    L.append("## Final determination\n")
    L.append(f"**{det.verdict.value}** — {det.reason}\n")
    if det.missing_information:
        L.append("Information requested:\n")
        for m in det.missing_information:
            L.append(f"- {m}")
        L.append("")

    if not correct:
        L.append("## Why this one is wrong\n")
        L.append(f"Expected **{gold.verdict.value}** citing `{gold.governing_rule}`.\n")
        L.append(f"Gold rationale: {gold.rationale}\n")

    L.append("---\n")
    L.append(
        f"_Replayed from the committed response cache "
        f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC. No live model calls._"
    )
    return "\n".join(L)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n… truncated, {len(text) - limit} more characters"


def _rules_summary(result) -> str:
    report = result.determination.rule_report
    if not report:
        return ""
    lines = []
    for r in report.results:
        mark = {"pass": "PASS", "fail": "FAIL", "unknown": "UNKNOWN",
                "not_applicable": "n/a"}[r.outcome.value]
        lines.append(f"[{r.rule_id}] {mark:8s} {r.summary}")
        if r.evidence:
            ev = ", ".join(f"{k}={v}" for k, v in r.evidence.items() if v is not None)
            lines.append(f"          evidence: {ev}")
    return "\n".join(lines)


def _resolution_summary(result) -> str:
    r = result.resolved
    if not r:
        return ""
    lines = [
        f"member   {r.member_id or 'UNRESOLVED'}  "
        f"(match confidence {r.member_match_confidence:.2f})",
        f"provider {r.provider_npi or 'UNRESOLVED'}",
        f"procedure {r.procedure_code}   diagnosis {', '.join(r.diagnosis_codes) or '—'}",
        f"date of service {r.date_of_service}",
    ]
    for a in r.ambiguities:
        lines.append(f"ambiguity: {a}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    cases = {c.case_id: c for c in load_cases()}
    missing = [cid for cid in REPRESENTATIVE if cid not in cases]
    if missing:
        console.print(f"[red]Unknown case ids:[/red] {missing}")
        return 1

    OUT.mkdir(exist_ok=True)
    holder: dict = {}
    instrument(holder)
    client = ModelClient(mode="replay")

    written: list[tuple[str, str, bool]] = []

    with connect() as conn:
        repo = ClaimsRepository(conn)
        retriever = build_retriever(conn)

        for case_id, why in REPRESENTATIVE.items():
            case = cases[case_id]
            trace = Trace(case_id=case_id)
            holder["current"] = trace
            ledger = CostLedger(case_id=case_id)

            try:
                result = adjudicate(
                    submission=Submission(
                        submission_id=case_id,
                        channel=SubmissionChannel.FAX,
                        received_at=datetime.now(UTC),
                        document_uri=str(document_for(case)),
                        degradation=case.label.degradation,
                        case_id=case_id,
                    ),
                    document_path=document_for(case),
                    repo=repo,
                    retriever=retriever,
                    client=client,
                    ledger=ledger,
                )
            except client_module.ReplayMiss as exc:
                console.print(f"  [yellow]{case_id}[/yellow] {exc}")
                continue

            # Splice the deterministic stages in after extraction, which is
            # where they actually run and where they shape the next prompt.
            insert_at = next(
                (i for i, s in enumerate(trace.steps)
                 if s.stage not in ("extract", "extract_reread")),
                len(trace.steps),
            )
            deterministic = [
                Step(n=0, kind="deterministic", stage="resolve entities",
                     detail="Transcribed strings matched onto real records. No model.",
                     response=_resolution_summary(result)),
                Step(n=0, kind="deterministic", stage="evaluate 9 rules",
                     detail="Pure functions over the payer records. No model.",
                     response=_rules_summary(result)),
            ]
            if result.clauses:
                deterministic.append(
                    Step(n=0, kind="deterministic", stage="retrieve criteria",
                         detail=(
                             f"{len(result.clauses)} assessable clauses from "
                             f"{result.clauses[0].document_id}, selected by procedure "
                             "code rather than similarity search."
                         ),
                         response="\n".join(
                             f"[{c.clause_id}] {c.role}" for c in result.clauses
                         ))
                )
            trace.steps[insert_at:insert_at] = deterministic
            for i, s in enumerate(trace.steps, 1):
                s.n = i

            det = result.determination
            path = OUT / f"{case_id}.md"
            path.write_text(render(case, trace, result, why), encoding="utf-8")
            ok = det.verdict == case.label.verdict
            written.append((case_id, case.scenario, ok))
            console.print(
                f"  {case_id} {case.scenario:32s} "
                f"{len([s for s in trace.steps if s.kind=='model'])} model calls "
                f"{'[green]correct[/green]' if ok else '[red]incorrect[/red]'}"
            )

    _write_index(written)
    console.print(f"\n[green]{len(written)}[/green] trajectories written to trajectories/")
    return 0


def _write_index(written: list[tuple[str, str, bool]]) -> None:
    L = ["# Agent trajectories\n"]
    L.append(
        "One trace per distinct path through the system, replayed from the "
        "committed response cache. Each shows the agent instructions in use, "
        "every prompt and response, the deterministic stages between them, "
        "any retry, and whether a clinician was required.\n"
    )
    L.append(
        "Regenerate with `python -m eval.harness.trajectories` — it costs "
        "nothing and needs no API key.\n"
    )
    L.append("## Agents\n")
    L.append("| Agent | Instructions | Role |")
    L.append("|---|---|---|")
    L.append(
        "| `intake_extractor` | "
        "[prompt.md](../agents/intake_extractor/prompt.md) | "
        "Reads the form; reports what it could not read rather than guessing |"
    )
    L.append(
        "| `adjudicator` | [prompt.md](../agents/adjudicator/prompt.md) | "
        "Judges the narrative against retrieved criteria. Returns no verdict |"
    )
    L.append(
        "| `reviewer_critic` | "
        "[prompt.md](../agents/reviewer_critic/prompt.md) | "
        "Audits the rationale for claims not traceable to evidence |"
    )
    L.append("")
    L.append("## Traces\n")
    L.append("| Case | Scenario | Verdict correct | Trace |")
    L.append("|---|---|---|---|")
    for case_id, scenario, ok in written:
        L.append(
            f"| {case_id} | {scenario} | {'yes' if ok else '**no**'} | "
            f"[{case_id}.md]({case_id}.md) |"
        )
    L.append("")
    L.append(
        "The set deliberately includes a case the system gets wrong. A "
        "trajectory set showing only successes is marketing, not evidence.\n"
    )
    (OUT / "README.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
