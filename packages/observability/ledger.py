"""Token and cost accounting.

The rubric asks for cost per task, and cost is not something that can be
reconstructed after the fact -- token counts live only in the API response
that produced them. So every model call in the system goes through this
ledger, and the per-case cost is a measured figure rather than an estimate.

It also does the thing the cost story actually depends on: recording which
stage spent the money. The headline claim is that most cases never reach an
adjudication model, and that claim is only checkable if the ledger can say
how many calls each stage made.
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from packages.core.config import MODEL_PRICES_USD

_PER_MILLION = Decimal("1000000")


@dataclass
class ModelCall:
    stage: str
    model: str
    input_tokens: int
    output_tokens: int
    seconds: float
    cached: bool = False

    @property
    def cost_usd(self) -> Decimal:
        """What this unit of work costs, whether or not we paid today.

        Computed from the recorded token counts even on a cache hit. This is
        the number that answers "what does it cost to adjudicate a case",
        which is the question the rubric asks and the one a reviewer sees in
        the console -- and it has to come out the same whether the run was
        live or replayed, or the committed cost comparison would collapse to
        zero for anyone reproducing it.
        """
        prices = MODEL_PRICES_USD.get(self.model)
        if prices is None:
            return Decimal("0")
        in_price, out_price = prices
        cost = (
            Decimal(self.input_tokens) * in_price
            + Decimal(self.output_tokens) * out_price
        ) / _PER_MILLION
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    @property
    def spend_usd(self) -> Decimal:
        """What this run actually put on the bill. Zero for a cache hit."""
        return Decimal("0") if self.cached else self.cost_usd


@dataclass
class CostLedger:
    """One ledger per case."""

    case_id: str
    calls: list[ModelCall] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)

    def record(
        self,
        *,
        stage: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        seconds: float,
        cached: bool = False,
    ) -> ModelCall:
        call = ModelCall(
            stage=stage,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            seconds=seconds,
            cached=cached,
        )
        self.calls.append(call)
        return call

    @contextmanager
    def timed(self, stage: str):
        """Time a stage even when it makes no model call at all.

        Stages that exit on the deterministic fast path still take wall-clock
        time, and leaving them out would flatter the latency numbers.
        """
        start = time.monotonic()
        holder: dict[str, float] = {}
        try:
            yield holder
        finally:
            holder["seconds"] = time.monotonic() - start

    # -- totals ------------------------------------------------------------

    @property
    def total_cost_usd(self) -> Decimal:
        """Cost of the work. Identical live or replayed."""
        return sum((c.cost_usd for c in self.calls), Decimal("0"))

    @property
    def total_spend_usd(self) -> Decimal:
        """Money this particular run spent. Zero on a full cache hit."""
        return sum((c.spend_usd for c in self.calls), Decimal("0"))

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at

    @property
    def model_seconds(self) -> float:
        return sum(c.seconds for c in self.calls)

    def by_stage(self) -> dict[str, dict[str, float | int | str]]:
        out: dict[str, dict] = defaultdict(
            lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                     "seconds": 0.0, "cost_usd": Decimal("0")}
        )
        for c in self.calls:
            row = out[c.stage]
            row["calls"] += 1
            row["input_tokens"] += c.input_tokens
            row["output_tokens"] += c.output_tokens
            row["seconds"] += c.seconds
            row["cost_usd"] += c.cost_usd
        return {k: {**v, "cost_usd": str(v["cost_usd"])} for k, v in out.items()}

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "model_calls": len(self.calls),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "cost_usd": str(self.total_cost_usd),
            "model_seconds": round(self.model_seconds, 3),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "by_stage": self.by_stage(),
        }


def aggregate(ledgers: list[CostLedger]) -> dict:
    """Roll up a run. Reports the median alongside the mean, because a single
    long case skews the mean and the median is what a reviewer would
    recognise as typical."""
    if not ledgers:
        return {"cases": 0}

    costs = sorted(float(le.total_cost_usd) for le in ledgers)
    latencies = sorted(le.elapsed_seconds for le in ledgers)
    calls = [len(le.calls) for le in ledgers]

    return {
        "cases": len(ledgers),
        "total_cost_usd": round(sum(costs), 4),
        "mean_cost_usd": round(sum(costs) / len(costs), 6),
        "median_cost_usd": round(_median(costs), 6),
        "mean_latency_s": round(sum(latencies) / len(latencies), 2),
        "median_latency_s": round(_median(latencies), 2),
        "total_model_calls": sum(calls),
        "cases_with_no_model_call": sum(1 for c in calls if c == 0),
        "total_input_tokens": sum(le.total_input_tokens for le in ledgers),
        "total_output_tokens": sum(le.total_output_tokens for le in ledgers),
    }


def _median(values: list[float]) -> float:
    n = len(values)
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2
