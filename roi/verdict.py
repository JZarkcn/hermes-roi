"""ROI P1/T04 — pure verdict layer: recovery %, break-even, four-tier verdict.

Scope (pure layer only): given the effective hardware start date, a forecast
anchor ``as_of``, a list of net-savings events ``(tz-aware timestamp,
Decimal net)`` and the configured hardware cost, compute the hero recovery
percent, the secondary net-ROI percent, the break-even projection and the
four-tier verdict. No I/O, no DB, no config reads, no floats in the money
path (event amounts must be ``Decimal``/int/str; ``float`` is rejected).

Fixed product rules (T04 — no alternatives are implemented here):

* **Hero recovery** ``= 100 × estimated_net_savings / configured_hardware_cost``
  (AGENTS.md "Key math"), quantized to EXACTLY 3 decimal places,
  ``ROUND_HALF_UP`` (documented).
* **Secondary net-ROI** ``= 100 × (net_savings − hardware_cost) /
  hardware_cost``, same formatting.
* **Break-even basis** (AGENTS.md): pace = net savings over the TRAILING
  30 CALENDAR days ending at ``as_of``'s calendar day (zero-usage days
  count in the denominator — inactive days slow the pace on purpose),
  projected from the explicit effective start date: cumulative net is
  summed from ``start_at`` to ``as_of``; remaining = hardware − net.
  No finite date when pace ≤ 0. Before 30 calendar days have elapsed, a
  PROVISIONAL pace uses ALL available days instead (Option B, owner
  2026-11-06): pace = cumulative net / (elapsed+1 calendar days), flagged
  ``provisional``; it switches to the standard trailing-30-day window on
  day 30 (a one-time number shift, disclosed in the UI badge).
* **Exactly four tiers**
  - ``LV1`` already paid off: net ≥ hardware (inclusive).
  - ``LV2`` break-even within 180 days (inclusive: day 180 → LV2).
  - ``LV3`` within 5 years = 1825 days (inclusive: day 1825 → LV3).
  - ``LV4`` farther than 1825 days, OR no positive pace (zero/negative).
  No recorded usage at all is the ``"unknown"`` onboarding state — NOT a
  tier. (With usage but <30 days elapsed, a provisional pace/tier is shown
  instead of unknown — see the break-even basis above.)
* **Timezone**: all timestamps must be tz-aware. Day buckets are calendar
  days in the given display ``tz`` (default ``timezone.utc``); the UI must
  state the display rule (DATA_CONTRACT §8). The forecast anchor ``as_of``
  is the single absolute timestamp the countdown and the date derive from
  (DATA_CONTRACT §8).

Net-savings semantics (DATA_CONTRACT §10): an event's ``net`` is
``cloud_equivalent_value − modeled_operating_costs`` for that usage —
computed upstream from the pricing layer minus the user's energy/operating
model. Stored ``estimated_cost_usd``/``actual_cost_usd`` are never an input
here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Optional, Sequence, Tuple

#: Break-even pace window: trailing 30 calendar days (zero-usage days
#: included in the denominator). AGENTS.md "Key math".
PACE_WINDOW_DAYS = 30

#: Tier horizons in whole days (boundary-inclusive).
LV2_HORIZON_DAYS = 180  # half a year per owner ruling 2026-11-22 ("线太小了，改成小于 180 天")
LV3_HORIZON_DAYS = 1825  # 5 years per the fixed product rule

#: 3-decimal display exponent for the percents.
_PCT_EXP = Decimal("0.001")

#: Tier / status constants (``"unknown"`` is an onboarding state, not a tier).
TIER_PAID_OFF = "LV1"
TIER_SOON = "LV2"
TIER_MODERATE = "LV3"
TIER_FAR = "LV4"
TIER_UNKNOWN = "unknown"

STATUS_OK = "ok"
STATUS_PAID_OFF = "already_paid_off"
STATUS_NO_PACE = "no_positive_pace"
STATUS_UNKNOWN = "unknown"

#: One net-savings event: (tz-aware timestamp, net savings Decimal).
Event = Tuple[datetime, Decimal]


def _as_decimal(value, name: str) -> Decimal:
    """Coerce to Decimal for the money path. ``float`` is REFUSED — floats
    must never touch a money value (T04 constraint)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception as e:
            raise ValueError(f"{name}: not a Decimal string: {value!r}") from e
    raise ValueError(
        f"{name}: must be Decimal/int/str, got {type(value).__name__} "
        "(floats are forbidden in the money path)"
    )


