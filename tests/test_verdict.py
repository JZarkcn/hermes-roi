"""Tests for roi.verdict (T04 acceptance).

Covers: all four tiers + the 'unknown' onboarding state, exact boundaries
(day 90 inclusive, day 1825 inclusive, net == hardware exactly), zero pace,
negative net, empty history, insufficient history, near/far break-even
dates, 3-decimal formatting (0.000, 12.346 HALF_UP rounding), and the UTC+8
timezone day-boundary.

Run:  python3 tests/test_verdict.py
"""
from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from roi import verdict as vd  # noqa: E402

D = Decimal
UTC = timezone.utc
TZ8 = timezone(timedelta(hours=8))

# Forecast anchor: 2026-11-03 12:00 UTC → as_of_date 2026-11-03 (UTC).
AS_OF = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
# Effective start: 2026-09-01 → 63 calendar days elapsed (≥ 30, sufficient).
START = datetime(2026, 9, 1, tzinfo=UTC)
# The trailing 30 calendar days in UTC: 2026-10-05 .. 2026-11-03.
WINDOW = [date(2026, 10, 5) + timedelta(days=k) for k in range(30)]


def window_events(amount) -> list:
    """One event per window day at 09:00 UTC (all < AS_OF 12:00 UTC)."""
    return [(datetime.combine(d, time(9, 0), tzinfo=UTC), D(amount)) for d in WINDOW]


def day90_fixture() -> list:
    """total_net 8100, window_net 300 → pace exactly 10/day."""
    return window_events(D(10)) + [(datetime(2026, 9, 5, 9, 0, tzinfo=UTC), D(7800))]


class PercentMathTest(unittest.TestCase):
    def test_recovery_pct_basic(self):
        # 100 × 12345.5 / 100000 = exactly 12.3455 → ROUND_HALF_UP → 12.346
        self.assertEqual(vd.recovery_pct(D("12345.5"), D("100000")), D("12.346"))

    def test_recovery_pct_half_up_pin(self):
        # 12.3445 → HALF_UP 12.345 (HALF_EVEN would give 12.344): pins the
        # documented rounding mode.
        self.assertEqual(vd.recovery_pct(D("123445"), D("1000000")), D("12.345"))

    def test_recovery_pct_zero(self):
        self.assertEqual(vd.recovery_pct(D(0), D(1000)), D("0.000"))

    def test_net_roi_pct(self):
        # 100 × (25000−10000)/10000 = 150; 100 × (2500−10000)/10000 = −75
        self.assertEqual(vd.net_roi_pct(D("25000"), D("10000")), D("150.000"))
        self.assertEqual(vd.net_roi_pct(D("2500"), D("10000")), D("-75.000"))

    def test_format_percent_exactly_three_decimals(self):
        self.assertEqual(vd.format_percent(D(0)), "0.000")
        self.assertEqual(vd.format_percent(D("-5")), "-5.000")
        self.assertEqual(vd.format_percent(D(150)), "150.000")
        self.assertEqual(vd.format_percent(D("12.3455")), "12.346")

    def test_format_percent_no_negative_zero(self):
        self.assertEqual(vd.format_percent(D("-0.0004")), "0.000")

    def test_zero_hardware_raises(self):
        with self.assertRaises(ValueError):
            vd.recovery_pct(D(10), D(0))
        with self.assertRaises(ValueError):
            vd.net_roi_pct(D(10), D(0))

    def test_float_refused_in_money_path(self):
        with self.assertRaises(ValueError):
            vd.recovery_pct(1.5, 10)  # type: ignore[arg-type]

    def test_naive_datetime_refused(self):
        with self.assertRaises(ValueError):
            vd.make_verdict(as_of=datetime(2026, 11, 3), start_at=START,
                            events=[], hardware_cost=D(1000))


