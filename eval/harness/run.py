"""Run the evaluation.

    make baseline      # single-prompt comparator
    make eval          # full pipeline
    make eval-replay   # both, from committed responses, no API key

Both systems see the same 49 cases and are scored identically. One resource
difference is deliberate and is disclosed in the report: the baseline is
handed the correct member, provider and procedure records, while the pipeline
must resolve them from the document it read. That makes the comparison
conservative -- the baseline is spared a step the real system has to get
right -- which is the direction an honest benchmark should err in.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from rich.console import Console
from rich.table import Table

from agents.client import ModelClient, ReplayMiss
from eval.baseline.single_prompt import run_baseline
from eval.harness.report import write_report
from eval.harness.scoring import CaseScore, by_degradation, by_scenario, score_case, summarise
from packages.core.labels import GeneratedCase
from packages.core.models import Submission, SubmissionChannel, Verdict
from packages.core.repository import ClaimsRepository, connect
from packages.observability.ledger import CostLedger
from packages.orchestrator.pipeline import PLAN_YEAR, adjudicate, build_retriever

REPO = Path(__file__).resolve().parents[2]
CASE_DIR = REPO / "eval" / "cases"
FORM_DIR = REPO / "data" / "seeds" / "forms"
REPORT_DIR = REPO / "eval" / "reports"

console = Console()


def load_cases(limit: int | None = None) -> list[GeneratedCase]:
    files = sorted(CASE_DIR.glob("CASE-*.json"))
    cases = [GeneratedCase(**json.loads(p.read_text(encoding="utf-8"))) for p in files]
    return cases[:limit] if limit else cases


def document_for(case: GeneratedCase) -> Path:
    for suffix in (".pdf", ".png"):
        candidate = FORM_DIR / f"{case.case_id}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No rendered document for {case.case_id}. Run `make seed` first."
    )


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------


def run_solution(cases, repo, retriever, client) -> list[CaseScore]:
    scores: list[CaseScore] = []
    for i, case in enumerate(cases, 1):
        ledger = CostLedger(case_id=case.case_id)
        console.print(f"  [dim]{i:>2}/{len(cases)}[/dim] {case.case_id} {case.scenario}")
        try:
            result = adjudicate(
                submission=Submission(
                    submission_id=case.case_id,
                    channel=SubmissionChannel.FAX,
                    received_at=datetime.now(UTC),
                    document_uri=str(document_for(case)),
                    degradation=case.label.degradation,
                    case_id=case.case_id,
                ),
                document_path=document_for(case),
                repo=repo,
                retriever=retriever,
                client=client,
                ledger=ledger,
            )
            det = result.determination
            scores.append(
                score_case(
                    case=case,
                    verdict=det.verdict,
                    governing_rule=det.governing_rule,
                    extraction=result.extraction,
                    requires_human_review=det.requires_human_review,
                    blocking_findings=(
                        sum(1 for f in det.critic.findings if f.severity == "blocking")
                        if det.critic
                        else 0
                    ),
                    cost_usd=ledger.total_cost_usd,
                    latency_s=ledger.model_seconds,
                    model_calls=len(ledger.calls),
                    exit_stage=result.exit_stage,
                )
            )
        except ReplayMiss:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad case must not lose the run
            console.print(f"     [red]error[/red] {exc}")
            traceback.print_exc(limit=2)
            scores.append(
                score_case(
                    case=case,
                    verdict=Verdict.PENDED,
                    governing_rule="error",
                    cost_usd=ledger.total_cost_usd,
                    latency_s=ledger.model_seconds,
                    model_calls=len(ledger.calls),
                    error=str(exc),
                )
            )
    return scores


def run_baseline_system(cases, repo, retriever, client) -> list[CaseScore]:
    scores: list[CaseScore] = []
    for i, case in enumerate(cases, 1):
        ledger = CostLedger(case_id=case.case_id)
        console.print(f"  [dim]{i:>2}/{len(cases)}[/dim] {case.case_id} {case.scenario}")
        try:
            # The baseline is handed the correct records rather than having
            # to resolve them from the document. Disclosed in the report.
            facts = repo.gather(
                member_id=case.member.member_id,
                provider_npi=case.provider.npi,
                procedure_code=case.procedure_code,
                diagnosis_codes=case.diagnosis_codes,
                date_of_service=case.date_of_service,
                units_requested=case.units_requested,
                plan_year=PLAN_YEAR,
            )
            out = run_baseline(
                client=client,
                ledger=ledger,
                document_path=document_for(case),
                facts=facts,
                retriever=retriever,
            )
            scores.append(
                score_case(
                    case=case,
                    verdict=out["verdict"],
                    governing_rule=out["governing_rule"],
                    # The baseline emits no per-field extraction, so field
                    # accuracy is not scored for it and the report says so
                    # rather than showing a misleading zero.
                    extraction=None,
                    requires_human_review=True,
                    cost_usd=ledger.total_cost_usd,
                    latency_s=ledger.model_seconds,
                    model_calls=len(ledger.calls),
                )
            )
        except ReplayMiss:
            raise
        except Exception as exc:  # noqa: BLE001
            console.print(f"     [red]error[/red] {exc}")
            scores.append(
                score_case(
                    case=case,
                    verdict=Verdict.PENDED,
                    governing_rule="error",
                    cost_usd=ledger.total_cost_usd,
                    latency_s=ledger.model_seconds,
                    model_calls=len(ledger.calls),
                    error=str(exc),
                )
            )
    return scores


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def print_summary(name: str, summary: dict) -> None:
    t = Table(title=f"\n{name}", show_header=False, box=None, pad_edge=False)
    t.add_column("", style="bold", width=26)
    t.add_column("")
    t.add_row("Verdict accuracy", f"{summary['verdict_accuracy']}%")
    t.add_row("Reason accuracy", f"{summary['reason_accuracy']}%")
    t.add_row(
        "False denials",
        f"[red]{summary['false_denials']}[/red] ({summary['false_denial_rate']}%)",
    )
    t.add_row(
        "False approvals",
        f"{summary['false_approvals']} ({summary['false_approval_rate']}%)",
    )
    if summary.get("field_accuracy") is not None:
        t.add_row("Field extraction", f"{summary['field_accuracy']}%")
    t.add_row("Mean cost per case", f"${summary['mean_cost_usd']:.5f}")
    t.add_row("Mean latency", f"{summary['mean_latency_s']}s")
    t.add_row("Model calls", f"{summary['total_model_calls']}")
    t.add_row(
        "Settled w/o adjudication",
        f"{summary['settled_without_adjudication']}"
        f" ({summary['settled_by_fast_path']} no-auth,"
        f" {summary['settled_by_hard_stop']} hard stop)",
    )
    if summary["errors"]:
        t.add_row("Errors", f"[red]{summary['errors']}[/red]")
    console.print(t)


def persist(name: str, scores: list[CaseScore]) -> dict:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "system": name,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summarise(scores),
        "by_scenario": by_scenario(scores),
        "by_degradation": by_degradation(scores),
        "cases": [asdict(s) for s in scores],
    }
    (REPORT_DIR / f"{name}.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    return payload


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--system", choices=["baseline", "solution", "both"], default="solution")
    ap.add_argument("--replay", action="store_true", help="Use recorded responses only")
    ap.add_argument("--limit", type=int, default=None, help="Run only the first N cases")
    args = ap.parse_args(argv)

    cases = load_cases(args.limit)
    if not cases:
        console.print("[red]No cases found.[/red] Run `make seed` first.")
        return 1

    mode = "replay" if args.replay else "auto"
    client = ModelClient(mode=mode)
    console.print(
        f"[bold]Evaluating {len(cases)} cases[/bold] "
        f"[dim](system={args.system}, mode={mode})[/dim]\n"
    )

    try:
        with connect() as conn:
            repo = ClaimsRepository(conn)
            retriever = build_retriever(conn)

            results: dict[str, dict] = {}
            if args.system in ("baseline", "both"):
                console.print("[bold]Baseline[/bold]")
                results["baseline"] = persist(
                    "baseline", run_baseline_system(cases, repo, retriever, client)
                )
            if args.system in ("solution", "both"):
                console.print("[bold]Solution[/bold]")
                results["solution"] = persist(
                    "solution", run_solution(cases, repo, retriever, client)
                )
    except psycopg.OperationalError as exc:
        console.print(f"[red]Database unreachable:[/red] {exc}")
        console.print("[dim]Start it with: docker compose up -d && make seed[/dim]")
        return 1
    except ReplayMiss as exc:
        console.print(f"[red]Replay miss:[/red] {exc}")
        return 1

    for name, payload in results.items():
        print_summary(name.title(), payload["summary"])

    console.print(
        f"\n[dim]cache: {client.hits} hits, {client.misses} live calls[/dim]"
    )

    if len(results) == 2:
        write_report(results["baseline"], results["solution"], REPORT_DIR)
        console.print(f"[green]Comparison written to[/green] {REPORT_DIR / 'comparison.md'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