def _require_aware(dt: datetime, name: str) -> None:
    if not isinstance(dt, datetime):
        raise ValueError(f"{name}: must be a datetime, got {type(dt).__name__}")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"{name}: must be tz-aware (explicit timezone required)")


def recovery_pct(estimated_net_savings, hardware_cost) -> Decimal:
    """Hero recovery: ``100 × net_savings / hardware_cost``, 3 decimals.

    Quantized to 0.001 with ``ROUND_HALF_UP`` (documented). ``hardware_cost``
    must be > 0. The result is the ``Decimal``; use :func:`format_percent`
    for the exact 3-decimal string.
    """
    net = _as_decimal(estimated_net_savings, "estimated_net_savings")
    hw = _as_decimal(hardware_cost, "hardware_cost")
    if hw <= 0:
        raise ValueError("hardware_cost must be > 0")
    return (Decimal(100) * net / hw).quantize(_PCT_EXP, rounding=ROUND_HALF_UP)


def net_roi_pct(net_savings, hardware_cost) -> Decimal:
    """Secondary net-ROI: ``100 × (net_savings − hardware_cost) /
    hardware_cost``, 3 decimals, same rounding as :func:`recovery_pct`."""
    net = _as_decimal(net_savings, "net_savings")
    hw = _as_decimal(hardware_cost, "hardware_cost")
    if hw <= 0:
        raise ValueError("hardware_cost must be > 0")
    return (Decimal(100) * (net - hw) / hw).quantize(_PCT_EXP, rounding=ROUND_HALF_UP)


def format_percent(value) -> str:
    """Exactly 3 decimal places: ``"0.000"``, ``"12.346"``, ``"-5.000"``.

    Re-quantizes with ``ROUND_HALF_UP`` so a non-3dp input is still pinned;
    a negative zero normalizes to ``"0.000"`` (never ``"-0.000"``).
    """
    v = _as_decimal(value, "value").quantize(_PCT_EXP, rounding=ROUND_HALF_UP)
    if v == 0:
        v = abs(v)
    return format(v, "f")


@dataclass(frozen=True)
class BreakEvenProjection:
    """Break-even math with its documented basis, for one forecast anchor.

    ``status`` is one of ``ok`` / ``already_paid_off`` / ``no_positive_pace``
    / ``unknown``. In the ``unknown`` (onboarding) state the pace/window
    fields are zeroed and ``break_even_date``/``days_remaining`` are None —
    an unknown history must not produce a fake date. ``total_net`` is the
    real cumulative net since ``start_at`` in every state (used to display
    the hero recovery).
    """

    as_of: datetime
    start_at: datetime
    tz: tzinfo
    status: str
    window_net: Decimal
    pace_per_day: Decimal
    total_net: Decimal
    remaining: Decimal
    days_remaining: Optional[int]
    break_even_date: Optional[date]
    note: str
    #: True when the pace is a provisional estimate built from fewer than 30
    #: calendar days of history (Option B, owner 2026-11-06, superseding the
    #: D-022a strict-unknown rule). The standard trailing-30-day window only
    #: exists once 30+ days have elapsed; before that the whole available
    #: history is the window and the pace is flagged provisional.
    provisional: bool = False
    #: Calendar days used as the pace denominator: 30 for the standard
    #: window, or the elapsed+1 available days for a provisional estimate.
    pace_days: int = 0

    @property
    def is_unknown(self) -> bool:
        return self.status == STATUS_UNKNOWN


