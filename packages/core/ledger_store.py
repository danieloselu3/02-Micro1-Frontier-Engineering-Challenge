"""The write surface. Determinations in, review actions in, nothing else.

Deliberately separate from ClaimsRepository, which is read-only. An agent
holding claims tools can look up anything and change nothing; issuing a
determination requires this module, and this module is only ever called
after the release gate has run.

The review action is the audit trail and the signature block on the
determination letter at the same time. Nothing is issued without one, which
is the concrete form of "a qualified human reviewer is part of any decision
that significantly affects someone".
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import psycopg
from psycopg.rows import dict_row

from packages.core.models import (
    Determination,
    ExtractedRequest,
    ReviewAction,
    ReviewDecision,
    ReviewerRole,
    Verdict,
)


class LedgerStore:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    # -- writes ------------------------------------------------------------

    def record_submission(
        self,
        *,
        submission_id: str,
        channel: str,
        document_uri: str,
        degradation: str,
        case_id: str | None = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO submissions
                     (submission_id, channel, received_at, document_uri,
                      degradation, case_id)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (submission_id) DO UPDATE
                     SET document_uri = EXCLUDED.document_uri,
                         degradation  = EXCLUDED.degradation""",
                (
                    submission_id,
                    channel,
                    datetime.now(UTC),
                    document_uri,
                    degradation,
                    case_id,
                ),
            )
        self.conn.commit()

    def record_determination(
        self,
        det: Determination,
        extraction: ExtractedRequest | None = None,
    ) -> None:
        """Persist the determination and everything needed to review it.

        The full object graph goes into `payload` as JSON -- rule results
        with their evidence, the criteria assessments, the retrieved clauses,
        the extracted fields with their page coordinates. The reviewer
        console renders entirely from this, so what a nurse sees is exactly
        what the pipeline produced, not a reconstruction of it.
        """
        payload = det.model_dump(mode="json")
        if extraction:
            payload["extraction"] = extraction.model_dump(mode="json")

        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO determinations
                     (determination_id, submission_id, verdict, governing_rule,
                      reason, approved_units, approved_amount,
                      missing_information, payload, auto_released,
                      requires_human_review, model_cost_usd, elapsed_seconds,
                      created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (determination_id) DO UPDATE SET
                      verdict              = EXCLUDED.verdict,
                      governing_rule       = EXCLUDED.governing_rule,
                      reason               = EXCLUDED.reason,
                      payload              = EXCLUDED.payload,
                      auto_released        = EXCLUDED.auto_released,
                      requires_human_review= EXCLUDED.requires_human_review,
                      model_cost_usd       = EXCLUDED.model_cost_usd,
                      elapsed_seconds      = EXCLUDED.elapsed_seconds""",
                (
                    det.determination_id,
                    det.submission_id,
                    det.verdict.value,
                    det.governing_rule,
                    det.reason,
                    det.approved_units,
                    det.approved_amount,
                    det.missing_information,
                    json.dumps(payload),
                    det.auto_released,
                    det.requires_human_review,
                    det.model_cost_usd,
                    det.elapsed_seconds,
                    det.created_at,
                ),
            )
        self.conn.commit()

    def record_review(
        self,
        *,
        determination_id: str,
        reviewer_id: str,
        reviewer_name: str,
        reviewer_role: ReviewerRole,
        decision: ReviewDecision,
        final_verdict: Verdict,
        reason: str,
        field_corrections: dict[str, str] | None = None,
        seconds_spent: float = 0.0,
    ) -> ReviewAction:
        """Sign a determination.

        This is the only way a determination becomes issuable, and the row it
        writes names the person accountable for it.
        """
        action = ReviewAction(
            action_id=f"ACT-{uuid.uuid4().hex[:12]}",
            determination_id=determination_id,
            reviewer_id=reviewer_id,
            reviewer_name=reviewer_name,
            reviewer_role=reviewer_role,
            decision=decision,
            final_verdict=final_verdict,
            reason=reason,
            field_corrections=field_corrections or {},
            seconds_spent=seconds_spent,
            acted_at=datetime.now(UTC),
        )

        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO review_actions
                     (action_id, determination_id, reviewer_id, decision,
                      final_verdict, reason, field_corrections, seconds_spent,
                      acted_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    action.action_id,
                    action.determination_id,
                    action.reviewer_id,
                    action.decision.value,
                    action.final_verdict.value,
                    action.reason,
                    json.dumps(action.field_corrections),
                    action.seconds_spent,
                    action.acted_at,
                ),
            )
            # The determination now carries the reviewer's verdict, and is no
            # longer waiting on anyone.
            cur.execute(
                """UPDATE determinations
                      SET verdict = %s, requires_human_review = FALSE
                    WHERE determination_id = %s""",
                (final_verdict.value, determination_id),
            )
        self.conn.commit()
        return action

    # -- reads for the console --------------------------------------------

    def queue(self, limit: int = 100) -> list[dict]:
        """Cases waiting on a clinician, most fundamental problems first."""
        return self._all(
            """SELECT d.determination_id, d.submission_id, d.verdict,
                      d.governing_rule, d.reason, d.requires_human_review,
                      d.auto_released, d.model_cost_usd, d.elapsed_seconds,
                      d.created_at, s.degradation, s.channel,
                      d.payload -> 'escalation_reasons' AS escalation_reasons
                 FROM determinations d
                 LEFT JOIN submissions s USING (submission_id)
                WHERE d.requires_human_review
             ORDER BY
                   CASE d.verdict
                     WHEN 'denied' THEN 0
                     WHEN 'partially_approved' THEN 1
                     WHEN 'pended' THEN 2
                     ELSE 3
                   END,
                   d.created_at
                LIMIT %s""",
            (limit,),
        )

    def completed(self, limit: int = 50) -> list[dict]:
        return self._all(
            """SELECT d.determination_id, d.submission_id, d.verdict,
                      d.governing_rule, d.auto_released, d.created_at,
                      r.reviewer_id, r.acted_at, r.decision,
                      rv.name AS reviewer_name, rv.credentials
                 FROM determinations d
                 LEFT JOIN review_actions r USING (determination_id)
                 LEFT JOIN reviewers rv ON rv.reviewer_id = r.reviewer_id
                WHERE NOT d.requires_human_review
             ORDER BY COALESCE(r.acted_at, d.created_at) DESC
                LIMIT %s""",
            (limit,),
        )

    def determination(self, determination_id: str) -> dict | None:
        return self._one(
            """SELECT d.*, s.degradation, s.channel, s.document_uri, s.case_id
                 FROM determinations d
                 LEFT JOIN submissions s USING (submission_id)
                WHERE d.determination_id = %s""",
            (determination_id,),
        )

    def review_for(self, determination_id: str) -> dict | None:
        return self._one(
            """SELECT r.*, rv.name AS reviewer_name, rv.credentials, rv.role
                 FROM review_actions r
                 JOIN reviewers rv USING (reviewer_id)
                WHERE r.determination_id = %s
             ORDER BY r.acted_at DESC
                LIMIT 1""",
            (determination_id,),
        )

    def stats(self) -> dict:
        row = self._one(
            """SELECT COUNT(*)                                        AS total,
                      COUNT(*) FILTER (WHERE requires_human_review)    AS pending,
                      COUNT(*) FILTER (WHERE auto_released)            AS auto_released,
                      COALESCE(SUM(model_cost_usd), 0)                 AS total_cost,
                      COALESCE(AVG(elapsed_seconds), 0)                AS mean_seconds
                 FROM determinations""",
            (),
        )
        return row or {}

    # -- plumbing ----------------------------------------------------------

    def _one(self, sql: str, params: tuple) -> dict | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def _all(self, sql: str, params: tuple) -> list[dict]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
