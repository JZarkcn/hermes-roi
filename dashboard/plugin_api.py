"""hermes-roi backend — mounted at /api/plugins/hermes-roi/.

Read-only by construction: every route reads the target profile's state.db
through ``roi.activity_reader`` (SQLite ``mode=ro``). No route writes
anything, and no route ever selects message content (DATA_CONTRACT.md).

Run context: inside the gateway process (desktop-plugin-sdk docs, "The
Python side"). The machine Hermes root is resolved from this process's own
environment; the target profile is always an explicit query parameter —
never implied from the process's active profile (issue #18594 trap,
DATA_CONTRACT.md §9).

Contract: ``GET /summary`` returns ``CONTRACT_VERSION``-ed JSON. Bump
``CONTRACT_VERSION`` on any breaking shape change; the desktop page pins
the version it renders.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from roi import activity_reader as ar  # noqa: E402
from roi import cards as pc  # noqa: E402
from roi import energy as en  # noqa: E402
from roi import fx as fxc  # noqa: E402
from roi import pricing as pr  # noqa: E402
from roi import verdict as vd  # noqa: E402

import re  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from decimal import Decimal, InvalidOperation  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

PLUGIN_VERSION = "0.1.0"
CONTRACT_VERSION = 0  # /summary JSON shape; bump on breaking change

try:  # fastapi ships in the gateway venv; guard for standalone unit tests
    from fastapi import APIRouter, HTTPException  # type: ignore[assignment]
except Exception:  # pragma: no cover - test environments without fastapi
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class APIRouter:
        def get(self, *_a, **_k):
            def deco(fn):
                return fn
            return deco


try:
    from hermes_constants import get_default_hermes_root
except Exception:  # pragma: no cover - standalone test environments
    get_default_hermes_root = None  # type: ignore[assignment]


def hermes_root() -> Path:
    """The machine Hermes root (holds the default home and all profiles).

    ``get_default_hermes_root()`` returns the root that *holds* this
    process's home, so a gateway running under a named profile still
    resolves the machine root correctly. Test hook: ``HERMES_TEST_ROOT``
    overrides (unit tests only; documented, not a security boundary).
    """
    override = os.environ.get("HERMES_TEST_ROOT", "").strip()
    if override:
        return Path(override).expanduser()
    if get_default_hermes_root is not None:
        return get_default_hermes_root()
    env = os.environ.get("HERMES_HOME", "").strip()
    p = Path(env).expanduser() if env else Path.home() / ".hermes"
    return p.parent.parent if p.parent.name == "profiles" else p


router = APIRouter()


def _parse_days(raw: str | None) -> int:
    try:
        d = int(raw) if raw else 30
    except ValueError:
        raise HTTPException(400, "days must be an integer")
    return max(1, min(d, 731))


@router.get("/health")
async def health() -> dict:
    root = hermes_root()
    # Benchmark dropdown options for the page: the card's model list.
    # Health must stay a liveness probe: a broken card degrades to None,
    # it never 500s the probe.
    models = None
    default_model = None
    try:
        card = pc.load_card(basis="peak")
        models = sorted(card.raw.get("models") or {})
        default_model = card.default_model
    except Exception:
        models = None
    return {
        "ok": True,
        "plugin": "hermes-roi",
        "version": PLUGIN_VERSION,
        "contract_version": CONTRACT_VERSION,
        "hermes_root": str(root),
        "default_store_present": (root / "state.db").is_file(),
        "economics_available": True,
        "benchmark_models": models,
        "benchmark_default": default_model,
    }


@router.get("/summary")
async def summary(
    scope: str = "all",
    days: str | None = None,
    since: str | None = None,
    until: str | None = None,
    local_models: str | None = None,
) -> dict:
    """Read-only usage summary (DATA_CONTRACT.md §8).

    ``scope``: ``"all"`` (default) aggregates every local profile store —
    ROI is machine-global and never follows the active profile tab. Any
    other value scopes to that one profile.

    ``local_models``: comma-separated user-declared local model names
    (P2 settings tick-list). A name alone is a user declaration, never an
    inference; the loopback route check remains a candidate hint, and the
    union of the two is what counts as local.

    Window: explicit ``[since, until)`` epochs win; otherwise the trailing
    ``days`` calendar days ending now (default 30, max 731).
    """
    now = time.time()
    if since is not None or until is not None:
        try:
            s = float(since) if since is not None else None
            u = float(until) if until is not None else now
        except ValueError:
            raise HTTPException(400, "since/until must be epoch numbers")
        if s is not None and u <= s:
            raise HTTPException(400, "until must be after since")
    else:
        d = _parse_days(days)
        u, s = now, now - d * 86400

    allow = tuple(m.strip() for m in (local_models or "").split(",") if m.strip())
    try:
        # Off the event loop: the read is short but the store may be large.
        if scope == "all":
            res = await asyncio.to_thread(
                ar.summarize_global, hermes_root(), s, u, allow
            )
        else:
            res = await asyncio.to_thread(
                ar.summarize, hermes_root(), scope, s, u, allow
            )
    except ar.ProfileNotFoundError as e:
        raise HTTPException(404, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, f"no session store for profile {scope!r}: {e}")
    except ar.SchemaError as e:
        raise HTTPException(500, f"unsupported store schema: {e}")

    return {
        "contract_version": CONTRACT_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "scope": scope,
        "profiles": res.profiles,
        "profile": res.profile_name,
        "as_of": now,
        "since": s,
        "until": u,
        "schema_version": res.schema_version,
        "local_models": list(allow),
        "totals": res.totals,
        "local_candidate_sessions": res.local_candidate_sessions,
        "unknown_route_sessions": res.unknown_route_sessions,
        "days": [
            {
                "day": d.day,
                "sessions": d.sessions,
                "subagent_sessions": d.subagent_sessions,
                "input_tokens": d.input_tokens,
                "output_tokens": d.output_tokens,
                "cache_read_tokens": d.cache_read_tokens,
                "cache_write_tokens": d.cache_write_tokens,
                "reasoning_tokens": d.reasoning_tokens,
                "local_tokens": d.local_tokens,
                "unknown_route_tokens": d.unknown_route_tokens,
            }
            for d in res.days
        ],
        "audit_notes": res.audit_notes or [],
    }


# ---------------------------------------------------------------------------
# GET /economics — hypothetical cloud-equivalent economics (D-018~D-022)
# ---------------------------------------------------------------------------


def _dec(raw: str, name: str) -> Decimal:
    """Exact Decimal from a query-string value; refuses float/inf/nan."""
    try:
        d = Decimal(raw)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"{name} must be a decimal number, got {raw!r}") from e
    if not d.is_finite():
        raise ValueError(f"{name} must be finite")
    return d


def _tzinfo(raw: str | None):
    """IANA tz from the param; default = the machine's local timezone."""
    if not raw or not raw.strip():
        return datetime.now().astimezone().tzinfo
    try:
        return ZoneInfo(raw.strip())
    except Exception as e:
        raise ValueError(f"unknown IANA timezone {raw.strip()!r}") from e