def _bucket_events(
    events: Sequence[Event],
    start_date: date,
    as_of_date: date,
    as_of: datetime,
    tz: tzinfo,
) -> Tuple[dict[date, Decimal], Decimal, int]:
    """Bucket events into calendar days of *tz* and sum in-range net.

    Returns (daily_net, total_net, dropped). Rules (documented):
    * timestamps must be tz-aware; amounts Decimal/int/str (no float);
    * events at/after ``as_of`` are dropped (future of the forecast anchor);
    * events before the effective start date are dropped (pre-hardware);
    * ``daily_net`` maps calendar day (in *tz*) → that day's net sum;
    * ``total_net`` = sum over ``start_date ≤ day ≤ as_of_date``.
    """
    daily: dict[date, Decimal] = {}
    total = Decimal(0)
    dropped = 0
    for ts, amount in events:
        _require_aware(ts, "event timestamp")
        amt = _as_decimal(amount, "event amount")
        if ts >= as_of:
            dropped += 1
            continue
        d = ts.astimezone(tz).date()
        if d < start_date or d > as_of_date:
            dropped += 1
            continue
        daily[d] = daily.get(d, Decimal(0)) + amt
        total += amt
    return daily, total, dropped


def project_break_even(
    *,
    as_of: datetime,
    start_at: datetime,
    events: Sequence[Event],
    hardware_cost,
    tz: Optional[tzinfo] = None,
    recurring_cost_per_day: Decimal = Decimal(0),
) -> BreakEvenProjection:
    """Project break-even from an explicit effective start date.

    Basis (see module docstring): trailing 30 calendar days (in *tz*)
    ending at ``as_of``'s day give the pace; cumulative net is summed from
    ``start_at``; ``remaining = hardware − net``. The first whole day D with
    ``pace × D ≥ remaining`` is the break-even, reported as the calendar
    day ``as_of_day + D`` in *tz*. Day math uses exact Decimal ``divmod``
    (no context-precision drift at integer boundaries).

    ``recurring_cost_per_day`` is a continuing cost (e.g. ongoing
    electricity) deducted from the pace so the projection keeps paying for
    it: ``pace = window_net / 30 − recurring_cost_per_day``. The cumulative
    net (``total_net``) already carries the elapsed portion of that cost via
    the event stream, so the break-even is net-of-recurring end to end.
    ``recurring_cost_per_day = 0`` (default) → ``pace`` is the raw gross
    window pace (legacy behaviour, byte-identical to before this param).

    The ``provisional`` flag is True when the pace is a provisional
    estimate from fewer than 30 calendar days of history (Option B, owner
    2026-11-06): ``pace_days = elapsed + 1``, ``window_net = total_net``
    (the whole available history is the window). From day 30 the standard
    trailing-30-day window applies and ``provisional`` is False.

    States: ``unknown`` (no recorded usage, or start at/after the anchor),
    ``already_paid_off`` (remaining ≤ 0), ``no_positive_pace`` (pace ≤ 0,
    remaining > 0), ``ok``. ``unknown`` is the only onboarding state —
    with any usage present a provisional (short-history) or standard pace
    is always produced, never a fake "insufficient history" wall.
    """
    _require_aware(as_of, "as_of")
    _require_aware(start_at, "start_at")
    hw = _as_decimal(hardware_cost, "hardware_cost")
    if hw <= 0:
        raise ValueError("hardware_cost must be > 0")
    display_tz = tz or timezone.utc
    as_of_date = as_of.astimezone(display_tz).date()
    start_date = start_at.astimezone(display_tz).date()
    daily, total_net, dropped = _bucket_events(events, start_date, as_of_date, as_of, display_tz)

    def _unknown(note: str) -> BreakEvenProjection:
        return BreakEvenProjection(
            as_of=as_of, start_at=start_at, tz=display_tz, status=STATUS_UNKNOWN,
            window_net=Decimal(0), pace_per_day=Decimal(0), total_net=total_net,
            remaining=hw - total_net, days_remaining=None, break_even_date=None,
            note=note,
        )

    if start_date > as_of_date:
        return _unknown("effective start date is at/after the forecast anchor")
    if not events:
        return _unknown("no usage recorded since the effective start (onboarding)")
    elapsed = (as_of_date - start_date).days
    if elapsed < PACE_WINDOW_DAYS:
        # Option B (owner 2026-11-06, superseding D-022a): give a PROVISIONAL
        # estimate from ALL available calendar days before a full 30-day window
        # exists. pace = cumulative net over [start_date..as_of_date] /
        # (elapsed+1 calendar days, zero-usage days included — the same
        # calendar-day convention as the standard window). Flagged provisional;
        # day 30+ switches to the standard trailing-30-day window, which can
        # shift the number — that one-time jump is expected and disclosed.
        pace_days = elapsed + 1
        window_net = total_net  # the whole available history IS the window
        gross_pace = window_net / Decimal(pace_days)
        provisional = True
    else:
        window = {as_of_date - timedelta(days=k) for k in range(PACE_WINDOW_DAYS)}
        window_net = sum((daily.get(d, Decimal(0)) for d in window), Decimal(0))
        gross_pace = window_net / Decimal(PACE_WINDOW_DAYS)
        pace_days = PACE_WINDOW_DAYS
        provisional = False

    # Net pace: gross token-savings pace minus any recurring cost
    # (ongoing electricity) so the projection keeps paying for it.
    # recurring=0 → net == gross (legacy behaviour).
    pace = gross_pace - recurring_cost_per_day
    remaining = hw - total_net
    note_suffix = f"; {dropped} event(s) dropped (out of range/future)" if dropped else ""
    net_note = (
        f"; net pace = {gross_pace} gross − {recurring_cost_per_day} recurring"
        if recurring_cost_per_day
        else ""
    )
    prov = (f"PROVISIONAL (based on {pace_days} day(s), < {PACE_WINDOW_DAYS}-day window): "
            if provisional else "")
    win_desc = (f"the {pace_days} available day(s)" if provisional
                else f"the trailing {PACE_WINDOW_DAYS} calendar days")

    if remaining <= 0:
        return BreakEvenProjection(
            as_of=as_of, start_at=start_at, tz=display_tz, status=STATUS_PAID_OFF,
            window_net=window_net, pace_per_day=pace, total_net=total_net,
            remaining=remaining, days_remaining=0, break_even_date=None,
            note=f"{prov}net {total_net} ≥ hardware {hw}: already paid off{note_suffix}",
            provisional=provisional, pace_days=pace_days,
        )
    if pace <= 0:
        return BreakEvenProjection(
            as_of=as_of, start_at=start_at, tz=display_tz, status=STATUS_NO_PACE,
            window_net=window_net, pace_per_day=pace, total_net=total_net,
            remaining=remaining, days_remaining=None, break_even_date=None,
            note=(
                f"{prov}pace {pace}/day over {win_desc} ≤ 0: "
                f"no positive trajectory, no finite date{net_note}"
                f"{note_suffix}"
            ),
            provisional=provisional, pace_days=pace_days,
        )
    # Exact integer days: divmod is exact for Decimal (quotient truncated,
    # remainder exact) — immune to 28-digit context drift at boundaries.
    q, r = divmod(remaining, pace)
    days = int(q) + (1 if r > 0 else 0)
    break_even = as_of_date + timedelta(days=days)
    return BreakEvenProjection(
        as_of=as_of, start_at=start_at, tz=display_tz, status=STATUS_OK,
        window_net=window_net, pace_per_day=pace, total_net=total_net,
        remaining=remaining, days_remaining=days, break_even_date=break_even,
        note=(
            f"{prov}pace {pace}/day × {days} day(s) covers remaining {remaining} "
            f"(window net {window_net} over {win_desc}){net_note}{note_suffix}"
        ),
        provisional=provisional, pace_days=pace_days,
    )


