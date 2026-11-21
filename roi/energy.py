"""ROI P1/T04b-data — optional energy/operating cost (D-020).

Owner decision: an optional setting; support entering electricity price
× energy usage (电费 × 用电量). Shape::

    energy_cost = unit_price_per_kwh * kwh          (exact Decimal)
    net         = gross if energy unset, else gross - energy_cost

An empty energy setting means net == gross, labeled "gross, energy not
modeled". The module is currency-agnostic: both inputs are plain Decimal
values in whatever currency the caller uses (usually USD, after the fx
module). Net MAY be negative (energy > gross) — an honest result the
verdict layer treats as no-positive-pace, not an error.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

#: Cost-precision exponent (one micro currency unit), as in pricing.py.
_EXP = Decimal("0.000001")


class EnergyError(ValueError):
    """Bad energy input (float, negative, non-decimal string, ...)."""


def _as_decimal(value, name: str) -> Decimal:
    if isinstance(value, bool):
        raise EnergyError(f"{name}: bool is not a Decimal")
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, int):
        d = Decimal(value)
    elif isinstance(value, str):
        try:
            d = Decimal(value)
        except InvalidOperation as e:
            raise EnergyError(f"{name}: not a decimal string: {value!r}") from e
    else:
        raise EnergyError(
            f"{name}: must be Decimal/int/str, got {type(value).__name__} "
            "(floats are forbidden in the money path)")
    if not d.is_finite():
        raise EnergyError(f"{name}: not finite")
    if d < 0:
        raise EnergyError(f"{name}: must be >= 0, got {d}")
    return d


def energy_cost(unit_price_per_kwh, kwh) -> Decimal:
    """Electricity unit price × usage, quantized to 6dp ROUND_HALF_UP."""
    price = _as_decimal(unit_price_per_kwh, "unit_price_per_kwh")
    usage = _as_decimal(kwh, "kwh")
    return (price * usage).quantize(_EXP, rounding=ROUND_HALF_UP)


def net_savings(gross, energy=None) -> Decimal:
    """gross − energy; ``energy is None`` means "not modeled" -> gross.

    The result may be negative; that is a legitimate input to the verdict
    layer (no positive trajectory), not an exception.
    """
    g = _as_decimal(gross, "gross")
    if energy is None:
        return g.quantize(_EXP, rounding=ROUND_HALF_UP)
    e = _as_decimal(energy, "energy_cost")
    return (g - e).quantize(_EXP, rounding=ROUND_HALF_UP)
