"""The adjudication pipeline.

This is a state machine, not an agent. The stages run in a fixed order with
explicit branch conditions, because there is no ambiguity about what follows
"gather facts" and nothing for a model to decide. An LLM orchestrator here
would be slower, more expensive, non-deterministic, and would make the whole
evaluation unreproducible -- in exchange for nothing.

Where the model *is* used, it is used narrowly: reading the form, judging
medical necessity against retrieved criteria, and auditing its own rationale.
Three calls at most, and frequently zero.

The short-circuits are where the cost story lives:

  * R1 not applicable  -> exit after extraction. No retrieval, no judgment,
                          no verification. A third of real inbound volume is
                          a provider requesting authorization for something
                          that never needed one.
  * a hard-stop rule   -> exit after the rules. A terminated policy makes
                          medical necessity irrelevant, and paying a model to
                          assess it anyway is waste with a clinical risk
                          attached.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from agents.adjudicator.agent import judge_necessity
from agents.client import ModelClient
from agents.intake_extractor.agent import extract
from agents.reviewer_critic.agent import verify
from data.generator.reference import accumulator_for_procedure
from packages.core.config import ENTITY_MATCH_FLOOR
from packages.core.models import (
    Determination,
    ExtractedRequest,
    NecessityJudgment,
    PolicyClause,
    ResolvedEntities,
    RuleOutcome,
    Submission,
)
from packages.core.records import CaseFacts
from packages.core.repository import ClaimsRepository
from packages.core.retrieval import PolicyRetriever
from packages.observability.ledger import CostLedger
from packages.rules.assemble import assemble
from packages.rules.engine import evaluate

PLAN_YEAR = 2026


@dataclass
class PipelineResult:
    """Everything one run produced, for the console and the harness."""

    determination: Determination
    extraction: ExtractedRequest | None = None
    resolved: ResolvedEntities | None = None
    facts: CaseFacts | None = None
    clauses: list[PolicyClause] = field(default_factory=list)
    ledger: CostLedger | None = None
    exit_stage: str = "complete"


def adjudicate(
    *,
    submission: Submission,
    document_path: Path,
    repo: ClaimsRepository,
    retriever: PolicyRetriever,
    client: ModelClient,
    ledger: CostLedger | None = None,
) -> PipelineResult:
    ledger = ledger or CostLedger(case_id=submission.submission_id)
    det_id = f"DET-{uuid.uuid5(uuid.NAMESPACE_URL, submission.submission_id).hex[:12]}"

    # -- 1. read the form --------------------------------------------------
    extraction = extract(
        client=client,
        ledger=ledger,
        document_path=document_path,
        submission_id=submission.submission_id,
    )

    # -- 2. resolve what was read onto real records ------------------------
    resolved = resolve(repo, extraction)

    # -- 3. gather facts ---------------------------------------------------
    facts = _gather(repo, resolved)

    # -- 4. evaluate the rules --------------------------------------------
    category = (
        accumulator_for_procedure(resolved.procedure_code)
        if resolved.procedure_code
        and resolved.procedure_code in _known_procedure_codes()
        else "outpatient"
    )
    rules = evaluate(facts, category, PLAN_YEAR)

    # -- 5. the fast path: nothing here needed authorization ---------------
    r1 = rules.get("R1")
    if r1 and r1.outcome == RuleOutcome.NOT_APPLICABLE:
        det = assemble(
            determination_id=det_id,
            submission_id=submission.submission_id,
            rules=rules,
            facts=facts,
            extraction=extraction,
            model_cost_usd=ledger.total_cost_usd,
            elapsed_seconds=ledger.model_seconds,
        )
        return PipelineResult(
            determination=det,
            extraction=extraction,
            resolved=resolved,
            facts=facts,
            ledger=ledger,
            exit_stage="no_auth_required",
        )

    # -- 6. a contractual or eligibility stop ends it ----------------------
    if rules.hard_stop is not None:
        det = assemble(
            determination_id=det_id,
            submission_id=submission.submission_id,
            rules=rules,
            facts=facts,
            extraction=extraction,
            model_cost_usd=ledger.total_cost_usd,
            elapsed_seconds=ledger.model_seconds,
        )
        return PipelineResult(
            determination=det,
            extraction=extraction,
            resolved=resolved,
            facts=facts,
            ledger=ledger,
            exit_stage="hard_stop",
        )

    # -- 7. retrieve the governing criteria --------------------------------
    clauses = _retrieve(retriever, facts)

    # -- 8. judge medical necessity ----------------------------------------
    necessity = _judge(client, ledger, clauses, extraction, facts)

    # -- 9. assemble a draft ------------------------------------------------
    draft = assemble(
        determination_id=det_id,
        submission_id=submission.submission_id,
        rules=rules,
        facts=facts,
        necessity=necessity,
        clauses=clauses,
        extraction=extraction,
        model_cost_usd=ledger.total_cost_usd,
        elapsed_seconds=ledger.model_seconds,
    )

    # -- 10. audit the rationale before anyone sees it ---------------------
    critic = verify(
        client=client,
        ledger=ledger,
        rationale=draft.reason,
        rules=rules,
        clauses=clauses,
        necessity=necessity,
        narrative=extraction.clinical_narrative,
    )

    # -- 11. reassemble with the audit, which may force review -------------
    final = assemble(
        determination_id=det_id,
        submission_id=submission.submission_id,
        rules=rules,
        facts=facts,
        necessity=necessity,
        clauses=clauses,
        critic=critic,
        extraction=extraction,
        model_cost_usd=ledger.total_cost_usd,
        elapsed_seconds=ledger.model_seconds,
    )

    return PipelineResult(
        determination=final,
        extraction=extraction,
        resolved=resolved,
        facts=facts,
        clauses=clauses,
        ledger=ledger,
    )


# --------------------------------------------------------------------------
# Stages
# --------------------------------------------------------------------------


def resolve(repo: ClaimsRepository, extraction: ExtractedRequest) -> ResolvedEntities:
    """Match transcribed strings onto real records.

    Kept separate from extraction so a misread field and a mis-matched
    record stay distinguishable in the evaluation. They have different
    fixes: one is a document-quality problem, the other a matching problem.
    """
    printed_id = _clean_id(extraction.value("member_id"))
    name = extraction.value("member_name")
    dob = _parse_date(extraction.value("date_of_birth"))

    member, confidence, ambiguities = repo.match_member(printed_id, name, dob)

    npi = extraction.value("provider_npi")
    provider = repo.provider(npi) if npi else None
    if npi and provider is None:
        ambiguities.append(f"NPI '{npi}' is not on file.")

    return ResolvedEntities(
        member_id=member.member_id if member else None,
        member_match_confidence=confidence,
        provider_npi=provider.npi if provider else None,
        provider_match_confidence=1.0 if provider else 0.0,
        procedure_code=(extraction.value("procedure_code") or "").strip() or None,
        diagnosis_codes=[c for c in [extraction.value("diagnosis_code")] if c],
        date_of_service=_parse_date(extraction.value("date_of_service")),
        units_requested=_parse_int(extraction.value("units_requested"), default=1),
        ambiguities=ambiguities,
    )


def _gather(repo: ClaimsRepository, resolved: ResolvedEntities) -> CaseFacts:
    """Collect records for whatever resolved.

    Anything unresolved simply stays absent, and the rules that need it
    return UNKNOWN rather than PASS -- which pends the case for a human
    instead of guessing at it.
    """
    if not (resolved.member_id and resolved.date_of_service):
        return CaseFacts(
            date_of_service=resolved.date_of_service,
            units_requested=resolved.units_requested,
            procedure=(
                repo.procedure(resolved.procedure_code)
                if resolved.procedure_code
                else None
            ),
        )

    facts = repo.gather(
        member_id=resolved.member_id,
        provider_npi=resolved.provider_npi or "",
        procedure_code=resolved.procedure_code or "",
        diagnosis_codes=resolved.diagnosis_codes,
        date_of_service=resolved.date_of_service,
        units_requested=resolved.units_requested,
        plan_year=PLAN_YEAR,
    )

    # A weak identity match is not a match. Drop the member rather than
    # adjudicate a benefit against a person we are not confident about.
    if resolved.member_match_confidence < ENTITY_MATCH_FLOOR:
        facts.member = None
        facts.plan = None
    return facts


def _retrieve(retriever: PolicyRetriever, facts: CaseFacts) -> list[PolicyClause]:
    if not facts.procedure or not facts.procedure.policy_document_id:
        return []
    return retriever.criteria_for(facts.procedure.policy_document_id)


def _judge(
    client: ModelClient,
    ledger: CostLedger,
    clauses: list[PolicyClause],
    extraction: ExtractedRequest,
    facts: CaseFacts,
) -> NecessityJudgment:
    dx = facts.diagnoses[0] if facts.diagnoses else None
    return judge_necessity(
        client=client,
        ledger=ledger,
        clauses=clauses,
        narrative=extraction.clinical_narrative,
        procedure_code=facts.procedure.code if facts.procedure else "unknown",
        procedure_description=facts.procedure.description if facts.procedure else "",
        diagnosis=f"{dx.code} — {dx.description}" if dx else "not supplied",
    )


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------


def _clean_id(value: str | None) -> str | None:
    """Reject a partially-illegible identifier rather than repair it.

    The extractor marks unreadable characters with '?'. Stripping them to
    make the id look valid would produce a lookup against a member who is
    not the one on the form.
    """
    if not value:
        return None
    value = value.strip()
    return None if "?" in value else value


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_int(value: str | None, default: int = 1) -> int:
    try:
        return max(1, int(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _known_procedure_codes() -> set[str]:
    from data.generator.reference import PROCEDURES_BY_CODE

    return set(PROCEDURES_BY_CODE)


def build_retriever(conn) -> PolicyRetriever:
    from packages.core.retrieval import load_clauses

    return PolicyRetriever(load_clauses(conn))
