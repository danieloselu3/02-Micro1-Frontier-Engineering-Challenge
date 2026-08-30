"""Retrieval over the policy corpus.

The design choice worth stating: **the procedure code selects the document
deterministically, and retrieval only ranks clauses within it.**

A pure vector search over the whole corpus would be the conventional move
and it is the wrong one here. Medical policies are written to look alike --
every one of them contains a "failure of conservative management" clause
phrased almost identically -- so nearest-neighbour search across documents
reliably retrieves the conservative-therapy criterion from the *knee*
policy when adjudicating a *spine* request. The clinical language is
similar; the thresholds are not.

But the payer already knows exactly which policy governs CPT 72148, because
that mapping is a maintained business record rather than something to be
inferred. So we look it up, and spend retrieval only on the question it is
actually good at: which clauses within this document bear on this narrative.

Scoring is BM25 over the clause text. That keeps the whole path offline,
deterministic, and free -- retrieval never varies between runs, which means
a change in evaluation results is always attributable to something we
actually changed.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from packages.core.models import PolicyClause

_WORD = re.compile(r"[a-z0-9]+")

# Terms that appear in nearly every clause carry no discriminating signal.
_STOPWORDS = frozenset(
    """
    a an and are as at be been by criterion do does for from has have in is it
    its not of on or that the this to was were where which with within must
    least does not member record documented policy applies request requests
    """.split()
)


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2]


class ClauseIndex:
    """A small BM25 index over one corpus of clauses.

    Built once per process from the database. The corpus is 68 clauses, so
    an in-memory index is not a compromise -- it is simply the right size.
    """

    K1 = 1.5
    B = 0.75

    def __init__(self, clauses: list[PolicyClause]) -> None:
        self.clauses = clauses
        self._tokens = [tokenize(c.text) for c in clauses]
        self._lengths = [len(t) for t in self._tokens]
        self._avg_len = (sum(self._lengths) / len(self._lengths)) if clauses else 0.0
        self._tf = [Counter(t) for t in self._tokens]

        df: Counter[str] = Counter()
        for toks in self._tokens:
            df.update(set(toks))
        n = len(clauses)
        self._idf = {
            term: math.log(1 + (n - count + 0.5) / (count + 0.5))
            for term, count in df.items()
        }

    def search(
        self,
        query: str,
        *,
        document_ids: list[str] | None = None,
        limit: int = 8,
    ) -> list[PolicyClause]:
        """Rank clauses against the query, optionally scoped to documents."""
        terms = tokenize(query)
        scored: list[tuple[float, PolicyClause]] = []

        for i, clause in enumerate(self.clauses):
            if document_ids and clause.document_id not in document_ids:
                continue
            score = self._score(terms, i)
            scored.append((score, clause))

        scored.sort(key=lambda pair: (-pair[0], pair[1].clause_id))
        out: list[PolicyClause] = []
        for score, clause in scored[:limit]:
            out.append(clause.model_copy(update={"score": round(score, 4)}))
        return out

    def _score(self, terms: list[str], doc: int) -> float:
        tf, length = self._tf[doc], self._lengths[doc]
        if not length:
            return 0.0
        total = 0.0
        for term in terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = self._idf.get(term, 0.0)
            denom = freq + self.K1 * (1 - self.B + self.B * length / self._avg_len)
            total += idf * (freq * (self.K1 + 1)) / denom
        return total


class PolicyRetriever:
    """The retrieval surface the adjudicator sees."""

    def __init__(self, clauses: list[PolicyClause]) -> None:
        self.index = ClauseIndex(clauses)
        self._by_document: dict[str, list[PolicyClause]] = {}
        for c in clauses:
            self._by_document.setdefault(c.document_id, []).append(c)
        for group in self._by_document.values():
            group.sort(key=lambda c: _ordinal(c.clause_id))

    #: Clause roles the necessity judgment is asked to assess. Scope
    #: statements and closing notes are context, not requirements -- asking
    #: whether the documentation "establishes the scope paragraph" produces a
    #: no-evidence finding on every single request, and pends all of them.
    ASSESSABLE = ("criterion", "exception")

    def criteria_for(self, policy_document_id: str) -> list[PolicyClause]:
        """The assessable clauses of the governing policy, in document order.

        The necessity judgment gets the *complete* set of them, not the top-k
        most similar to the narrative. Ranking would be actively harmful: the
        criterion a narrative fails to mention is precisely the one least
        similar to it, so a similarity cut-off would silently drop the
        criterion most likely to matter and turn a pend into an approval.

        What is filtered out is by role, not by score. Scope and notes are
        excluded because nothing can fail them.
        """
        return [
            c
            for c in self._by_document.get(policy_document_id, [])
            if c.role in self.ASSESSABLE
        ]

    def all_clauses_for(self, policy_document_id: str) -> list[PolicyClause]:
        """Everything, including scope and notes -- for the reviewer to read."""
        return list(self._by_document.get(policy_document_id, []))

    def coverage_clauses(self, coverage_document_id: str, query: str, limit: int = 3):
        """Contract language relevant to a question -- exclusions, appeals."""
        return self.index.search(query, document_ids=[coverage_document_id], limit=limit)

    def search(self, query: str, limit: int = 5) -> list[PolicyClause]:
        return self.index.search(query, limit=limit)


def _ordinal(clause_id: str) -> tuple[int, str]:
    """Sort '#0' before '#1' before '#F', numerically not lexically."""
    suffix = clause_id.rsplit("#", 1)[-1]
    return (int(suffix), "") if suffix.isdigit() else (10_000, suffix)


def load_clauses(conn) -> list[PolicyClause]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.clause_id, c.document_id, c.text, c.role,
                      d.title AS document_title, d.version
               FROM policy_chunks c
               JOIN policy_documents d USING (document_id)
               ORDER BY c.document_id, c.ordinal"""
        )
        return [PolicyClause(**row) for row in cur.fetchall()]