def _parse_start(raw: str | None, tzinfo) -> datetime:
    """start_at as epoch seconds or YYYY-MM-DD (midnight in the display tz)."""
    if not raw or not raw.strip():
        raise ValueError("start_at is required (epoch seconds or YYYY-MM-DD)")
    r = raw.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", r):
        y, m, d = (int(x) for x in r.split("-"))
        try:
            return datetime(y, m, d, tzinfo=tzinfo)
        except ValueError as e:
            raise ValueError(f"start_at is not a valid date: {r!r}") from e
    try:
        return datetime.fromtimestamp(float(r), tz=tzinfo)
    except (ValueError, OverflowError, OSError) as e:
        raise ValueError("start_at must be epoch seconds or YYYY-MM-DD") from e


def _is_local(row: "ar.SessionRow", allow: set) -> bool:
    """D-002: local = loopback candidate OR user-ticked model (union). A
    model name alone is a user declaration, never an inference."""
    if row.route.is_local_candidate():
        return True
    return bool(row.route.model) and row.route.model in allow


def _collect_events(
    root: Path,
    scope: str,
    allow: set,
    snapshot,
    benchmark: str,
    fx_table: dict | None,
    tzinfo,
) -> tuple[list, int, int, Decimal]:
    """Every local session in scope, priced at the benchmark row.

    Returns (events, local_count, priced_count, gross). Each event is
    (tz-aware datetime, USD Decimal) — the verdict module's Event shape.
    Unknown stores in a global scope are a legitimate zero contribution
    (DATA_CONTRACT §9a).
    """
    names = ar.iter_profiles(root) if scope == "all" else [scope]
    if scope != "all" and not ar.db_path(root, scope).is_file():
        raise HTTPException(404, f"no session store for profile {scope!r}")
    need_fx = snapshot.currency != "USD"
    events: list = []
    n_local = n_priced = 0
    gross = Decimal("0")
    for name in names:
        p = ar.db_path(root, name)
        if not p.is_file():
            continue
        with ar.open_read_only(p) as conn:
            for row in ar.iter_sessions(conn, None, None):
                if not _is_local(row, allow):
                    continue
                n_local += 1
                bd = pr.price_model_usage(
                    [(benchmark, {
                        "input": row.input_tokens,
                        "output": row.output_tokens,
                        "cache_read": row.cache_read_tokens,
                        "cache_write": row.cache_write_tokens,
                        "reasoning": row.reasoning_tokens,
                    })],
                    snapshot,
                )
                if benchmark in bd.unknown_models:
                    continue  # benchmark not in the card — stays unpriced
                n_priced += 1
                cost = bd.priced
                if need_fx:
                    if fx_table is None:
                        raise HTTPException(500, "FX table unavailable")
                    cost = fxc.to_usd(cost, snapshot.currency, fx_table)
                if cost > 0:
                    events.append(
                        (datetime.fromtimestamp(row.started_at, tz=tzinfo), cost))
                gross += cost
    return events, n_local, n_priced, gross