@dataclass(frozen=True)
class Verdict:
    """The four-tier verdict plus the formatted hero/secondary percents.

    ``tier`` is ``"LV1"``–``"LV4"`` or ``"unknown"`` (onboarding, not a
    tier). ``recovery_text``/``net_roi_text`` are the exact 3-decimal
    strings for display; ``break_even_date`` is None unless a finite
    projection exists.
    """

    tier: str
    label: str
    reason: str
    recovery_pct: Decimal
    net_roi_pct: Decimal
    recovery_text: str
    net_roi_text: str
    break_even_date: Optional[date]
    pace_per_day: Optional[Decimal]
    label_zh: str = ""
    roast: str = ""
    #: Mirrors BreakEvenProjection.provisional — True when this verdict rests
    #: on a provisional pace from <30 days of history (Option B, 2026-11-06).
    provisional: bool = False


_TIER_META = {
    TIER_PAID_OFF: "PAID OFF. ABSOLUTE LEGEND.",
    TIER_SOON: "ALMOST THERE.",
    TIER_MODERATE: "STILL A LONG WAY. KEEP GRINDING.",
    TIER_FAR: "PAYBACK IS A DISTANT DREAM.",
    TIER_UNKNOWN: "ONBOARDING — NOT ENOUGH HISTORY TO JUDGE.",
}

