"""ROI P1/T04 — pure pricing layer: price snapshots and cost math.

Scope (pure layer only): given per-model token rows — ``list[(model_id,
{bucket: tokens})]`` — and a :class:`PriceSnapshot`, compute the
cloud-equivalent cost in the snapshot's currency. No I/O, no DB, no config
reads, no floats anywhere in the money path.

Token-bucket semantics (audited assumption, see docs/DATA_CONTRACT.md §3):
the five buckets ``input``, ``output``, ``cache_read``, ``cache_write``,
``reasoning`` are DISJOINT source columns of ``sessions`` /
``session_model_usage``. ``input`` is *uncached* input (the wire's cached
tokens are subtracted back out before storage), ``cache_read`` and
``cache_write`` are reported separately, and ``reasoning`` is a display-only
subset of ``output`` that the default rate card prices at 0 (it is never
added to the billed total a second time). Because the columns are disjoint
and each is multiplied by exactly one bucket price, the sum
``sum(bucket_tokens[b] * price[b])`` CANNOT double-count. That is the
audited assumption this module's math rests on; a future column that
overlaps an existing bucket must change DATA_CONTRACT.md §3 first.

Money semantics (docs/DATA_CONTRACT.md §10): the result is a
*hypothetical benchmark* (what this usage would cost in the cloud), NOT a
stored ``estimated_cost_usd``/``actual_cost_usd`` value, which is audit
context only and never summed into recovered hardware.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Optional, Sequence

#: The five disjoint token buckets, in canonical order (DATA_CONTRACT §3).
BUCKETS: tuple[str, ...] = ("input", "output", "cache_read", "cache_write", "reasoning")

#: Per-million-token divisor. The division happens exactly ONCE, at the end
#: of :func:`compute_cost` — every intermediate product is an integer-token
#: count times a Decimal unit price (exact).
_PER_MILLION = Decimal(1_000_000)

#: Final quantize of a cost: 6 decimal places = one micro unit of the
#: snapshot currency (e.g. USD 0.000001). Rounding mode ROUND_HALF_UP,
#: documented per ticket T04. Costs accumulate per model row and are summed
#: at that precision; a snapshot with many models therefore loses at most
#: half a micro unit per model (audited, bounded).
_COST_EXP = Decimal("0.000001")


class PricingError(ValueError):
    """Malformed pricing input (bad bucket name, negative token count...)."""


class UnknownPrice:
    """Explicit marker: the snapshot carries no rate for this model.

    A singleton — identity comparison works (``is``). It is never coerced
    to 0.0: :func:`price_model_usage` routes its tokens into
    :attr:`CostBreakdown.unknown_tokens` so coverage stays auditable
    instead of silently inflating the "priced" figure.
    """

    _instance: Optional["UnknownPrice"] = None

    def __new__(cls) -> "UnknownPrice":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UnknownPrice"

    def __bool__(self) -> bool:
        return False


@dataclass(frozen=True)
class BucketPrices:
    """Per-1M-token unit prices for one model, all in the snapshot currency.

    All values are ``Decimal``. ``reasoning`` defaults to 0 (DATA_CONTRACT
    §3.3: the default never bills reasoning separately); set a non-zero
    rate only for providers documented to bill it as its own line.
    """

    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal = Decimal("0")
    reasoning: Decimal = Decimal("0")

    def as_dict(self) -> dict[str, Decimal]:
        return {
            "input": self.input,
            "output": self.output,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "reasoning": self.reasoning,
        }


@dataclass(frozen=True)
class PriceSnapshot:
    """A point-in-time, per-model rate card in one currency.

    ``currency`` is an ISO-4217 code (e.g. ``"USD"``); ``as_of`` is the
    snapshot date (prices change, so a cost figure is only meaningful next
    to its snapshot date). ``prices`` maps exact ``model_id`` strings to
    :class:`BucketPrices`. FX is intentionally OUT of scope here: a snapshot
    is single-currency; conversion is an owner policy decision (see the
    ticket's open questions), not this layer's job.
    """

    currency: str
    as_of: date
    prices: Mapping[str, BucketPrices] = field(default_factory=dict)

    def price_for(self, model_id: str) -> BucketPrices | UnknownPrice:
        """Rate card for *model_id*, or the :class:`UnknownPrice` marker.

        Never returns 0.0 for a missing model — absence must be visible in
        coverage accounting, not buried as a free model.
        """
        p = self.prices.get(model_id)
        if p is None:
            return UnknownPrice()
        return p

    @property
    def is_empty(self) -> bool:
        return not self.prices


def _validate_bucket_counts(bucket_tokens: Mapping[str, int]) -> dict[str, int]:
    """Return a full 5-bucket int mapping; raise on unknown/negative keys.

    Missing keys default to 0 (a row may omit buckets it did not use).
    Unknown keys raise :class:`PricingError` — a typo'd bucket would
    otherwise silently drop tokens out of the priced total.
    """
    out: dict[str, int] = {}
    for b in BUCKETS:
        v = bucket_tokens.get(b, 0)
        if not isinstance(v, int) or isinstance(v, bool):
            raise PricingError(f"bucket {b!r} must be an int, got {v!r}")
        if v < 0:
            raise PricingError(f"bucket {b!r} is negative: {v}")
        out[b] = v
    extra = set(bucket_tokens) - set(BUCKETS)
    if extra:
        raise PricingError(f"unknown bucket(s): {sorted(extra)}")
    return out


def compute_cost(bucket_tokens: Mapping[str, int], price: BucketPrices) -> Decimal:
    """Cost of one model's token counts under *price* (snapshot currency).

    Formula::

        cost = sum_b( tokens[b] * unit_price_per_1M[b] ) / 1_000_000

    Decimal arithmetic end-to-end: each product is exact (int × Decimal),
    the sum is exact, and the single per-million division happens once at
    the end, quantized to 6 decimal places (micro currency units) with
    ``ROUND_HALF_UP``. No float ever touches this path. The five buckets
    are disjoint (module docstring), so the sum cannot double-count.
    """
    counts = _validate_bucket_counts(bucket_tokens)
    rates = price.as_dict()
    for b in BUCKETS:
        if not isinstance(rates[b], Decimal):
            raise PricingError(
                f"bucket {b!r} price must be Decimal, got "
                f"{type(rates[b]).__name__} (floats are forbidden in the money path)"
            )
    total_micro = Decimal(0)
    for b in BUCKETS:
        total_micro += Decimal(counts[b]) * rates[b]
    cost = total_micro / _PER_MILLION
    return cost.quantize(_COST_EXP, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CostBreakdown:
    """Result of pricing a list of per-model rows against one snapshot.

    ``priced`` is the exact Decimal sum of per-model costs for models the
    snapshot knows. Unknown models contribute NOTHING to ``priced`` —
    their tokens are carried in ``unknown_tokens`` (per-bucket) and their
    ids in ``unknown_models`` so a reviewer can see the gap (coverage)
    instead of finding a silent 0.0 hiding in the total.
    """

    currency: str
    as_of: date
    priced: Decimal
    per_model: Mapping[str, Decimal]
    unknown_models: tuple[str, ...]
    unknown_tokens: Mapping[str, int]
    total_tokens: int = 0

    @property
    def priced_tokens(self) -> int:
        """Total tokens that were actually priced (all buckets)."""
        return self.total_tokens - sum(self.unknown_tokens.values())

    @property
    def coverage(self) -> Optional[Decimal]:
        """priced_tokens / total_tokens as a Decimal, or None if no tokens.

        ``coverage == 1`` means the snapshot explains the whole usage;
        anything less is a data-coverage gap the UI must surface, never
        assume away.
        """
        if self.total_tokens == 0:
            return None
        return Decimal(self.priced_tokens) / Decimal(self.total_tokens)


def price_model_usage(
    rows: Sequence[tuple[str, Mapping[str, int]]],
    snapshot: PriceSnapshot,
) -> CostBreakdown:
    """Price per-model token rows against a snapshot.

    ``rows`` is a list of ``(model_id, {bucket: tokens})`` — the shape the
    DB/UI wiring layer produces from ``session_model_usage`` (per-model
    rows, not per-session: DATA_CONTRACT §7, mixed-route sessions). Each
    row is priced with its own model's rate card; a model absent from the
    snapshot becomes an :class:`UnknownPrice` contribution (see
    :class:`CostBreakdown`), never a silent 0.0.
    """
    per_model: dict[str, Decimal] = {}
    unknown: set[str] = set()
    unknown_tokens: dict[str, int] = {b: 0 for b in BUCKETS}
    total_tokens = 0
    for model_id, bucket_tokens in rows:
        counts = _validate_bucket_counts(bucket_tokens)
        total_tokens += sum(counts.values())
        price = snapshot.price_for(model_id)
        if isinstance(price, UnknownPrice):
            unknown.add(model_id)
            for b in BUCKETS:
                unknown_tokens[b] += counts[b]
            continue
        per_model[model_id] = per_model.get(model_id, Decimal(0)) + compute_cost(
            counts, price
        )
    priced = sum(per_model.values(), Decimal(0))
    return CostBreakdown(
        currency=snapshot.currency,
        as_of=snapshot.as_of,
        priced=priced,
        per_model=per_model,
        unknown_models=tuple(sorted(unknown)),
        unknown_tokens=unknown_tokens,
        total_tokens=total_tokens,
    )


# ---------------------------------------------------------------------------
# Self-test (smoke, no pytest dependency) — mirrors tests/test_pricing.py
# ---------------------------------------------------------------------------

def _selftest() -> int:
    import json

    failures: list[str] = []
    D = Decimal
    snap = PriceSnapshot(
        currency="USD", as_of=date(2026, 11, 2),
        prices={
            "m1": BucketPrices(input=D("3.00"), output=D("15.00"),
                               cache_read=D("0.30"), cache_write=D("3.75")),
        },
    )

    # exact cost: (1M×3 + 1M×15 + 1M×0.30)/1e6 = 18.30
    cost = compute_cost({"input": 1_000_000, "output": 1_000_000,
                         "cache_read": 1_000_000}, snap.prices["m1"])
    if cost != D("18.300000"):
        failures.append(f"cost mismatch: {cost}")

    # unknown model: priced excludes it, coverage accounts for it
    bd = price_model_usage([("m1", {"input": 1_000_000}),
                            ("ghost", {"input": 3_000_000})], snap)
    if bd.priced != D("3.000000") or bd.unknown_models != ("ghost",) \
            or bd.coverage != D(1) / D(4):
        failures.append(f"unknown-model coverage: {bd}")

    # floats must be refused in the money path
    try:
        compute_cost({"input": 1}, BucketPrices(input=0.5, output=D("0"),  # type: ignore[arg-type]
                                                cache_read=D("0"), cache_write=D("0")))
        failures.append("float price accepted")
    except PricingError:
        pass

    out = {"failures": failures, "ok": not failures}
    print(json.dumps(out, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    import sys

    sys.exit(_selftest())
