"""Build the whole synthetic world from one seed.

    python -m data.generator.build --seed 20260830

Emits, deterministically:
  * payer reference data and a member population, loaded into Postgres
  * the policy corpus, chunked on criterion boundaries
  * one rendered pre-auth document per case, degraded to its tier
  * gold labels, written to eval/cases/

Re-running with the same seed reproduces the same labels byte for byte. That
property is what lets someone else re-run the evaluation and get our numbers.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import psycopg
from rich.console import Console
from rich.table import Table

from data.generator import corpus as C
from data.generator.forms import build_document
from data.generator.population import PLAN_YEAR, Population
from data.generator.reference import (
    CODE_PAIRS,
    DIAGNOSES,
    PLANS,
    PROCEDURES,
)
from data.generator.scenarios import SCENARIOS, ScenarioContext
from packages.core.config import DATABASE_URL
from packages.core.labels import GeneratedCase
from packages.core.models import DegradationTier
from packages.core.records import PriorAuthorization

REPO = Path(__file__).resolve().parents[2]
SEED_DIR = REPO / "data" / "seeds"
FORM_DIR = SEED_DIR / "forms"
CASE_DIR = REPO / "eval" / "cases"

console = Console()


# --------------------------------------------------------------------------
# Generate
# --------------------------------------------------------------------------


def generate(
    seed: int,
) -> tuple[Population, list[GeneratedCase], list[PriorAuthorization]]:
    pop = Population(seed=seed)
    rng = random.Random(seed ^ 0x5EED)
    cases: list[GeneratedCase] = []
    used: set[str] = set()
    extra_auths: list[PriorAuthorization] = []

    n = 0
    for builder, count in SCENARIOS:
        for _ in range(count):
            n += 1
            ctx = ScenarioContext(pop, rng, case_id=f"CASE-{n:03d}")
            ctx.used_members = used
            case = builder(ctx)
            # Each case gets its own member so one scenario's mutation --
            # a termination date, an exhausted accumulator -- cannot leak
            # into another case's expected outcome.
            used.add(case.member.member_id)
            extra_auths.extend(ctx.extra_prior_auths)
            cases.append(case)

    _spread_degradation(cases)
    return pop, cases, extra_auths


#: Tiers a case may be reassigned to. Document quality is independent of the
#: clinical and contractual facts, so spreading it evenly across the case mix
#: is both more realistic and the only way to compare extraction per tier
#: without confounding it with verdict difficulty.
_SPREADABLE = [
    DegradationTier.CLEAN,
    DegradationTier.SCAN,
    DegradationTier.FAX,
    DegradationTier.PHOTO,
]


def _spread_degradation(cases: list[GeneratedCase]) -> None:
    """Deal document quality round-robin across cases that do not pin it.

    Scenarios that exist *because* of their document quality -- the
    handwritten member id, the faxed clean approval -- keep the tier they
    asked for. Everything else is dealt in a fixed rotation, so the
    assignment is deterministic and each tier gets a comparable share of easy
    and hard verdicts.
    """
    pinned = {"illegible_member_id", "clean_approval_faxed"}
    i = 0
    for case in cases:
        if case.scenario in pinned:
            continue
        case.label.degradation = _SPREADABLE[i % len(_SPREADABLE)]
        i += 1


# --------------------------------------------------------------------------
# Load
# --------------------------------------------------------------------------


def load_database(pop: Population, cases: list[GeneratedCase], extra_auths: list) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=False) as conn, conn.cursor() as cur:
        # Order matters: children before parents.
        for table in (
            "review_actions", "determinations", "submissions", "policy_chunks",
            "policy_documents", "prior_authorizations", "code_pairs",
            "accumulators", "members", "providers", "procedures", "diagnoses",
            "reviewers", "plans",
        ):
            cur.execute(f"TRUNCATE {table} CASCADE")

        cur.executemany(
            """INSERT INTO plans (plan_id, name, waiting_period_days,
               preexisting_exclusion_months, requires_in_network, covered_states,
               excluded_categories, coverage_document_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (p.plan_id, p.name, p.waiting_period_days, p.preexisting_exclusion_months,
                 p.requires_in_network, p.covered_states, p.excluded_categories,
                 p.coverage_document_id)
                for p in PLANS
            ],
        )

        cur.executemany(
            """INSERT INTO procedures (code, description, category, requires_preauth,
               unit_cost, always_review, sex_restriction, age_min, age_max,
               policy_document_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (p.code, p.description, p.category, p.requires_preauth, p.unit_cost,
                 p.always_review, p.sex_restriction, p.age_min, p.age_max,
                 p.policy_document_id)
                for p in PROCEDURES
            ],
        )

        cur.executemany(
            "INSERT INTO diagnoses (code, description) VALUES (%s,%s)",
            [(d.code, d.description) for d in DIAGNOSES],
        )

        cur.executemany(
            "INSERT INTO code_pairs (procedure_code, diagnosis_code) VALUES (%s,%s)",
            [(px, dx) for px, dxs in CODE_PAIRS.items() for dx in dxs],
        )

        cur.executemany(
            """INSERT INTO providers (npi, name, specialty, network_tier, license_state,
               license_expiry, contract_start, contract_end, sanctioned,
               credentialed_procedures) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (p.npi, p.name, p.specialty, p.network_tier.value, p.license_state,
                 p.license_expiry, p.contract_start, p.contract_end, p.sanctioned,
                 p.credentialed_procedures)
                for p in pop.providers
            ],
        )

        cur.executemany(
            """INSERT INTO members (member_id, first_name, last_name, date_of_birth, sex,
               plan_id, group_id, status, effective_date, termination_date,
               premium_paid_through, state, enrolled_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                (m.member_id, m.first_name, m.last_name, m.date_of_birth, m.sex,
                 m.plan_id, m.group_id, m.status.value, m.effective_date,
                 m.termination_date, m.premium_paid_through, m.state, m.enrolled_at)
                for m in pop.members
            ],
        )

        cur.executemany(
            """INSERT INTO accumulators (member_id, plan_year, category, limit_amount,
               consumed_amount) VALUES (%s,%s,%s,%s,%s)""",
            [
                (a.member_id, a.plan_year, a.category, a.limit_amount, a.consumed_amount)
                for a in pop.accumulators
            ],
        )

        cur.executemany(
            """INSERT INTO reviewers (reviewer_id, name, role, credentials, license_number)
               VALUES (%s,%s,%s,%s,%s)""",
            [(r.reviewer_id, r.name, r.role, r.credentials, r.license_number)
             for r in pop.reviewers],
        )

        if extra_auths:
            cur.executemany(
                """INSERT INTO prior_authorizations (auth_id, member_id, provider_npi,
                   procedure_code, valid_from, valid_to, status, units_approved)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    (a.auth_id, a.member_id, a.provider_npi, a.procedure_code,
                     a.valid_from, a.valid_to, a.status, a.units_approved)
                    for a in extra_auths
                ],
            )

        # -- corpus --------------------------------------------------------
        cur.executemany(
            """INSERT INTO policy_documents (document_id, title, doc_type, version, body)
               VALUES (%s,%s,%s,%s,%s)""",
            [(d.document_id, d.title, d.doc_type, d.version, d.body) for d in C.ALL_DOCUMENTS],
        )
        chunk_rows = []
        for doc in C.ALL_DOCUMENTS:
            for ordinal, (clause_id, text) in enumerate(doc.chunks()):
                chunk_rows.append((clause_id, doc.document_id, ordinal, text))
        cur.executemany(
            "INSERT INTO policy_chunks (clause_id, document_id, ordinal, text) "
            "VALUES (%s,%s,%s,%s)",
            chunk_rows,
        )

        conn.commit()
    return len(chunk_rows)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def summarise(pop: Population, cases: list[GeneratedCase], n_chunks: int, n_docs: int) -> None:
    from collections import Counter

    verdicts = Counter(c.label.verdict.value for c in cases)
    tiers = Counter(c.label.degradation.value for c in cases)
    adversarial = sum(1 for c in cases if c.label.is_adversarial)
    auto_ok = sum(1 for c in cases if not c.label.requires_human_review)

    t = Table(title=None, show_header=True, header_style="dim", box=None, pad_edge=False)
    t.add_column("", style="bold")
    t.add_column("")
    t.add_row("Members", f"{len(pop.members)}")
    t.add_row("Providers", f"{len(pop.providers)}")
    t.add_row("Accumulators", f"{len(pop.accumulators)}")
    t.add_row("Policy documents", f"{n_docs} ({n_chunks} retrievable clauses)")
    t.add_row("", "")
    t.add_row("Cases", f"{len(cases)}  ({adversarial} adversarial)")
    t.add_row("Verdict mix", ", ".join(f"{k} {v}" for k, v in sorted(verdicts.items())))
    t.add_row("Document tiers", ", ".join(f"{k} {v}" for k, v in sorted(tiers.items())))
    t.add_row("Eligible for auto-release", f"{auto_ok} of {len(cases)}")
    console.print(t)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=20260830)
    ap.add_argument(
        "--skip-db", action="store_true", help="Generate files without loading Postgres"
    )
    ap.add_argument("--skip-forms", action="store_true", help="Skip document rendering (faster)")
    args = ap.parse_args(argv)

    console.print(f"[bold]Generating from seed {args.seed}[/bold]")
    pop, cases, extra_auths = generate(args.seed)

    # -- labels ------------------------------------------------------------
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    for case in cases:
        (CASE_DIR / f"{case.case_id}.json").write_text(
            case.model_dump_json(indent=2), encoding="utf-8"
        )
    manifest = {
        "seed": args.seed,
        "plan_year": PLAN_YEAR,
        "case_count": len(cases),
        "cases": [
            {
                "case_id": c.case_id,
                "scenario": c.scenario,
                "verdict": c.label.verdict.value,
                "governing_rule": c.label.governing_rule,
                "degradation": c.label.degradation.value,
                "adversarial": c.label.is_adversarial,
                "requires_human_review": c.label.requires_human_review,
            }
            for c in cases
        ],
    }
    (CASE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"  labels    [green]{len(cases)}[/green] written to eval/cases/")

    # -- documents ---------------------------------------------------------
    if not args.skip_forms:
        for case in cases:
            build_document(case, FORM_DIR)
        console.print(f"  documents [green]{len(cases)}[/green] rendered to data/seeds/forms/")

    # -- database ----------------------------------------------------------
    n_chunks = 0
    if not args.skip_db:
        try:
            n_chunks = load_database(pop, cases, extra_auths)
            console.print("  database  [green]loaded[/green]")
        except psycopg.OperationalError as exc:
            console.print(f"  database  [red]unreachable[/red] -- {exc}")
            console.print("  [dim]start it with: docker compose up -d[/dim]")
            return 1

    console.print()
    summarise(pop, cases, n_chunks, len(C.ALL_DOCUMENTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