# Bilingual verdict copy from the original design mockup (owner, 2026-11-05).
# English-first per the catalog rule (maintainer review, 2026-11-22): the EN
# _TIER_META line is the headline everywhere; the Chinese line is a secondary
# subtitle. The roast is the "// ..." line under the banner — sarcasm lives
# here, never in the math.
_TIER_META_ZH = {
    TIER_PAID_OFF: "回本了·太强了！",
    TIER_SOON: "马上回本！",
    TIER_MODERATE: "还差得远·再接再厉！",
    TIER_FAR: "回本遥遥无期！",
    TIER_UNKNOWN: "数据不足·暂不评价",
}

_TIER_ROASTS = {
    TIER_PAID_OFF: "// At this rate, the receipt is old news — the hardware funds its successor.",
    TIER_SOON: "// At this rate, payback lands before the warranty paperwork dries.",
    TIER_MODERATE: "// At this rate, patience is the only asset still appreciating.",
    TIER_FAR: "// At this rate, your next GPU will retire first.",
    TIER_UNKNOWN: "// At this rate, there is no rate yet. Feed it tokens.",
}


def make_verdict(
    *,
    as_of: datetime,
    start_at: datetime,
    events: Sequence[Event],
    hardware_cost,
    tz: Optional[tzinfo] = None,
    recurring_cost_per_day: Decimal = Decimal(0),
) -> Verdict:
    """Full verdict: hero + secondary percents, projection, four-tier tier.

    Tier assignment (fixed rules, see module docstring): unknown history →
    ``"unknown"``; remaining ≤ 0 → LV1; days ≤ 180 → LV2; days ≤ 1825 → LV3;
    days > 1825 or pace ≤ 0 → LV4.

    ``recurring_cost_per_day`` is forwarded to :func:`project_break_even`
    so the break-even (and therefore the tier) is net of any continuing
    cost such as ongoing electricity.
    """
    proj = project_break_even(
        as_of=as_of, start_at=start_at, events=events,
        hardware_cost=hardware_cost, tz=tz,
        recurring_cost_per_day=recurring_cost_per_day,
    )
    recovery = recovery_pct(proj.total_net, hardware_cost)
    net_roi = net_roi_pct(proj.total_net, hardware_cost)
    recovery_text = format_percent(recovery)
    net_roi_text = format_percent(net_roi)

    if proj.status == STATUS_UNKNOWN:
        return Verdict(
            tier=TIER_UNKNOWN, label=_TIER_META[TIER_UNKNOWN],
            reason=f"unknown: {proj.note}", break_even_date=None,
            pace_per_day=None,
            recovery_pct=recovery, net_roi_pct=net_roi,
            recovery_text=recovery_text, net_roi_text=net_roi_text,
            label_zh=_TIER_META_ZH[TIER_UNKNOWN], roast=_TIER_ROASTS[TIER_UNKNOWN],
            provisional=False,
        )
    if proj.status == STATUS_PAID_OFF:
        return Verdict(
            tier=TIER_PAID_OFF, label=_TIER_META[TIER_PAID_OFF],
            reason=f"LV1: {proj.note}", break_even_date=None,
            pace_per_day=proj.pace_per_day,
            recovery_pct=recovery, net_roi_pct=net_roi,
            recovery_text=recovery_text, net_roi_text=net_roi_text,
            label_zh=_TIER_META_ZH[TIER_PAID_OFF], roast=_TIER_ROASTS[TIER_PAID_OFF],
            provisional=proj.provisional,
        )
    if proj.status == STATUS_NO_PACE:
        return Verdict(
            tier=TIER_FAR, label=_TIER_META[TIER_FAR],
            reason=f"LV4: {proj.note}", break_even_date=None,
            pace_per_day=proj.pace_per_day,
            recovery_pct=recovery, net_roi_pct=net_roi,
            recovery_text=recovery_text, net_roi_text=net_roi_text,
            label_zh=_TIER_META_ZH[TIER_FAR], roast=_TIER_ROASTS[TIER_FAR],
            provisional=proj.provisional,
        )
    days = proj.days_remaining
    if days is None:  # unreachable: status ok always carries a day count
        days = 0
    if days <= LV2_HORIZON_DAYS:
        tier = TIER_SOON
    elif days <= LV3_HORIZON_DAYS:
        tier = TIER_MODERATE
    else:
        tier = TIER_FAR
    return Verdict(
        tier=tier, label=_TIER_META[tier],
        reason=f"{tier}: break-even in {days} day(s) → {proj.break_even_date}; {proj.note}",
        break_even_date=proj.break_even_date,
        pace_per_day=proj.pace_per_day,
        recovery_pct=recovery, net_roi_pct=net_roi,
        recovery_text=recovery_text, net_roi_text=net_roi_text,
        label_zh=_TIER_META_ZH[tier], roast=_TIER_ROASTS[tier],
        provisional=proj.provisional,
    )


