"""Read-only access to payer records.

Deliberately read-only. This module and the MCP server that wraps it are the
only path an agent has to member, provider and benefit data, and none of it
can write. Determinations are written through a separate, human-gated
surface, so an agent holding these tools is structurally incapable of
issuing one.

Every method returns typed records rather than rows, so the rules engine can
be unit-tested against constructed objects with no database in the loop.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import psycopg
from psycopg.rows import dict_row

from packages.core.config import DATABASE_URL
from packages.core.records import (
    Accumulator,
    CaseFacts,
    Diagnosis,
    Member,
    Plan,
    PriorAuthorization,
    Procedure,
    Provider,
    Reviewer,
)


@contextmanager
def connect(dsn: str | None = None):
    with psycopg.connect(dsn or DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


class ClaimsRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    # -- single-record lookups ---------------------------------------------

    def member(self, member_id: str) -> Member | None:
        row = self._one("SELECT * FROM members WHERE member_id = %s", (member_id,))
        return Member(**row) if row else None

    def plan(self, plan_id: str) -> Plan | None:
        row = self._one("SELECT * FROM plans WHERE plan_id = %s", (plan_id,))
        return Plan(**row) if row else None

    def provider(self, npi: str) -> Provider | None:
        row = self._one("SELECT * FROM providers WHERE npi = %s", (npi,))
        return Provider(**row) if row else None

    def procedure(self, code: str) -> Procedure | None:
        row = self._one("SELECT * FROM procedures WHERE code = %s", (code,))
        return Procedure(**row) if row else None

    def diagnoses(self, codes: list[str]) -> list[Diagnosis]:
        if not codes:
            return []
        rows = self._all("SELECT * FROM diagnoses WHERE code = ANY(%s)", (codes,))
        by_code = {r["code"]: Diagnosis(**r) for r in rows}
        # Preserve submitted order; the first diagnosis is the primary one.
        return [by_code[c] for c in codes if c in by_code]

    def reviewer(self, reviewer_id: str) -> Reviewer | None:
        row = self._one("SELECT * FROM reviewers WHERE reviewer_id = %s", (reviewer_id,))
        return Reviewer(**row) if row else None

    def reviewers(self) -> list[Reviewer]:
        return [Reviewer(**r) for r in self._all("SELECT * FROM reviewers ORDER BY name")]

    # -- collections -------------------------------------------------------

    def accumulators(self, member_id: str, plan_year: int) -> list[Accumulator]:
        rows = self._all(
            "SELECT * FROM accumulators WHERE member_id = %s AND plan_year = %s",
            (member_id, plan_year),
        )
        return [Accumulator(**r) for r in rows]

    def prior_authorizations(self, member_id: str, code: str) -> list[PriorAuthorization]:
        rows = self._all(
            """SELECT * FROM prior_authorizations
               WHERE member_id = %s AND procedure_code = %s
               ORDER BY valid_from DESC""",
            (member_id, code),
        )
        return [PriorAuthorization(**r) for r in rows]

    def supporting_diagnoses(self, procedure_code: str) -> list[str]:
        rows = self._all(
            "SELECT diagnosis_code FROM code_pairs WHERE procedure_code = %s",
            (procedure_code,),
        )
        return [r["diagnosis_code"] for r in rows]

    # -- entity resolution -------------------------------------------------

    def match_member(
        self, member_id: str | None, name: str | None, dob: date | None
    ) -> tuple[Member | None, float, list[str]]:
        """Resolve a member from what was printed on the form.

        Returns the match, a confidence, and any ambiguities worth surfacing.
        Confidence is deliberately conservative: an exact id hit that
        disagrees with the printed name is *not* full confidence, because a
        transposed id can land on a real and entirely different person.
        """
        ambiguities: list[str] = []

        if member_id:
            found = self.member(member_id)
            if found:
                score = 1.0
                if name and name.strip().lower() != found.full_name.lower():
                    score = 0.94
                    ambiguities.append(
                        f"Form shows '{name}' against record '{found.full_name}'."
                    )
                if dob and dob != found.date_of_birth:
                    score = min(score, 0.55)
                    ambiguities.append(
                        f"Form shows date of birth {dob:%m/%d/%Y} against record "
                        f"{found.date_of_birth:%m/%d/%Y}."
                    )
                return found, score, ambiguities
            ambiguities.append(f"Member id '{member_id}' is not on file.")

        # Fall back to name plus date of birth. This is the path the
        # handwritten-id case has to take, and it must not guess the digit.
        #
        # A unique hit on surname *and* exact date of birth is strong
        # evidence -- two independent identifiers agreeing, with no other
        # member in the book matching both. It is arguably stronger than an
        # id read in isolation, because a transposed digit lands silently on
        # a real and entirely different person whereas this cannot.
        if name and dob:
            parts = name.strip().split()
            last = parts[-1] if parts else ""
            first = parts[0] if len(parts) > 1 else None
            rows = self._all(
                """SELECT * FROM members
                   WHERE date_of_birth = %s AND lower(last_name) = lower(%s)""",
                (dob, last),
            )
            if len(rows) == 1:
                found = Member(**rows[0])
                if first and first.casefold() == found.first_name.casefold():
                    score = 0.97  # both names and the date of birth agree
                else:
                    score = 0.93
                    if first:
                        ambiguities.append(
                            f"Given name on the form is '{first}' against record "
                            f"'{found.first_name}'; surname and date of birth match."
                        )
                return found, score, ambiguities
            if len(rows) > 1:
                ambiguities.append(
                    f"{len(rows)} members share that surname and date of birth; "
                    "identity cannot be resolved without a legible member id."
                )
                return None, 0.0, ambiguities

        return None, 0.0, ambiguities or ["No member could be resolved from the form."]

    # -- assembly ----------------------------------------------------------

    def gather(
        self,
        *,
        member_id: str,
        provider_npi: str,
        procedure_code: str,
        diagnosis_codes: list[str],
        date_of_service: date,
        units_requested: int = 1,
        plan_year: int | None = None,
    ) -> CaseFacts:
        """One deterministic pass that collects everything the rules need.

        Gathering up front rather than letting each rule fetch its own data
        keeps the rules pure, makes the whole evaluation replayable from a
        fixture, and means the reviewer console can show exactly the record
        set the decision was made on.
        """
        member = self.member(member_id)
        plan = self.plan(member.plan_id) if member else None
        year = plan_year or date_of_service.year

        return CaseFacts(
            member=member,
            plan=plan,
            provider=self.provider(provider_npi),
            procedure=self.procedure(procedure_code),
            diagnoses=self.diagnoses(diagnosis_codes),
            accumulators=self.accumulators(member_id, year) if member else [],
            prior_auths=self.prior_authorizations(member_id, procedure_code) if member else [],
            valid_diagnosis_codes=self.supporting_diagnoses(procedure_code),
            date_of_service=date_of_service,
            units_requested=units_requested,
        )

    # -- plumbing ----------------------------------------------------------

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
