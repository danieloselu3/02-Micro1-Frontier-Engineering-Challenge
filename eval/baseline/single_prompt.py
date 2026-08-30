"""The baseline: one prompt, one model call, one verdict.

This is the comparator the improvement is measured against, and it is built
to be genuinely fair rather than a straw man. It receives:

  * the same form image the real pipeline reads
  * the member, plan, provider, procedure, accumulator and prior-auth
    records the MCP tools would have fetched, rendered as text
  * the full text of the governing medical policy

So the baseline is not handicapped on information. It has everything. What
it lacks is *architecture*: no deterministic rule evaluation, no separation
between reading and judging, no verification pass, no release gate. It does
what a competent engineer would do first -- put it all in the context window
and ask for an answer.

Keeping the information equal is what makes the comparison mean something.
Any difference in the results is attributable to how the work was decomposed,
not to one system having been shown more than the other.

It is also given the same answer vocabulary. The first recorded run left the
`governing_rule` field free-form, and the baseline answered substantively
correctly in prose -- "coverage terminated", "PLN-HMO-CORE
waiting_period_days" -- while scoring 0% on reason accuracy purely because it
did not guess the rule identifiers the grader compares against. That measured
formatting compliance, not reasoning, and would have overstated the
improvement considerably. The rule catalogue below fixes that.
"""

from __future__ import annotations

from pathlib import Path

from agents.client import ModelClient, extract_json
from agents.intake_extractor.agent import _image_block, load_page
from packages.core.config import ADJUDICATION_MODEL
from packages.core.models import Verdict
from packages.core.records import CaseFacts
from packages.core.retrieval import PolicyRetriever
from packages.observability.ledger import CostLedger

STAGE = "baseline"

SYSTEM = """\
You are a utilization management reviewer for a US commercial health plan.

You are given a prior-authorization request form, the plan records for the
member and provider involved, and the medical policy that governs the
requested procedure. Decide the request.

Consider everything that bears on the decision: whether coverage was active on
the date of service, whether any waiting period had elapsed, whether the plan
covers this benefit category, whether the provider is in the service area and
in good standing, whether the benefit has enough remaining, whether an
authorization already exists, whether the diagnosis supports the procedure, and
whether the clinical documentation meets the policy criteria.

Return a single JSON object and nothing else:

{
  "verdict": "approved | partially_approved | denied | pended | no_auth_required",
  "governing_rule": "the identifier of the single check that decided this",
  "reason": "the explanation a reviewer and the member would read",
  "missing_information": ["what to request, if the verdict is pended"]
}

Use "no_auth_required" when the procedure does not require prior authorization
under this plan. Use "pended" when you need something before you can decide.

For "governing_rule", give exactly one identifier from this catalogue -- the
single check that actually decided the case, not a list:

  R1  the procedure does not require prior authorization
  R2  member eligibility: coverage inactive, terminated, or suspended
  R3  the plan's waiting period had not elapsed
  R4  the benefit category is excluded under the plan
  R5  the provider is outside the plan's service area
  R6  provider standing: sanctioned, unlicensed, uncontracted, or out of network
  R7  the benefit accumulator has insufficient balance remaining
  R8  an active authorization already covers this procedure
  R9  the diagnosis does not support the procedure code

If none of the above decided it and the case turned on the clinical
documentation, give the medical policy document id instead -- for example
"MP-IMG-001". Use the document id alone, without a clause suffix.
"""


def run_baseline(
    *,
    client: ModelClient,
    ledger: CostLedger,
    document_path: Path,
    facts: CaseFacts,
    retriever: PolicyRetriever,
    model: str = ADJUDICATION_MODEL,
) -> dict:
    image = load_page(document_path)
    records = render_records(facts)
    policy = _policy_text(retriever, facts)

    raw = client.complete(
        stage=STAGE,
        model=model,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    _image_block(image),
                    {
                        "type": "text",
                        "text": (
                            f"## Plan records\n\n{records}\n\n"
                            f"## Governing medical policy\n\n{policy}\n\n"
                            "## Task\n\nDecide this prior-authorization "
                            "request. Return the JSON object described in "
                            "your instructions and nothing else."
                        ),
                    },
                ],
            }
        ],
        ledger=ledger,
        # The first run capped this at 2000 and truncated 3 of 49 responses
        # mid-object, which the harness then scored as failures. Those were
        # the harness's fault, not the baseline's. Sized with headroom now:
        # the longest untruncated baseline response was well under half this.
        max_tokens=8000,
    )

    try:
        data = extract_json(raw)
    except ValueError:
        return {
            "verdict": Verdict.PENDED,
            "governing_rule": "unparseable",
            "reason": "The baseline returned output that could not be parsed.",
            "missing_information": [],
        }

    return {
        "verdict": _verdict(data.get("verdict")),
        "governing_rule": str(data.get("governing_rule", "")).strip() or "unspecified",
        "reason": str(data.get("reason", "")).strip(),
        "missing_information": [
            str(m) for m in data.get("missing_information", []) if str(m).strip()
        ],
    }


