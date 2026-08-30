"""Runtime configuration.

Thresholds that shape decisions live here rather than in the code that uses
them, so the changelog can record exactly what was tuned between iterations
and the reviewer console can display the policy it is operating under.
"""

from __future__ import annotations

import os
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# -- infrastructure ---------------------------------------------------------

DATABASE_URL = _env("DATABASE_URL", "postgresql://preauth:preauth@localhost:5432/preauth")
REDIS_URL = _env("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = _env("QUEUE_NAME", "preauth_submissions")

# -- models -----------------------------------------------------------------

EXTRACTION_MODEL = _env("EXTRACTION_MODEL", "claude-sonnet-5")
ADJUDICATION_MODEL = _env("ADJUDICATION_MODEL", "claude-sonnet-5")
CRITIC_MODEL = _env("CRITIC_MODEL", "claude-haiku-4-5-20251001")

# Published per-million-token prices, used by the cost ledger. Kept here so a
# price change is one edit and every historical report stays reproducible.
MODEL_PRICES_USD: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5-20251001": (Decimal("1.00"), Decimal("5.00")),
}

# -- decision policy --------------------------------------------------------

#: A field read below this is re-read with a targeted crop before it is used.
FIELD_REREAD_THRESHOLD = float(_env("FIELD_REREAD_THRESHOLD", "0.85"))

#: A field still below this after re-reading blocks auto-release.
FIELD_CONFIDENCE_FLOOR = float(_env("FIELD_CONFIDENCE_FLOOR", "0.95"))

#: A member match weaker than this is an ambiguity, not a match.
ENTITY_MATCH_FLOOR = float(_env("ENTITY_MATCH_FLOOR", "0.92"))

#: Approvals above this dollar amount always get a human, however clean.
AUTO_RELEASE_COST_CEILING = Decimal(_env("AUTO_RELEASE_COST_CEILING", "2500"))

#: Necessity judgments below this confidence always get a human.
NECESSITY_CONFIDENCE_FLOOR = float(_env("NECESSITY_CONFIDENCE_FLOOR", "0.80"))

#: Denials never auto-release. This is not configurable on purpose: a denial
#: affects someone's care and carries a clinician's name, always.
DENIALS_ALWAYS_REVIEWED = True
