"""ROI P1/T04b-data — currency conversion to USD (D-019).

Owner decision: Xe.com data, target USD. v1 ships a committed
Xe-sourced mid-market snapshot (as-of dated) plus manual rate entry; a
live Xe API fetch is a later opt-in (user key, no default network calls
— privacy-first). The money path is Decimal-only; floats are refused.

Direction convention: a rate is stored as ``1 base = rate quote``
(e.g. 1 USD = 6.64910834 CNY). Converting a quote-currency amount to
USD therefore DIVIDES by the rate (100 CNY -> 100 / 6.64910834 USD).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Mapping, Optional

DEFAULT_FX_PATH = Path(__file__).resolve().parent / "price_cards" / "fx-xe.json"

#: Cost-precision exponent (one micro currency unit), as in pricing.py.
_EXP = Decimal("0.000001")


class FxError(ValueError):
    """Bad FX input (unknown currency, wrong base, float amount, ...).
    A missing rate must be visible, never assumed 1:1."""


@dataclass(frozen=True)
class FxRate:
    """1 *base* unit = *rate* *quote* units, as of *as_of*, from *source*."""

    base: str
    quote: str
    rate: Decimal
    as_of: date
    source: str


def _as_decimal(value, name: str) -> Decimal:
    if isinstance(value, bool):
        raise FxError(f"{name}: bool is not a Decimal")
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, str):
        try:
            d = Decimal(value)
        except InvalidOperation as e:
            raise FxError(f"{name}: not a decimal string: {value!r}") from e
    else:
        raise FxError(
            f"{name}: must be Decimal/int/str, got {type(value).__name__} "
            "(floats are forbidden in the money path)")
    if not d.is_finite():
        raise FxError(f"{name}: not finite")
    return d


def load_fx_table(path: Optional[Path] = None) -> dict[str, FxRate]:
    """Load the committed snapshot -> {quote_ccy: FxRate(base='USD', ...)}."""
    p = Path(path) if path is not None else DEFAULT_FX_PATH
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise FxError(f"fx snapshot not found: {p}") from e
    except json.JSONDecodeError as e:
        raise FxError(f"fx snapshot is not valid JSON ({p}): {e}") from e
    base = str(raw.get("base", "USD")).strip().upper()
    try:
        as_of = date.fromisoformat(raw["as_of"])
    except (KeyError, TypeError, ValueError) as e:
        raise FxError(f"fx snapshot: 'as_of' must be ISO YYYY-MM-DD, got {raw.get('as_of')!r}") from e
    source = str(raw.get("source", ""))
    rates = raw.get("rates")
    if not isinstance(rates, dict) or not rates:
        raise FxError("fx snapshot: 'rates' must be a non-empty object")
    out: dict[str, FxRate] = {}
    for ccy, r in rates.items():
        rate = _as_decimal(r, f"rate[{ccy}]")
        if rate <= 0:
            raise FxError(f"fx snapshot: rate[{ccy}] must be > 0")
        out[str(ccy).strip().upper()] = FxRate(
            base=base, quote=str(ccy).strip().upper(), rate=rate,
            as_of=as_of, source=source)
    return out


def to_usd(amount, ccy: str, table: Mapping[str, FxRate]) -> Decimal:
    """Convert a *ccy* amount to USD using *table*.

    USD passes through (quantized to 6dp). Unknown currency raises
    FxError — a missing rate must be visible, never assumed 1:1.
    """
    amt = _as_decimal(amount, "amount")
    if amt < 0:
        raise FxError(f"amount must be >= 0, got {amt}")
    ccy = str(ccy).strip().upper()
    if ccy == "USD":
        return amt.quantize(_EXP, rounding=ROUND_HALF_UP)
    rate = table.get(ccy)
    if rate is None:
        raise FxError(
            f"no FX rate for {ccy!r} (add it to the snapshot or enter a "
            "manual rate)")
    if rate.base != "USD":
        raise FxError(f"rate for {ccy!r} has base {rate.base!r}, expected 'USD'")
    return (amt / rate.rate).quantize(_EXP, rounding=ROUND_HALF_UP)
