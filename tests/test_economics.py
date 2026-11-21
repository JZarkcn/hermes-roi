"""Tests for dashboard/plugin_api.py GET /economics (T04b-wire).

Deterministic minimal store: ONE local session (loopback URL) with
1M input + 1M output tokens at T0 (2025-11-01 UTC), and ONE cloud
session (api.openai.com, model gpt-x). At the committed DeepSeek card's
flash peak row: (1M x 0.30 + 1M x 1.20) / 1e6 = exactly 1.500000 USD —
hand-computed, no float anywhere.

Run:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_activity_reader import T0  # noqa: E402
import dashboard.plugin_api as api  # noqa: E402

# Pinned "as of" for deterministic monthly-energy tests (via HERMES_ECON_NOW).
NOW_PIN = datetime(2025, 12, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()


def run(coro):
    return asyncio.run(coro)


def _make_eco_store(root: Path) -> None:
    """profiles/eco/state.db with schema_version + 2 fixture sessions."""
    home = root / "profiles" / "eco"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text("profile: eco\n")
    db = home / "state.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE schema_version (version TEXT);
        CREATE TABLE sessions (
          id TEXT PRIMARY KEY, source TEXT, model TEXT, parent_session_id TEXT,
          started_at REAL, ended_at REAL, input_tokens INTEGER DEFAULT 0,
          output_tokens INTEGER DEFAULT 0, cache_read_tokens INTEGER DEFAULT 0,
          cache_write_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0,
          billing_provider TEXT, billing_base_url TEXT, billing_mode TEXT,
          estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT,
          api_call_count INTEGER DEFAULT 0
        );
        """
    )
    conn.execute("INSERT INTO schema_version (version) VALUES ('32')")
    # s-local: loopback, 1M in + 1M out -> flash peak = 0.30 + 1.20 = 1.50 USD
    conn.execute(
        "INSERT INTO sessions (id, source, model, started_at, input_tokens,"
        " output_tokens, billing_provider, billing_base_url)"
        " VALUES ('s-local','cli','local-mlx', ?, 1000000, 1000000, NULL, ?)",
        (T0, "http://127.0.0.1:1234/v1"),
    )
    # s-cloud: openai-hosted, NOT local unless the user ticks gpt-x.
    # 500 in x 0.30/1e6 = 0.000150 + 100 out x 1.20/1e6 = 0.000120
    # => 0.000270 USD at peak flash
    conn.execute(
        "INSERT INTO sessions (id, source, model, started_at, input_tokens,"
        " output_tokens, billing_provider, billing_base_url)"
        " VALUES ('s-cloud','cli','gpt-x', ?, 500, 100, 'openai', ?)",
        (T0, "https://api.openai.com/v1"),
    )
    conn.commit()
    conn.close()


class EconomicsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="roi-eco-")
        self.root = Path(self._tmp.name) / ".hermes"
        _make_eco_store(self.root)
        self._old = os.environ.get("HERMES_TEST_ROOT")
        os.environ["HERMES_TEST_ROOT"] = str(self.root)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(
            lambda: os.environ.pop("HERMES_TEST_ROOT", None)
            if self._old is None else os.environ.__setitem__("HERMES_TEST_ROOT", self._old)
        )

    def _eco(self, **kw):
        kw.setdefault("scope", "eco")
        kw.setdefault("hardware_cost", "30")
        kw.setdefault("start_at", "2025-01-01")
        kw.setdefault("tz", "UTC")  # deterministic day bucketing
        return run(api.economics(**kw))

    def _add_recent_session(self, input_tokens=1000000, days_ago=10):
        """Append a local session `days_ago` days before now (in-window pace)."""
        db = self.root / "profiles" / "eco" / "state.db"
        conn = sqlite3.connect(str(db))
        ts = time.time() - days_ago * 86400
        conn.execute(
            "INSERT INTO sessions (id, source, model, started_at, input_tokens,"
            " output_tokens, billing_base_url)"
            " VALUES ('s-recent','cli','local-mlx', ?, ?, 0, ?)",
            (ts, input_tokens, "http://127.0.0.1:1234/v1"),
        )
        conn.commit()
        conn.close()

    def _pin_now(self, ts: float) -> None:
        """Pin the endpoint's 'as of' to ts via HERMES_ECON_NOW (determinism)."""
        old = os.environ.get("HERMES_ECON_NOW")
        os.environ["HERMES_ECON_NOW"] = str(ts)

        def _restore():
            if old is None:
                os.environ.pop("HERMES_ECON_NOW", None)
            else:
                os.environ["HERMES_ECON_NOW"] = old

        self.addCleanup(_restore)

    def _add_session_at(self, ts: float, input_tokens=1_000_000,
                        output_tokens=0) -> None:
        """Append a local session at an EXACT timestamp (for in-window pace)."""
        db = self.root / "profiles" / "eco" / "state.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO sessions (id, source, model, started_at, input_tokens,"
            " output_tokens, billing_base_url)"
            " VALUES ('s-inwin','cli','local-mlx', ?, ?, ?, ?)",
            (ts, input_tokens, output_tokens, "http://127.0.0.1:1234/v1"),
        )
        conn.commit()
        conn.close()

    # --- pricing + verdict wiring ------------------------------------------
    def test_health_exposes_benchmark_models(self):
        d = run(api.health())
        self.assertEqual(d["benchmark_models"],
                         ["deepseek-flash", "deepseek-v4-pro"])
        self.assertEqual(d["benchmark_default"], "deepseek-flash")
        self.assertTrue(d["economics_available"])

    def test_basic_gross_and_lv4_no_pace(self):
        d = self._eco()
        self.assertEqual(d["gross_usd"], "1.500000")
        self.assertEqual(d["net_usd"], "1.500000")
        self.assertEqual(d["local_sessions"], {"total": 1, "priced": 1, "unpriced": 0})
        self.assertEqual(d["benchmark"]["model"], "deepseek-flash")
        self.assertEqual(d["benchmark"]["basis"], "peak")
        self.assertEqual(d["benchmark"]["options"],
                         {"models": ["deepseek-flash", "deepseek-v4-pro"],
                          "default": "deepseek-flash"})
        self.assertEqual(d["benchmark"]["card_currency"], "USD")
        self.assertFalse(d["fx"]["applied"])
        self.assertFalse(d["energy"]["applied"])
        # T0 (2025-11-01) is outside the trailing-30-day window of "now":
        # pace 0, remaining > 0 -> LV4 no_positive_pace, no finite date.
        self.assertEqual(d["verdict"]["tier"], "LV4")
        self.assertEqual(d["break_even"]["state"], "no_positive_pace")
        self.assertIsNone(d["break_even"]["days_remaining"])
        self.assertIsNone(d["break_even"]["date"])
        # 100 x 1.5 / 30 = exactly 5.000 (3dp, hard product rule)
        self.assertEqual(d["verdict"]["recovery_pct"], "5.000")
        self.assertEqual(d["pace_window_days"], 30)
        # Bilingual verdict copy (original mockup, owner 2026-11-05)
        self.assertEqual(d["verdict"]["label"], "PAYBACK IS A DISTANT DREAM.")
        self.assertEqual(d["verdict"]["label_zh"], "回本遥遥无期！")
        self.assertIn("GPU", d["verdict"]["roast"])
        # Curve: actuals only, no projection, not crossed
        c = d["curve"]
        self.assertFalse(c["projected"])
        self.assertEqual(c["cost"], "30.000000")
        self.assertEqual(c["start"], "2025-01-01")
        self.assertIsNone(c["crossed"])
        self.assertGreaterEqual(len(c["points"]), 2)
        self.assertLessEqual(len(c["points"]), 500)
        self.assertEqual(c["points"][0]["d"], "2025-01-01")
        self.assertEqual(c["points"][0]["v"], "0.000000")
        self.assertEqual(c["points"][-1]["v"], "1.500000")

    def test_paid_off_is_lv1(self):
        d = self._eco(hardware_cost="0.000001")
        self.assertEqual(d["verdict"]["tier"], "LV1")
        self.assertEqual(d["break_even"]["state"], "already_paid_off")
        self.assertEqual(d["verdict"]["recovery_pct"], "150000000.000")
        self.assertEqual(d["verdict"]["label_zh"], "回本了·太强了！")
        # The curve crosses the cost line on the session day (2025-11-01)
        self.assertEqual(d["curve"]["crossed"], "2025-11-01")
        self.assertFalse(d["curve"]["projected"])

    def test_unknown_onboarding_is_strict(self):
        # D-022 option A: start after the anchor -> unknown, no fake date.
        d = self._eco(start_at="2030-01-01")
        self.assertEqual(d["verdict"]["tier"], "unknown")
        self.assertEqual(d["break_even"]["state"], "unknown")
        self.assertIsNone(d["break_even"]["date"])
        self.assertEqual(d["verdict"]["label_zh"], "数据不足·暂不评价")
        # Start in the future: no actuals, empty curve
        self.assertEqual(d["curve"]["points"], [])
        self.assertFalse(d["curve"]["projected"])

    def test_curve_projects_to_break_even(self):
        # Add a session 10 days ago -> in-window pace 0.30/30 = 0.01/day,
        # 30+ days of history -> status ok. Curve must extend linearly to
        # the break-even date where it meets the hardware-cost line exactly.
        self._add_recent_session()
        d = self._eco()
        self.assertEqual(d["break_even"]["state"], "ok")
        be = d["break_even"]["date"]
        self.assertIsNotNone(be)
        c = d["curve"]
        self.assertTrue(c["projected"])
        self.assertEqual(c["end"], be)
        self.assertIsNone(c["crossed"])
        last = c["points"][-1]
        self.assertEqual(last["d"], be)
        self.assertEqual(last["v"], "30.000000")  # == hw by construction

    def test_offpeak_basis(self):
        # flash off-peak: 1M x 0.15 + 1M x 0.60 = 0.750000
        d = self._eco(basis="off_peak")
        self.assertEqual(d["gross_usd"], "0.750000")
        self.assertEqual(d["benchmark"]["basis"], "off_peak")

    def test_energy_monthly_estimate(self):
        # 2 kWh/month x 0.5 USD/kWh = 1.00 USD/month; /30 = 0.033333/day.
        # start 2025-11-01, now pinned 2025-12-01 -> 30 days elapsed.
        # elapsed cost = 0.033333 x 30 = 1.000000 (flat offset on start day).
        # gross 1.50 (base session) - 1.00 = 0.50 net.
        # net pace = 0 (base session is outside the window) - 0.033333 < 0.
        self._pin_now(NOW_PIN)
        d = self._eco(start_at="2025-11-01", hardware_cost="30",
                      energy_price="0.5", energy_kwh="2")
        e = d["energy"]
        self.assertTrue(e["applied"])
        self.assertEqual(e["basis"], "monthly-estimate")
        self.assertEqual(e["kwh_per_month"], "2")
        self.assertEqual(e["monthly_usd"], "1.000000")
        self.assertEqual(e["per_day_usd"], "0.033333")
        self.assertEqual(e["elapsed_days"], 30)
        self.assertEqual(e["total_applied_usd"], "1.000000")
        self.assertEqual(d["gross_usd"], "1.500000")
        self.assertEqual(d["net_usd"], "0.500000")
        # Net pace is negative (recurring electricity exceeds the 0 gross
        # pace) -> no positive trajectory, LV4.
        self.assertEqual(d["break_even"]["state"], "no_positive_pace")
        self.assertEqual(d["verdict"]["tier"], "LV4")

    def test_energy_monthly_nets_the_pace(self):
        # In-window session at 2025-11-20 (1M in -> 0.30 flash peak) plus the
        # base session (2025-11-01, 1.50, OUTSIDE the window). window_net 0.30
        # -> gross pace 0.01/day. Energy 1 kWh/mo x 0.05 = 0.05/mo -> /30 =
        # 0.001666.../day. net pace = 0.01 - 0.001666... = 0.008333.../day.
        # start 2025-10-01, now 2025-12-01 -> 61 days; elapsed cost
        # = 0.001666... x 61 = 0.101667. total_net = 1.80 - 0.101667 = 1.698333.
        # hw 10 -> remaining 8.301667 -> ceil(/0.008333...) = 997 days.
        # The SAME rig with no energy breaks even in 820 days: energy must
        # push the date LATER, never earlier.
        self._pin_now(NOW_PIN)
        inwin = datetime(2025, 11, 20, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        self._add_session_at(inwin, input_tokens=1_000_000, output_tokens=0)
        d = self._eco(start_at="2025-10-01", hardware_cost="10",
                      energy_price="0.05", energy_kwh="1")
        e = d["energy"]
        self.assertEqual(e["monthly_usd"], "0.050000")
        self.assertEqual(e["elapsed_days"], 61)
        self.assertEqual(e["total_applied_usd"], "0.101667")
        self.assertEqual(d["gross_usd"], "1.800000")
        self.assertEqual(d["net_usd"], "1.698333")
        self.assertEqual(d["break_even"]["state"], "ok")
        self.assertEqual(d["break_even"]["pace_per_day_usd"], "0.008333")
        self.assertEqual(d["break_even"]["days_remaining"], 997)
        d2 = self._eco(start_at="2025-10-01", hardware_cost="10")
        self.assertEqual(d2["break_even"]["state"], "ok")
        self.assertEqual(d2["break_even"]["days_remaining"], 820)

    def test_allowlist_prices_cloud_lookalike(self):
        # Product rule: the tick alone makes it local, even on openai's URL.
        d = self._eco(local_models="gpt-x")
        self.assertEqual(d["local_sessions"]["total"], 2)
        self.assertEqual(d["gross_usd"], "1.500270")

    def test_global_scope_includes_all_profiles(self):
        d = self._eco(scope="all")
        self.assertEqual(d["scope"], "all")
        self.assertEqual(d["gross_usd"], "1.500000")

    # --- parameter errors ----------------------------------------------------
    def test_missing_hardware_cost_is_400(self):
        kw = dict(scope="eco", start_at="2025-01-01", tz="UTC")
        with self.assertRaises(Exception) as e:
            run(api.economics(**kw))
        self.assertEqual(getattr(e.exception, "status_code", None), 400)

    def test_zero_hardware_cost_is_400(self):
        with self.assertRaises(Exception) as e:
            self._eco(hardware_cost="0")
        self.assertEqual(getattr(e.exception, "status_code", None), 400)

    def test_bad_hardware_cost_is_400(self):
        with self.assertRaises(Exception) as e:
            self._eco(hardware_cost="abc")
        self.assertEqual(getattr(e.exception, "status_code", None), 400)

    def test_bad_start_at_is_400(self):
        with self.assertRaises(Exception) as e:
            self._eco(start_at="not-a-date")
        self.assertEqual(getattr(e.exception, "status_code", None), 400)

    def test_missing_start_at_is_400(self):
        with self.assertRaises(Exception) as e:
            run(api.economics(scope="eco", hardware_cost="30", tz="UTC"))
        self.assertEqual(getattr(e.exception, "status_code", None), 400)

    def test_unknown_benchmark_is_400(self):
        with self.assertRaises(Exception) as e:
            self._eco(benchmark="ghost-model")
        self.assertEqual(getattr(e.exception, "status_code", None), 400)

    def test_energy_half_given_is_400(self):
        with self.assertRaises(Exception) as e:
            self._eco(energy_price="0.5")
        self.assertEqual(getattr(e.exception, "status_code", None), 400)

    def test_unknown_scope_is_404(self):
        with self.assertRaises(Exception) as e:
            self._eco(scope="ghost")
        self.assertEqual(getattr(e.exception, "status_code", None), 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
