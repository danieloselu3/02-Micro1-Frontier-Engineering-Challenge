"""The reviewer console.

Server-rendered Jinja with a little vanilla JavaScript, and no build step on
purpose: a judge reproducing this runs `docker compose up` and `make console`,
with no npm install between them and the working system.

The screen is organised around one principle -- a reviewer cannot verify a
verdict, only evidence. So the recommendation is never the first thing on the
page. The document and the facts come first, every number is traceable to the
record or the page region it came from, and the agent's opinion sits where a
second opinion belongs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from packages.core.ledger_store import LedgerStore
from packages.core.models import ReviewDecision, ReviewerRole, Verdict
from packages.core.repository import ClaimsRepository, connect

BASE = Path(__file__).parent
FORM_DIR = Path(__file__).resolve().parents[2] / "data" / "seeds" / "forms"

app = FastAPI(title="Meridian Utilization Review")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["money"] = lambda v: f"${float(v):,.2f}" if v is not None else "—"
templates.env.filters["ago"] = lambda dt: _ago(dt)


# --------------------------------------------------------------------------
# Document preview
# --------------------------------------------------------------------------

PREVIEW_DIR = BASE / ".previews"


@app.get("/preview/{name}")
def preview(name: str):
    """Serve any submitted document as a PNG.

    Portal submissions arrive as PDFs, which a browser cannot draw field
    overlays on top of. Rendering every document to an image means the
    provenance overlay works identically whether the request came through the
    portal or off a fax, rather than only for the degraded half.

    Rendered once and cached on disk; these are immutable per submission.
    """
    source = (FORM_DIR / name).resolve()
    # Containment check: `name` comes off the URL, and a document store is
    # exactly the sort of route that turns into a path traversal.
    if FORM_DIR.resolve() not in source.parents or not source.exists():
        raise HTTPException(404, "No such document")

    if source.suffix.lower() != ".pdf":
        return FileResponse(source)

    PREVIEW_DIR.mkdir(exist_ok=True)
    rendered = PREVIEW_DIR / f"{source.stem}.png"
    if not rendered.exists():
        from data.generator.forms import pdf_to_image

        pdf_to_image(source.read_bytes()).save(rendered, format="PNG", optimize=True)
    return FileResponse(rendered)


# --------------------------------------------------------------------------
# Queue
# --------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def queue(request: Request):
    with connect() as conn:
        store = LedgerStore(conn)
        pending = store.queue()
        done = store.completed(limit=12)
        stats = store.stats()

    return templates.TemplateResponse(
        request,
        "queue.html",
        {"pending": pending, "completed": done, "stats": stats},
    )


# --------------------------------------------------------------------------
# One case
# --------------------------------------------------------------------------


@app.get("/case/{determination_id}", response_class=HTMLResponse)
def case(request: Request, determination_id: str):
    with connect() as conn:
        store = LedgerStore(conn)
        repo = ClaimsRepository(conn)

        row = store.determination(determination_id)
        if not row:
            raise HTTPException(404, "No such determination")

        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        review = store.review_for(determination_id)
        reviewers = repo.reviewers()

    return templates.TemplateResponse(
        request,
        "case.html",
        {
            "det": row,
            "p": payload,
            "extraction": payload.get("extraction") or {},
            "rules": (payload.get("rule_report") or {}).get("results", []),
            "necessity": payload.get("necessity"),
            "critic": payload.get("critic"),
            "clauses": payload.get("retrieved_clauses", []),
            "escalations": payload.get("escalation_reasons", []),
            "document": _document_name(row),
            "review": review,
            "reviewers": reviewers,
            "verdicts": [v.value for v in Verdict],
        },
    )


@app.post("/case/{determination_id}/decide")
def decide(
    determination_id: str,
    reviewer_id: str = Form(...),
    decision: str = Form(...),
    final_verdict: str = Form(...),
    reason: str = Form(""),
    seconds_spent: float = Form(0.0),
):
    """Sign the determination.

    The reason is mandatory whenever the reviewer departs from the
    recommendation. An override with no stated basis is unreviewable later,
    and it is also the most valuable signal the system produces -- it is
    exactly where the agent and a clinician disagreed.
    """
    with connect() as conn:
        store = LedgerStore(conn)
        repo = ClaimsRepository(conn)

        row = store.determination(determination_id)
        if not row:
            raise HTTPException(404, "No such determination")

        reviewer = repo.reviewer(reviewer_id)
        if not reviewer:
            raise HTTPException(400, "Unknown reviewer")

        try:
            decision_enum = ReviewDecision(decision)
            verdict_enum = Verdict(final_verdict)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        if decision_enum != ReviewDecision.CONFIRM and not reason.strip():
            raise HTTPException(400, "A reason is required when overriding.")

        store.record_review(
            determination_id=determination_id,
            reviewer_id=reviewer.reviewer_id,
            reviewer_name=reviewer.name,
            reviewer_role=(
                ReviewerRole.MEDICAL_DIRECTOR
                if reviewer.role == "medical_director"
                else ReviewerRole.NURSE
            ),
            decision=decision_enum,
            final_verdict=verdict_enum,
            reason=reason.strip(),
            seconds_spent=seconds_spent,
        )

    return RedirectResponse(f"/case/{determination_id}/letter", status_code=303)


# --------------------------------------------------------------------------
# The determination letter
# --------------------------------------------------------------------------


@app.get("/case/{determination_id}/letter", response_class=HTMLResponse)
def letter(request: Request, determination_id: str):
    """The artifact that actually leaves the building.

    Carries the signing clinician's name and credentials, the governing
    clause, and appeal rights -- the things a provider or member needs in
    order to act on it or contest it.
    """
    with connect() as conn:
        store = LedgerStore(conn)
        repo = ClaimsRepository(conn)

        row = store.determination(determination_id)
        if not row:
            raise HTTPException(404, "No such determination")

        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        review = store.review_for(determination_id)
        extraction = payload.get("extraction") or {}
        member = None
        member_id = _field_value(extraction, "member_id")
        if member_id:
            member = repo.member(member_id)

    return templates.TemplateResponse(
        request,
        "letter.html",
        {
            "det": row,
            "p": payload,
            "review": review,
            "member": member,
            "extraction": extraction,
            "today": datetime.now(UTC),
        },
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _document_name(row: dict) -> str | None:
    uri = row.get("document_uri")
    if uri:
        return Path(uri).name
    case_id = row.get("case_id") or row.get("submission_id")
    for suffix in (".pdf", ".png"):
        if (FORM_DIR / f"{case_id}{suffix}").exists():
            return f"{case_id}{suffix}"
    return None


def _field_value(extraction: dict, name: str) -> str | None:
    field = (extraction.get("fields") or {}).get(name) or {}
    return field.get("value")


def _ago(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    seconds = (datetime.now(UTC) - value).total_seconds()
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{int(seconds // 60)} min"
    if seconds < 172800:
        return f"{int(seconds // 3600)} hr"
    return f"{int(seconds // 86400)} d"
