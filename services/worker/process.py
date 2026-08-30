"""Process submissions and persist the results.

    python -m services.worker.process            # all cases, from cache
    python -m services.worker.process --limit 10

This is the path that fills the reviewer console. It runs the same pipeline
the evaluation does, then writes each determination through the ledger store
so a nurse can open it.

By default it runs in replay mode against the recorded responses, so filling
the console after an evaluation costs nothing and produces exactly the
determinations that were scored -- what the reviewer sees is the run that was
measured, not a fresh one that might differ.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

import psycopg
from rich.console import Console

from agents.client import ModelClient, ReplayMiss
from eval.harness.run import document_for, load_cases
from packages.core.ledger_store import LedgerStore
from packages.core.models import Submission, SubmissionChannel
from packages.core.repository import ClaimsRepository, connect
from packages.observability.ledger import CostLedger
from packages.orchestrator.pipeline import adjudicate, build_retriever

console = Console()

#: Which intake channel a case is presented as arriving through. Document
#: condition is the honest proxy: clean PDFs come from the portal, degraded
#: scans and photographs come off the fax gateway.
CHANNEL_BY_TIER = {
    "clean": SubmissionChannel.PORTAL,
    "scan": SubmissionChannel.FAX,
    "fax": SubmissionChannel.FAX,
    "photo": SubmissionChannel.FAX,
    "handwritten": SubmissionChannel.FAX,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument(
        "--live",
        action="store_true",
        help="Call the API for anything not cached (default: replay only)",
    )
    args = ap.parse_args(argv)

    cases = load_cases(args.limit)
    if not cases:
        console.print("[red]No cases found.[/red] Run `make seed` first.")
        return 1

    client = ModelClient(mode="auto" if args.live else "replay")
    console.print(f"[bold]Processing {len(cases)} submissions[/bold]\n")

    released = 0
    queued = 0

    try:
        with connect() as conn:
            repo = ClaimsRepository(conn)
            store = LedgerStore(conn)
            retriever = build_retriever(conn)

            for i, case in enumerate(cases, 1):
                document = document_for(case)
                tier = case.label.degradation.value
                channel = CHANNEL_BY_TIER.get(tier, SubmissionChannel.FAX)

                store.record_submission(
                    submission_id=case.case_id,
                    channel=channel.value,
                    document_uri=document.name,
                    degradation=tier,
                    case_id=case.case_id,
                )

                ledger = CostLedger(case_id=case.case_id)
                try:
                    result = adjudicate(
                        submission=Submission(
                            submission_id=case.case_id,
                            channel=channel,
                            received_at=datetime.now(UTC),
                            document_uri=document.name,
                            degradation=case.label.degradation,
                            case_id=case.case_id,
                        ),
                        document_path=document,
                        repo=repo,
                        retriever=retriever,
                        client=client,
                        ledger=ledger,
                    )
                except ReplayMiss:
                    console.print(
                        f"  [yellow]{case.case_id}[/yellow] not in cache — "
                        "run `make eval` first, or pass --live"
                    )
                    continue

                det = result.determination
                store.record_determination(det, result.extraction)

                if det.requires_human_review:
                    queued += 1
                    marker = "[yellow]queued[/yellow]"
                else:
                    released += 1
                    marker = "[green]released[/green]"

                console.print(
                    f"  [dim]{i:>2}/{len(cases)}[/dim] {case.case_id} "
                    f"{det.verdict.value:<19} {det.governing_rule:<12} {marker}"
                )

    except psycopg.OperationalError as exc:
        console.print(f"[red]Database unreachable:[/red] {exc}")
        return 1

    console.print(
        f"\n[bold]{queued}[/bold] awaiting review, "
        f"[bold]{released}[/bold] released without a clinician."
    )
    console.print("[dim]Open the console with: make console[/dim]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