def _verdict(value) -> Verdict:
    try:
        return Verdict(str(value).strip().lower())
    except ValueError:
        return Verdict.PENDED


def render_records(facts: CaseFacts) -> str:
    """Every record the pipeline's tools would have returned, as plain text."""
    out: list[str] = []

    if facts.member:
        m = facts.member
        out.append(
            f"MEMBER\n"
            f"  member_id: {m.member_id}\n"
            f"  name: {m.full_name}\n"
            f"  date_of_birth: {m.date_of_birth}\n"
            f"  sex: {m.sex}\n"
            f"  status: {m.status.value}\n"
            f"  plan_id: {m.plan_id}\n"
            f"  effective_date: {m.effective_date}\n"
            f"  termination_date: {m.termination_date}\n"
            f"  premium_paid_through: {m.premium_paid_through}\n"
            f"  enrolled_at: {m.enrolled_at}\n"
            f"  state: {m.state}"
        )
    else:
        out.append("MEMBER\n  (no member record resolved)")

    if facts.plan:
        p = facts.plan
        out.append(
            f"PLAN\n"
            f"  plan_id: {p.plan_id}\n"
            f"  name: {p.name}\n"
            f"  waiting_period_days: {p.waiting_period_days}\n"
            f"  requires_in_network: {p.requires_in_network}\n"
            f"  covered_states: {', '.join(p.covered_states)}\n"
            f"  excluded_categories: {', '.join(p.excluded_categories) or 'none'}"
        )

    if facts.provider:
        pr = facts.provider
        out.append(
            f"PROVIDER\n"
            f"  npi: {pr.npi}\n"
            f"  name: {pr.name}\n"
            f"  specialty: {pr.specialty}\n"
            f"  network_tier: {pr.network_tier.value}\n"
            f"  license_state: {pr.license_state}\n"
            f"  license_expiry: {pr.license_expiry}\n"
            f"  contract_start: {pr.contract_start}\n"
            f"  contract_end: {pr.contract_end}\n"
            f"  sanctioned: {pr.sanctioned}"
        )
    else:
        out.append("PROVIDER\n  (no provider record resolved)")

    if facts.procedure:
        pc = facts.procedure
        out.append(
            f"PROCEDURE\n"
            f"  code: {pc.code}\n"
            f"  description: {pc.description}\n"
            f"  category: {pc.category}\n"
            f"  requires_preauth: {pc.requires_preauth}\n"
            f"  unit_cost: {pc.unit_cost}\n"
            f"  always_review: {pc.always_review}"
        )

    if facts.diagnoses:
        lines = "\n".join(f"  {d.code}: {d.description}" for d in facts.diagnoses)
        out.append(f"DIAGNOSES SUBMITTED\n{lines}")

    if facts.valid_diagnosis_codes:
        out.append(
            "DIAGNOSES THAT SUPPORT THIS PROCEDURE\n  "
            + ", ".join(facts.valid_diagnosis_codes)
        )

    if facts.accumulators:
        lines = "\n".join(
            f"  {a.category}: limit {a.limit_amount}, consumed "
            f"{a.consumed_amount}, remaining {a.remaining}"
            for a in facts.accumulators
        )
        out.append(f"BENEFIT ACCUMULATORS (plan year)\n{lines}")

    if facts.prior_auths:
        lines = "\n".join(
            f"  {a.auth_id}: {a.procedure_code}, valid {a.valid_from} to "
            f"{a.valid_to}, status {a.status}"
            for a in facts.prior_auths
        )
        out.append(f"EXISTING AUTHORIZATIONS\n{lines}")
    else:
        out.append("EXISTING AUTHORIZATIONS\n  (none on file)")

    out.append(
        f"REQUEST\n"
        f"  date_of_service: {facts.date_of_service}\n"
        f"  units_requested: {facts.units_requested}"
    )

    return "\n\n".join(out)


def _policy_text(retriever: PolicyRetriever, facts: CaseFacts) -> str:
    if not facts.procedure or not facts.procedure.policy_document_id:
        return "(no medical policy applies to this procedure)"
    clauses = retriever.criteria_for(facts.procedure.policy_document_id)
    return "\n\n".join(f"[{c.clause_id}]\n{c.text}" for c in clauses) or "(none)"