class TierTest(unittest.TestCase):
    def test_lv1_net_equals_hardware_exactly(self):
        # net 10000 == hardware 10000 (inclusive) → paid off, recovery 100.000
        events = window_events(D(10)) + [(datetime(2026, 9, 5, 9, 0, tzinfo=UTC), D(9700))]
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=events,
                            hardware_cost=D(10000))
        self.assertEqual(v.tier, "LV1")
        self.assertEqual(v.recovery_text, "100.000")
        self.assertEqual(v.net_roi_text, "0.000")
        self.assertIsNone(v.break_even_date)

    def test_lv1_net_above_hardware(self):
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=day90_fixture(),
                            hardware_cost=D(8000))
        self.assertEqual(v.tier, "LV1")
        self.assertEqual(v.recovery_text, "101.250")  # 100×8100/8000

    def test_lv2_day90_inclusive(self):
        # remaining 900 / pace 10 = exactly 90 days → day 90 is LV2 (inclusive)
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=day90_fixture(),
                            hardware_cost=D(9000))
        self.assertEqual(v.tier, "LV2")
        self.assertEqual(v.break_even_date, date(2026, 11, 3) + timedelta(days=90))
        self.assertEqual(v.break_even_date, date(2027, 2, 1))  # pinned near date
        self.assertEqual(v.recovery_text, "90.000")
        self.assertEqual(v.net_roi_text, "-10.000")

    def test_lv3_day1825_inclusive(self):
        # remaining 26350−8100 = 18250, pace 10 → exactly 1825 days → LV3
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=day90_fixture(),
                            hardware_cost=D(26350))
        self.assertEqual(v.tier, "LV3")
        self.assertEqual(v.break_even_date, date(2026, 11, 3) + timedelta(days=1825))

    def test_lv4_beyond_1825(self):
        # 26360−8100 = 18260 remaining / 10 = 1826 days > 5-year horizon → LV4
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=day90_fixture(),
                            hardware_cost=D(26360))
        self.assertEqual(v.tier, "LV4")
        self.assertEqual(v.break_even_date, date(2026, 11, 3) + timedelta(days=1826))

    def test_zero_pace_is_lv4(self):
        # Usage exists (net 5000) but entirely before the 30-day window →
        # window net 0, pace 0 → no positive trajectory → LV4, no date.
        events = [(datetime(2026, 9, 5, 9, 0, tzinfo=UTC), D(5000))]
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=events,
                            hardware_cost=D(10000))
        self.assertEqual(v.tier, "LV4")
        self.assertIsNone(v.break_even_date)
        self.assertEqual(v.pace_per_day, D(0))
        self.assertEqual(v.recovery_text, "50.000")

    def test_negative_net_is_lv4(self):
        # Negative net everywhere: pace −10/day, total −2300 → LV4, no date
        events = window_events(D(-10)) + [(datetime(2026, 9, 5, 9, 0, tzinfo=UTC), D(-2000))]
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=events,
                            hardware_cost=D(10000))
        self.assertEqual(v.tier, "LV4")
        self.assertIsNone(v.break_even_date)
        self.assertEqual(v.recovery_text, "-23.000")
        self.assertEqual(v.net_roi_text, "-123.000")

    def test_zero_usage_days_count_in_denominator(self):
        # 15 active days × 20 = 300 over 30 calendar days → pace is 300/30
        # = 10 (NOT 300/15 = 20): zero-usage days slow the pace. Same day-90
        # boundary holds: remaining 900 / 10 → LV2.
        events = [
            (datetime.combine(WINDOW[k], time(9, 0), tzinfo=UTC), D(20))
            for k in range(0, 30, 2)
        ] + [(datetime(2026, 9, 5, 9, 0, tzinfo=UTC), D(7800))]
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=events,
                            hardware_cost=D(9000))
        self.assertEqual(v.tier, "LV2")
        self.assertEqual(v.break_even_date, date(2027, 2, 1))