def _build_curve(events, start, now_aware, tzinfo, hw, proj):
    """Cumulative-net curve for the savings chart (2026-11-05 mockup).

    Daily cumulative sum of *events* (the energy offset already lives in
    the stream as a negative event on the start day, so the curve is net
    and consistent with the hero / break-even math) from the effective
    start day to today. When the projection has a positive pace, a linear
    segment extends to the break-even date, where the curve meets the
    hardware-cost line exactly by construction. ``crossed`` marks the
    first real day the cumulative net reached the hardware cost (if ever).
    Points are decimated to <= 500 for the SVG payload.
    """
    start_d = start.astimezone(tzinfo).date()
    now_d = now_aware.astimezone(tzinfo).date()
    out = {
        "start": start_d.isoformat(),
        "end": now_d.isoformat(),
        "cost": str(hw.quantize(Decimal("0.000001"))),
        "projected": False,
        "crossed": None,
        "points": [],
    }
    if now_d < start_d:
        return out  # start date in the future: no actuals yet
    by_day = {}
    for ts, cost in events:
        d = ts.astimezone(tzinfo).date()
        if start_d <= d <= now_d:
            by_day[d] = by_day.get(d, Decimal(0)) + cost
    series = []
    cum = Decimal(0)
    d = start_d
    while d <= now_d:
        cum += by_day.get(d, Decimal(0))
        series.append((d, cum))
        if out["crossed"] is None and cum >= hw:
            out["crossed"] = d.isoformat()
        d += timedelta(days=1)
    if len(series) > 500:
        step = -(-len(series) // 500)  # ceil
        series = series[::step] + [series[-1]]
    end = now_d
    if (proj.status == vd.STATUS_OK and proj.break_even_date is not None
            and proj.break_even_date > now_d):
        # v(break-even date) == hw exactly by the projection's definition
        # (pace x D >= remaining with D the first whole day that suffices,
        # so the drawn segment slightly overstates the last stretch — the
        # chart is illustrative; the date and pace remain the contract).
        series.append((proj.break_even_date, hw))
        end = proj.break_even_date
        out["projected"] = True
    out["end"] = end.isoformat()
    out["points"] = [
        {"d": d.isoformat(), "v": str(c.quantize(Decimal("0.000001")))}
        for d, c in series
    ]
    return out


@router.get("/economics")
async def economics(
    scope: str = "all",
    local_models: str | None = None,
    hardware_cost: str | None = None,
    start_at: str | None = None,
    benchmark: str | None = None,
    basis: str = "peak",
    energy_price: str | None = None,
    energy_kwh: str | None = None,
    energy_ccy: str = "USD",
    tz: str | None = None,
) -> dict:
    """Hypothetical cloud-equivalent savings + the four-tier verdict.

    Prices every LOCAL session (D-002 union) at the committed DeepSeek
    card's *benchmark* row (*basis* default "peak", D-018/D-022), converts
    to USD when the card currency differs (Xe snapshot, D-019), subtracts
    the optional flat energy offset (D-020), then runs the verdict with
    the strict unknown-onboarding state (D-022 option A).

    Machine-global by default (scope=all) — same rule as /summary. All
    figures are ESTIMATES of cloud API cost avoided; never money earned.
    """
    # --- validate parameters (fast, before touching the store) -------------
    try:
        if not hardware_cost or not hardware_cost.strip():
            raise ValueError("hardware_cost is required (decimal string, > 0)")
        hw = _dec(hardware_cost.strip(), "hardware_cost")
        if hw <= 0:
            raise ValueError("hardware_cost must be > 0")
        tzinfo = _tzinfo(tz)
        start = _parse_start(start_at, tzinfo)
        if (energy_price is None) != (energy_kwh is None):
            raise ValueError(
                "energy_price and energy_kwh must be given together")
        # Energy is a MONTHLY usage estimate (D-020 revised): nobody tracks
        # cumulative kWh, so the field is kWh/month. The rate (price ×
        # kWh/month), FX conversion, the ELAPSED cost (rate/30 × days since
        # start) and the recurring pace deduction are all computed in
        # _compute(), where the FX table is in scope (FxError is caught there)
        # and `now` is known.
        energy_in = None
        if energy_price is not None and energy_kwh is not None:
            energy_in = {"price": energy_price,
                         "kwh_per_month": energy_kwh,
                         "ccy": energy_ccy.strip().upper() or "USD"}
    except ValueError as e:
        raise HTTPException(400, str(e))

    allow = {m.strip() for m in (local_models or "").split(",") if m.strip()}
    # Determinism seam (tests pin HERMES_ECON_NOW); production = real time.
    now = (float(os.environ["HERMES_ECON_NOW"])
           if os.environ.get("HERMES_ECON_NOW") else time.time())

    def _compute() -> dict:
        try:
            card = pc.load_card(basis=basis)
        except pc.CardError as e:
            raise HTTPException(500, f"price card unavailable: {e}")
        bench = (benchmark or card.default_model).strip()
        if bench not in card.snapshot.prices:
            raise HTTPException(
                400, f"benchmark {bench!r} not in the card "
                     f"(available: {sorted(card.snapshot.prices)})")
        need_fx = card.snapshot.currency != "USD"
        fx_table = fxc.load_fx_table() if (need_fx or (energy_in and energy_in["ccy"] != "USD")) else None
        try:
            events, n_local, n_priced, gross = _collect_events(
                hermes_root(), scope, allow, card.snapshot, bench, fx_table, tzinfo)
            now_aware = datetime.fromtimestamp(now, tz=tzinfo)
            # --- Energy, MONTHLY estimate (D-020 revised) ------------------
            # rate USD/month = price × kWh/month (FX'd to USD when ccy≠USD).
            # The ELAPSED portion (rate/30 × days since start) is a flat
            # offset on the start day → feeds total_net / hero %. The ongoing
            # rate/30 per day is netted out of the break-even pace so the
            # projection keeps paying for electricity. Affects NET only.
            energy_rate_per_day = None
            energy_usd_past = None
            energy_elapsed_days = 0
            energy_out = None
            if energy_in is not None:
                monthly = en.energy_cost(
                    _dec(energy_in["price"], "energy_price"),
                    _dec(energy_in["kwh_per_month"], "energy_kwh"))
                if energy_in["ccy"] != "USD":
                    if fx_table is None:
                        raise fxc.FxError(
                            "FX table unavailable for energy currency "
                            f"{energy_in['ccy']}")
                    monthly = fxc.to_usd(monthly, energy_in["ccy"], fx_table)
                energy_rate_per_day = monthly / Decimal(30)
                now_date = now_aware.astimezone(tzinfo).date()
                start_date = start.astimezone(tzinfo).date()
                energy_elapsed_days = max(0, (now_date - start_date).days)
                energy_usd_past = (
                    energy_rate_per_day * Decimal(energy_elapsed_days)
                ).quantize(Decimal("0.000001"))
                if energy_usd_past != 0:
                    events.append((start, -energy_usd_past))
                energy_out = {
                    "applied": True,
                    "basis": "monthly-estimate",
                    "price": energy_in["price"],
                    "kwh_per_month": energy_in["kwh_per_month"],
                    "ccy": energy_in["ccy"],
                    "monthly_usd": str(monthly.quantize(Decimal("0.000001"))),
                    "per_day_usd": str(
                        energy_rate_per_day.quantize(Decimal("0.000001"))),
                    "elapsed_days": energy_elapsed_days,
                    "total_applied_usd": str(energy_usd_past),
                }
            recurring = (energy_rate_per_day
                         if energy_rate_per_day is not None else Decimal(0))
            proj = vd.project_break_even(
                as_of=now_aware, start_at=start, events=events,
                hardware_cost=hw, tz=tzinfo, recurring_cost_per_day=recurring)
            v = vd.make_verdict(
                as_of=now_aware, start_at=start, events=events,
                hardware_cost=hw, tz=tzinfo, recurring_cost_per_day=recurring)
        except fxc.FxError as e:
            raise HTTPException(500, f"FX conversion failed: {e}")
        except ar.ProfileNotFoundError as e:
            raise HTTPException(404, str(e))
        except ar.SchemaError as e:
            raise HTTPException(500, f"unsupported store schema: {e}")

        net = proj.total_net  # includes the energy offset (net, per D-020)
        fx_rate = None
        fx_as_of = None
        fx_source = None
        if need_fx and fx_table is not None:
            r = fx_table.get(card.snapshot.currency)
            if r is not None:
                fx_rate = str(r.rate)
                fx_as_of = str(r.as_of)
                fx_source = r.source
        return {
            "contract_version": CONTRACT_VERSION,
            "plugin_version": PLUGIN_VERSION,
            "scope": scope,
            "as_of": now,
            "start_at": start.isoformat(),
            "benchmark": {
                "model": bench,
                "basis": basis,
                "card_provider": card.raw.get("provider"),
                "card_currency": card.snapshot.currency,
                "card_as_of": str(card.snapshot.as_of),
                "card_source": card.source,
                "options": {"models": sorted(card.raw.get("models") or {}),
                            "default": card.default_model},
            },
            "fx": {
                "applied": need_fx,
                "rate_per_usd": fx_rate,
                "as_of": fx_as_of,
                "source": fx_source,
            },
            "energy": energy_out or {
                "applied": False,
                "basis": "monthly-estimate",
            },
            "hardware_cost_usd": str(hw),
            "local_sessions": {"total": n_local, "priced": n_priced,
                               "unpriced": n_local - n_priced},
            "gross_usd": str(gross.quantize(Decimal("0.000001"))),
            "net_usd": str(net.quantize(Decimal("0.000001"))),
            "pace_window_days": vd.PACE_WINDOW_DAYS,
            "break_even": {
                "state": proj.status,
                "date": str(proj.break_even_date) if proj.break_even_date else None,
                "days_remaining": proj.days_remaining,
                "pace_per_day_usd": (str(proj.pace_per_day.quantize(Decimal("0.000001")))
                                     if proj.pace_per_day else None),
                "provisional": proj.provisional,
                "pace_days": proj.pace_days,
                "note": proj.note,
            },
            "curve": _build_curve(events, start, now_aware, tzinfo, hw, proj),
            "verdict": {
                "tier": v.tier,
                "label": v.label,
                "label_zh": v.label_zh,
                "roast": v.roast,
                "reason": v.reason,
                "recovery_pct": v.recovery_text,
                "net_roi_pct": v.net_roi_text,
                "provisional": v.provisional,
            },
        }

    return await asyncio.to_thread(_compute)
