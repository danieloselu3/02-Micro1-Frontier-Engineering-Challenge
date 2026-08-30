"""Model client with record/replay.

Every model call in the system goes through here, and every response is
cached on disk keyed by a hash of the exact request. Two consequences, both
of which the project depends on:

* **The evaluation reproduces without an API key.** The cache is committed,
  so `make eval-replay` re-runs both systems over all 49 cases from the
  recorded responses. A judge starting from a clean clone reaches the
  headline number with no account, no credentials, and no spend. That
  directly answers the reproducibility criterion instead of asking them to
  take our numbers on trust.

* **Iteration is cheap and comparable.** Re-running the harness after a
  prompt change only pays for the calls whose prompt actually changed, and
  unchanged stages return byte-identical output -- so a movement in the
  results is attributable to the edit rather than to sampling noise.

The cache key covers the model, the full message payload and the sampling
parameters, so any change to a prompt produces a miss rather than a stale
hit. Temperature is pinned to 0 throughout; it is not a knob worth having
when the output feeds a medical determination.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from packages.observability.ledger import CostLedger

CACHE_DIR = Path(__file__).resolve().parents[1] / "eval" / "cache"


class ReplayMiss(RuntimeError):
    """A replay run needed a response that was never recorded."""


class ModelClient:
    """Anthropic wrapper with an on-disk response cache.

    modes:
      "auto"   -- use the cache when warm, call the API otherwise (default)
      "replay" -- cache only; a miss is an error rather than a silent API call
      "live"   -- always call the API and refresh the cache
    """

    def __init__(
        self,
        *,
        mode: str = "auto",
        cache_dir: Path | None = None,
        api_key: str | None = None,
    ) -> None:
        self.mode = mode
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client: Any = None
        self.hits = 0
        self.misses = 0

    # -- public ------------------------------------------------------------

    def complete(
        self,
        *,
        stage: str,
        model: str,
        system: str,
        messages: list[dict],
        ledger: CostLedger,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> str:
        payload = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        key = self._key(payload)
        path = self.cache_dir / f"{key}.json"

        if self.mode != "live" and path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            self.hits += 1
            ledger.record(
                stage=stage,
                model=model,
                input_tokens=record["input_tokens"],
                output_tokens=record["output_tokens"],
                seconds=record.get("seconds", 0.0),
                cached=True,
            )
            return record["text"]

        if self.mode == "replay":
            raise ReplayMiss(
                f"No recorded response for stage '{stage}' (key {key[:12]}). "
                "The prompts have changed since the cache was recorded. "
                "Re-record with: make eval  (requires ANTHROPIC_API_KEY)"
            )

        text, usage, seconds = self._call_api(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self.misses += 1
        path.write_text(
            json.dumps(
                {
                    "stage": stage,
                    "model": model,
                    "text": text,
                    "input_tokens": usage[0],
                    "output_tokens": usage[1],
                    "seconds": round(seconds, 3),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        ledger.record(
            stage=stage,
            model=model,
            input_tokens=usage[0],
            output_tokens=usage[1],
            seconds=seconds,
        )
        return text

    # -- internals ---------------------------------------------------------

    def _key(self, payload: dict) -> str:
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _call_api(
        self, *, model: str, system: str, messages: list[dict],
        max_tokens: int, temperature: float,
    ) -> tuple[str, tuple[int, int], float]:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Either export it, or run "
                    "`make eval-replay` to reproduce the committed results "
                    "from the recorded responses."
                )
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self._api_key)

        start = time.monotonic()
        resp = self._client.messages.create(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        seconds = time.monotonic() - start
        text = "".join(block.text for block in resp.content if block.type == "text")
        return text, (resp.usage.input_tokens, resp.usage.output_tokens), seconds


# --------------------------------------------------------------------------
# Structured output
# --------------------------------------------------------------------------


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model response.

    Models wrap JSON in prose or fences often enough that a bare
    json.loads is a liability in a pipeline that must not crash mid-case.
    Raises ValueError with the offending text when nothing parses, so the
    harness can record the case as a failure rather than losing the run.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1: -1 if lines[-1].strip() == "```" else None])
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Unparseable JSON in model response: {text[:400]}") from exc

    raise ValueError(f"No JSON object found in model response: {text[:400]}")