class UnknownOnboardingTest(unittest.TestCase):
    def test_empty_history_is_unknown_not_a_tier(self):
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=[],
                            hardware_cost=D(9000))
        self.assertEqual(v.tier, "unknown")
        self.assertNotIn(v.tier, ("LV1", "LV2", "LV3", "LV4"))
        self.assertIsNone(v.break_even_date)
        self.assertIn("no usage recorded", v.reason)

    def test_insufficient_history_is_provisional(self):
        # 14 calendar days elapsed < 30 → Option B provisional estimate
        # (NOT unknown): window = all 15 available days (10-20..11-03), net
        # 15×$10 = $150, pace 150/15 = $10/day, remaining 9000−150 = 8850,
        # 8850/10 = 885 days → LV3, flagged provisional.
        recent_start = datetime(2026, 10, 20, tzinfo=UTC)
        v = vd.make_verdict(as_of=AS_OF, start_at=recent_start,
                            events=window_events(D(10)), hardware_cost=D(9000))
        self.assertEqual(v.tier, "LV3")
        self.assertTrue(v.provisional)
        self.assertEqual(v.break_even_date, date(2026, 11, 3) + timedelta(days=885))
        self.assertEqual(v.recovery_text, "1.667")  # 100×150/9000
        self.assertIn("PROVISIONAL", v.reason)

    def test_provisional_pace_divides_by_actual_days(self):
        # 10 days elapsed (start 10-24 → as_of 11-03) = 11 calendar days
        # 10-24..11-03. 11 events × $5 = $55 → pace = 55/11 = $5/day (NOT
        # 55/30 = $1.83). Pins the provisional denominator = elapsed+1 days.
        recent_start = datetime(2026, 10, 24, tzinfo=UTC)
        evs = [(datetime.combine(date(2026, 10, 24) + timedelta(days=k),
                                 time(9, 0), tzinfo=UTC), D(5))
               for k in range(11)]
        p = vd.project_break_even(as_of=AS_OF, start_at=recent_start, events=evs,
                                  hardware_cost=D(5000))
        self.assertTrue(p.provisional)
        self.assertEqual(p.pace_days, 11)
        self.assertEqual(p.window_net, D(55))
        self.assertEqual(p.total_net, D(55))
        self.assertEqual(p.pace_per_day, D(5))

    def test_provisional_requires_usage_else_unknown(self):
        # <30 days but NO usage → still the unknown onboarding state (no
        # estimate to make), and not flagged provisional.
        recent_start = datetime(2026, 10, 24, tzinfo=UTC)
        v = vd.make_verdict(as_of=AS_OF, start_at=recent_start, events=[],
                            hardware_cost=D(5000))
        self.assertEqual(v.tier, "unknown")
        self.assertFalse(v.provisional)
        self.assertIn("no usage recorded", v.reason)

    def test_day30_boundary_is_standard_not_provisional(self):
        # elapsed exactly 30 (start 10-04 → as_of 11-03) → the full trailing-
        # 30-day window exists → standard, never provisional.
        recent_start = datetime(2026, 10, 4, tzinfo=UTC)
        p = vd.project_break_even(as_of=AS_OF, start_at=recent_start,
                                  events=window_events(D(10)), hardware_cost=D(9000))
        self.assertFalse(p.provisional)
        self.assertEqual(p.pace_days, vd.PACE_WINDOW_DAYS)
        self.assertEqual(p.status, "ok")

    def test_standard_history_not_provisional(self):
        # Default fixture (63 days elapsed) is far past 30 → standard window.
        p = vd.project_break_even(as_of=AS_OF, start_at=START,
                                  events=day90_fixture(), hardware_cost=D(9000))
        self.assertFalse(p.provisional)
        self.assertEqual(p.pace_days, vd.PACE_WINDOW_DAYS)

    def test_start_after_asof_is_unknown(self):
        v = vd.make_verdict(as_of=AS_OF, start_at=AS_OF + timedelta(days=1),
                            events=window_events(D(10)), hardware_cost=D(9000))
        self.assertEqual(v.tier, "unknown")


