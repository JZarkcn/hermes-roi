"""ROI P1/T04b-data — provider price-card snapshot loading (D-018/D-022).

Reads a committed provider rate-card JSON into ``pricing.PriceSnapshot``
objects. The card is a SNAPSHOT: source URL + as-of date are part of the
data, and refresh is a manual, user-triggered action (privacy-first: no
silent runtime network calls). All rates are exact decimal STRINGS in the
JSON — anything else is refused at load time, matching the money-path
rule.

v1 rate basis (D-018/D-022, owner-approved): ``"peak"`` — conservative
for the avoided-cost claim. Off-peak rates stay in the JSON for the P2
time-aware (per-timestamp) rates.

DeepSeek bucket mapping (D-018): the official card prices input
separately as cache-miss / cache-hit; that maps onto the collector's
disjoint buckets (DATA_CONTRACT §3) as::

    input       <- cache-miss input price   (uncached input)
    cache_read  <- cache-hit  input price
    output      <- output price
    cache_write <- 0  (no cache-write line in the card)
    reasoning   <- 0  (no separate line; thinking is billed inside output
                      — the D-021 rough-estimate path)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from roi import pricing as P

#: The committed default card (D-018: standard benchmark = DeepSeek).
DEFAULT_CARD_PATH = Path(__file__).resolve().parent / "price_cards" / "deepseek.json"

#: Rate bases selectable from a card.
BASIS = ("peak", "off_peak")


class CardError(ValueError):
    """Malformed price-card snapshot. A card that fails to load must never
    price anything."""


@dataclass(frozen=True)
class Card:
    """A loaded rate card: one PriceSnapshot for the chosen basis plus the
    raw JSON (off-peak rates, model versions, source) for audit and for
    the P2 time-aware rates."""

    snapshot: P.PriceSnapshot
    default_model: str
    source: str
    basis: str
    raw: dict


def _decimal(value, what: str) -> Decimal:
    """Exact non-negative finite Decimal from a JSON string."""
    if isinstance(value, bool):
        raise CardError(f"{what}: bool is not a decimal string")
    if not isinstance(value, str):
        raise CardError(
            f"{what}: must be a decimal string, got {type(value).__name__}")
    try:
        d = Decimal(value)
    except InvalidOperation as e:
        raise CardError(f"{what}: not a decimal: {value!r}") from e
    if not d.is_finite() or d < 0:
        raise CardError(f"{what}: must be finite and >= 0: {value!r}")
    return d


def load_card(path: Optional[Path] = None, basis: str = "peak") -> Card:
    """Load a rate-card JSON into a Card for *basis* ('peak'/'off_peak').

    The returned PriceSnapshot carries ONE rate per model/bucket (the
    chosen basis); the raw JSON keeps both. Raises CardError on any
    malformation — an unparseable card fails loudly, never prices
    silently.
    """
    if basis not in BASIS:
        raise CardError(f"basis must be one of {BASIS}, got {basis!r}")
    p = Path(path) if path is not None else DEFAULT_CARD_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise CardError(f"price card not found: {p}") from e
    except json.JSONDecodeError as e:
        raise CardError(f"price card is not valid JSON ({p}): {e}") from e

    currency = raw.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        raise CardError("price card: missing/empty 'currency'")
    try:
        as_of = date.fromisoformat(raw["as_of"])
    except (KeyError, TypeError, ValueError) as e:
        raise CardError(f"price card: 'as_of' must be ISO YYYY-MM-DD, got {raw.get('as_of')!r}") from e
    source = raw.get("source")
    if not isinstance(source, str) or not source.strip():
        raise CardError("price card: missing/empty 'source'")
    models = raw.get("models")
    if not isinstance(models, dict) or not models:
        raise CardError("price card: 'models' must be a non-empty object")

    prices = {}
    for model_id, entry in models.items():
        if not isinstance(entry, dict):
            raise CardError(f"price card: model {model_id!r} entry must be an object")
        buckets = {}
        for b in P.BUCKETS:
            cell = entry.get(b)
            if not isinstance(cell, dict):
                raise CardError(
                    f"price card: model {model_id!r} bucket {b!r} must be a "
                    "{'peak': str, 'off_peak': str} object")
            buckets[b] = _decimal(cell.get(basis), f"{model_id}.{b}[{basis}]")
        prices[model_id] = P.BucketPrices(**buckets)

    default_model = raw.get("default_benchmark_model")
    if default_model not in prices:
        raise CardError(
            f"price card: default_benchmark_model {default_model!r} not in "
            f"models {sorted(prices)}")

    snapshot = P.PriceSnapshot(currency=currency.strip().upper(), as_of=as_of, prices=prices)
    return Card(snapshot=snapshot, default_model=default_model, source=source,
                basis=basis, raw=raw)