# ---------------------------------------------------------------------------
# Self-test (smoke, no pytest dependency) — mirrors tests/test_verdict.py
# ---------------------------------------------------------------------------

def _selftest() -> int:
    import json
    from datetime import time as _time

    failures: list[str] = []
    utc = timezone.utc
    D = Decimal

    # 3-decimal formatting pins
    if format_percent(D("0")) != "0.000":
        failures.append("format 0")
    if format_percent(D("-0.0004")) != "0.000":
        failures.append("negative zero must normalize")
    if format_percent(D("12.3455")) != "12.346":
        failures.append("HALF_UP 12.3455")
    if format_percent(D("-5")) != "-5.000":
        failures.append("negative format")

    # LV2 at exactly day 90
    as_of = datetime(2026, 11, 3, 12, 0, tzinfo=utc)
    start = datetime(2026, 9, 1, tzinfo=utc)
    win = [datetime.combine(date(2026, 10, 5) + timedelta(days=k), _time(9, 0), tzinfo=utc)
           for k in range(30)]
    events: list[Event] = [(t, D(10)) for t in win] + [(datetime(2026, 9, 5, 9, 0, tzinfo=utc), D(7800))]
    v = make_verdict(as_of=as_of, start_at=start, events=events, hardware_cost=D(9000))
    if v.tier != "LV2" or v.break_even_date != date(2026, 11, 3) + timedelta(days=90):
        failures.append(f"LV2 boundary: {v.tier} {v.break_even_date} {v.reason}")

    # unknown onboarding: empty history
    v2 = make_verdict(as_of=as_of, start_at=start, events=[], hardware_cost=D(9000))
    if v2.tier != "unknown":
        failures.append(f"empty history must be unknown, got {v2.tier}")

    # float must be refused
    try:
        recovery_pct(1.5, 10)
        failures.append("float accepted in money path")
    except ValueError:
        pass

    out = {"failures": failures, "ok": not failures}
    print(json.dumps(out, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    import sys

    sys.exit(_selftest())