class BoundaryAndRangeTest(unittest.TestCase):
    def test_future_events_dropped(self):
        # Events at/after AS_OF must not count: total stays 8100 → LV2.
        events = day90_fixture() + [
            (AS_OF, D(500)),
            (AS_OF + timedelta(hours=1), D(500)),
        ]
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=events,
                            hardware_cost=D(9000))
        self.assertEqual(v.tier, "LV2")
        self.assertEqual(v.recovery_text, "90.000")

    def test_pre_start_events_dropped(self):
        # Before the effective start date → not counted as hardware savings.
        events = day90_fixture() + [(datetime(2026, 8, 1, 9, 0, tzinfo=UTC), D(5000))]
        v = vd.make_verdict(as_of=AS_OF, start_at=START, events=events,
                            hardware_cost=D(9000))
        self.assertEqual(v.tier, "LV2")
        self.assertEqual(v.recovery_text, "90.000")

    def test_naive_event_timestamp_refused(self):
        with self.assertRaises(ValueError):
            vd.make_verdict(as_of=AS_OF, start_at=START,
                            events=[(datetime(2026, 10, 10, 9, 0), D(10))],
                            hardware_cost=D(1000))

    def test_float_event_amount_refused(self):
        with self.assertRaises(ValueError):
            vd.make_verdict(as_of=AS_OF, start_at=START,
                            events=[(AS_OF - timedelta(days=1), 10.5)],  # type: ignore[list-item]
                            hardware_cost=D(1000))


class TimezoneTest(unittest.TestCase):
    """Day buckets are calendar days in the display tz (default UTC).

    AS_OF8 = 2026-11-01 16:30 UTC = 2026-11-02 00:30 UTC+8: the two zones
    disagree on both the anchor's calendar day and the 30-day window start,
    so the same event is inside the UTC window and outside the +8 window.
    """

    AS_OF8 = datetime(2026, 11, 1, 16, 30, tzinfo=UTC)
    E = (datetime(2026, 10, 3, 0, 0, tzinfo=UTC), D(3000))  # 08:00 on 10-03 in +8

    def test_utc8_window_boundary(self):
        # UTC: as_of day 2026-11-01 → window 10-03..11-01 → E (10-03) inside:
        #       window_net 3000, pace 100, remaining 97000 → exactly 970 days.
        p_utc = vd.project_break_even(
            as_of=self.AS_OF8, start_at=START, events=[self.E],
            hardware_cost=D(100000), tz=UTC)
        self.assertEqual(p_utc.status, "ok")
        self.assertEqual(p_utc.window_net, D(3000))
        self.assertEqual(p_utc.pace_per_day, D(100))
        self.assertEqual(p_utc.days_remaining, 970)
        self.assertEqual(p_utc.break_even_date, date(2026, 11, 1) + timedelta(days=970))

        # UTC+8: as_of day 2026-11-02 → window 10-04..11-02 → E's +8 day is
        # 10-03, OUTSIDE the window → window_net 0, pace 0, no finite date.
        p_8 = vd.project_break_even(
            as_of=self.AS_OF8, start_at=START, events=[self.E],
            hardware_cost=D(100000), tz=TZ8)
        self.assertEqual(p_8.status, "no_positive_pace")
        self.assertEqual(p_8.window_net, D(0))
        self.assertEqual(p_8.days_remaining, None)
        self.assertIsNone(p_8.break_even_date)
        # Same absolute money, different calendar-day bucketing:
        self.assertEqual(p_8.total_net, p_utc.total_net)

    def test_tz8_verdict_tiers_differ(self):
        v_utc = vd.make_verdict(as_of=self.AS_OF8, start_at=START, events=[self.E],
                                hardware_cost=D(100000), tz=UTC)
        v_8 = vd.make_verdict(as_of=self.AS_OF8, start_at=START, events=[self.E],
                              hardware_cost=D(100000), tz=TZ8)
        self.assertEqual(v_utc.tier, "LV3")  # 970 ≤ 1825
        self.assertEqual(v_8.tier, "LV4")    # no positive pace


if __name__ == "__main__":
    unittest.main()
