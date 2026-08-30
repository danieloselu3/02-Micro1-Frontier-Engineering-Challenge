"""Render the baseline-vs-solution comparison as markdown.

Written to eval/reports/comparison.md and committed, so every claim in the
README points at a file a reader can open rather than a number they have to
take on trust.

The report is deliberately unflattering where the results are unflattering:
per-scenario breakdowns are printed in full, including the categories the
system does worst on, and the resource asymmetry between the two systems is
stated at the top rather than buried.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def write_report(baseline: dict, solution: dict, out_dir: Path) -> Path:
    b, s = baseline["summary"], solution["summary"]
    lines: list[str] = []

    lines.append("# Baseline vs. agent pipeline\n")
    lines.append(
        f"_Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC over "
        f"{s['cases']} cases._\n"
    )

    # -- headline ----------------------------------------------------------
    lines.append("## Results\n")
    lines.append("| Metric | Baseline | Agent pipeline | Change |")
    lines.append("|---|---:|---:|---:|")
    lines.append(_row("Verdict accuracy", b, s, "verdict_accuracy", "%", higher_better=True))
    lines.append(_row("Reason accuracy", b, s, "reason_accuracy", "%", higher_better=True))
    lines.append(_row("False denials", b, s, "false_denials", "", higher_better=False))
    lines.append(_row("False approvals", b, s, "false_approvals", "", higher_better=False))
    lines.append(
        _row("Mean cost per case", b, s, "mean_cost_usd", "", higher_better=False, money=True)
    )
    lines.append(_row("Mean latency (s)", b, s, "mean_latency_s", "", higher_better=False))
    lines.append(_row("Model calls", b, s, "total_model_calls", "", higher_better=False))
    lines.append("")

    # -- the two error types -----------------------------------------------
    lines.append("## Why the two error types are reported separately\n")
    lines.append(
        "A wrong approval costs the payer money and is recoverable when the "
        "claim is adjudicated. A wrong denial delays someone's treatment and "
        "starts an appeal that takes weeks. They are not interchangeable, and "
        "a single blended accuracy figure lets a system trade the second for "
        "the first invisibly -- which, because approvals are the majority "
        "class in production, is exactly the trade an optimiser makes.\n"
    )
    lines.append(
        f"- **False denials** — baseline {b['false_denials']}, "
        f"pipeline {s['false_denials']}"
    )
    lines.append(
        f"- **False approvals** — baseline {b['false_approvals']}, "
        f"pipeline {s['false_approvals']}\n"
    )

    # -- extraction --------------------------------------------------------
    if s.get("field_accuracy") is not None:
        lines.append("## Extraction accuracy by document condition\n")
        lines.append(
            "The baseline emits no per-field transcription, so it is not "
            "scored here. These figures are the pipeline's.\n"
        )
        lines.append("| Document tier | Cases | Field accuracy | Verdict accuracy |")
        lines.append("|---|---:|---:|---:|")
        for tier, row in solution["by_degradation"].items():
            acc = f"{row['field_accuracy']}%" if row["field_accuracy"] is not None else "—"
            lines.append(
                f"| {tier} | {row['cases']} | {acc} | {row['verdict_accuracy']}% |"
            )
        lines.append("")

    # -- cost --------------------------------------------------------------
    lines.append("## Where the cost difference comes from\n")
    lines.append(
        f"The pipeline made **{s['total_model_calls']} model calls** across "
        f"{s['cases']} cases against the baseline's {b['total_model_calls']}, "
        f"and **{s['cases_with_no_model_call']} cases reached a determination "
        "with no adjudication model call at all** — requests for procedures "
        "that never required authorization, and requests stopped by a "
        "contractual or eligibility rule where medical necessity is "
        "irrelevant.\n"
    )

    # -- per scenario ------------------------------------------------------
    lines.append("## Per scenario\n")
    lines.append(
        "Every scenario is listed, including the ones the pipeline handles "
        "worst.\n"
    )
    lines.append("| Scenario | Cases | Baseline verdict | Pipeline verdict | Pipeline reason |")
    lines.append("|---|---:|---:|---:|---:|")
    for name, srow in solution["by_scenario"].items():
        brow = baseline["by_scenario"].get(name, {})
        lines.append(
            f"| {name} | {srow['cases']} | "
            f"{brow.get('verdict_accuracy', 0)}% | "
            f"{srow['verdict_accuracy']}% | {srow['reason_accuracy']}% |"
        )
    lines.append("")

    # -- disagreements -----------------------------------------------------
    misses = [c for c in solution["cases"] if not c["verdict_correct"]]
    if misses:
        lines.append("## Cases the pipeline got wrong\n")
        lines.append("| Case | Scenario | Expected | Produced | Rule cited |")
        lines.append("|---|---|---|---|---|")
        for c in misses:
            lines.append(
                f"| {c['case_id']} | {c['scenario']} | {c['expected_verdict']} | "
                f"{c['actual_verdict']} | {c['actual_rule']} |"
            )
        lines.append("")

    # -- caveats -----------------------------------------------------------
    lines.append("## What these numbers do not say\n")
    lines.append(
        "**The case mix is not production-representative.** It is a stress "
        "set built for failure-mode coverage, weighted heavily toward "
        "denials and adversarial conditions. Real prior authorization "
        "approves roughly 85% of requests. Accuracy here is a measure of "
        "robustness across failure modes, not an estimate of production "
        "performance.\n"
    )
    lines.append(
        "**The baseline is given an advantage.** It receives the correct "
        "member, provider and procedure records directly, while the pipeline "
        "must resolve them from the document it read. The comparison is "
        "therefore conservative: the baseline is spared a step the real "
        "system has to get right.\n"
    )
    lines.append(
        "**Both systems are graded against synthetic ground truth.** The "
        "labels are derived from generated record state, not from decisions "
        "made by practising utilization-review nurses.\n"
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "comparison.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _row(
    label: str,
    baseline: dict,
    solution: dict,
    key: str,
    suffix: str,
    *,
    higher_better: bool,
    money: bool = False,
) -> str:
    b, s = baseline.get(key, 0), solution.get(key, 0)
    fmt = (lambda v: f"${v:.5f}") if money else (lambda v: f"{v}{suffix}")

    delta = s - b
    if abs(delta) < 1e-9:
        change = "—"
    else:
        improved = (delta > 0) == higher_better
        arrow = "↑" if delta > 0 else "↓"
        sign = "+" if delta > 0 else ""
        shown = f"${abs(delta):.5f}" if money else f"{sign}{round(delta, 4)}{suffix}"
        change = f"{arrow} {shown}" + ("" if improved else " ⚠")

    return f"| {label} | {fmt(b)} | {fmt(s)} | {change} |"
