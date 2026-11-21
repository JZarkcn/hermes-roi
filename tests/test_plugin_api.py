"""Tests for dashboard/plugin_api.py (T03 backend smoke).

Runs the real endpoint functions in-process against a synthetic profile
store (no gateway, no fastapi required — the module guards that import).

Contract under test:
  * scope=all (default) aggregates EVERY local profile store — ROI is
    machine-global and must never follow the active profile tab.
  * scope=<name> scopes to one profile.
  * local_models= is the user-ticked allowlist (comma-separated); a name
    alone is a user declaration, never an inference.

Run:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_activity_reader import (  # noqa: E402
    EXP_INPUT, EXP_OUTPUT, EXP_CR, EXP_CW, EXP_REASONING,
    EXP_LOCAL_NO_ALLOW, EXP_UNKNOWN, T0, DAY,
    _make_store, _make_default_store,
)
import dashboard.plugin_api as api  # noqa: E402


def run(coro):
    return asyncio.run(coro)


class PluginApiTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="roi-api-")
        self.root = Path(self._tmp.name) / ".hermes"
        _make_store(self.root)
        _make_default_store(self.root)
        self._old = os.environ.get("HERMES_TEST_ROOT")
        os.environ["HERMES_TEST_ROOT"] = str(self.root)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(
            lambda: os.environ.pop("HERMES_TEST_ROOT", None)
            if self._old is None else os.environ.__setitem__("HERMES_TEST_ROOT", self._old)
        )

    def test_health_reports_contract_and_store(self):
        h = run(api.health())
        self.assertTrue(h["ok"])
        self.assertEqual(h["plugin"], "hermes-roi")
        self.assertEqual(h["contract_version"], api.CONTRACT_VERSION)
        self.assertTrue(h["default_store_present"])
        self.assertEqual(h["hermes_root"], str(self.root))

    def test_default_scope_is_global_all_profiles(self):
        # No scope parameter at all -> machine-global (product rule #1).
        s = run(api.summary(since=str(T0), until=str(T0 + DAY)))
        self.assertEqual(s["scope"], "all")
        self.assertEqual(s["profile"], "all")
        self.assertEqual(s["profiles"], ["default", "demo"])
        t = s["totals"]
        # demo [T0, T0+DAY): 5 rows; default: 2 rows.
        self.assertEqual(t["sessions"], 7)
        self.assertEqual(t["input_tokens"], 4100 + 300)
        self.assertEqual(t["output_tokens"], 1650 + 60)
        self.assertEqual(t["local_tokens"], 2350 + 255)
        self.assertEqual(t["unknown_route_tokens"], EXP_UNKNOWN)

    def test_scope_single_profile_matches_collector(self):
        s = run(api.summary(scope="demo", since=str(T0), until=str(T0 + DAY)))
        self.assertEqual(s["scope"], "demo")
        self.assertEqual(s["profiles"], ["demo"])
        self.assertEqual(s["schema_version"], "32")
        t = s["totals"]
        self.assertEqual(t["input_tokens"], EXP_INPUT)
        self.assertEqual(t["output_tokens"], EXP_OUTPUT)
        self.assertEqual(t["cache_read_tokens"], EXP_CR)
        self.assertEqual(t["cache_write_tokens"], EXP_CW)
        self.assertEqual(t["reasoning_tokens"], EXP_REASONING)
        self.assertEqual(t["sessions"], 5)
        self.assertEqual(t["subagent_sessions"], 1)
        self.assertEqual(t["local_tokens"], EXP_LOCAL_NO_ALLOW)
        self.assertEqual(t["unknown_route_tokens"], EXP_UNKNOWN)
        self.assertEqual(s["local_candidate_sessions"], 2)
        self.assertEqual(s["unknown_route_sessions"], 1)
        self.assertEqual(s["local_models"], [])

    def test_local_models_allowlist_is_user_declaration(self):
        # Product rule #2: the cloud-hosted lookalike becomes local ONLY via
        # the user's tick, even though its URL is api.openai.com.
        s = run(api.summary(scope="demo", since=str(T0), until=str(T0 + DAY),
                            local_models="cloud-only-model"))
        self.assertEqual(s["local_models"], ["cloud-only-model"])
        self.assertEqual(s["local_candidate_sessions"], 3)
        self.assertEqual(s["totals"]["local_tokens"], EXP_LOCAL_NO_ALLOW + 400)
        # Whitespace-tolerant, empty entries dropped.
        s2 = run(api.summary(scope="demo", since=str(T0), until=str(T0 + DAY),
                             local_models="  , cloud-only-model ,"))
        self.assertEqual(s2["local_models"], ["cloud-only-model"])

    def test_global_local_models_apply_to_every_profile(self):
        s = run(api.summary(scope="all", since=str(T0), until=str(T0 + DAY),
                            local_models="cloud-only-model"))
        self.assertEqual(s["totals"]["local_tokens"], 2605 + 400)
        self.assertEqual(s["local_candidate_sessions"], 4)

    def test_summary_days_window_is_calendar_days(self):
        # Fixture rows sit in 2025; "last 30 days" from now is empty, and
        # the empty state is reported (not an error).
        s = run(api.summary(scope="demo", days="30"))
        self.assertEqual(s["totals"]["sessions"], 0)
        self.assertEqual(s["days"], [])
        self.assertTrue(any("no sessions in range" in n for n in s["audit_notes"]))
        # Window math: exactly `days` calendar days wide.
        self.assertAlmostEqual(s["until"] - s["since"], 30 * 86400, delta=1.0)

    def test_summary_payload_never_carries_message_content(self):
        s = run(api.summary(scope="all", since=str(T0), until=str(T0 + DAY)))
        blob = json.dumps(s)
        self.assertNotIn("SECRET USER TEXT", blob)
        self.assertNotIn('"content"', blob)

    def test_unknown_scope_profile_is_404(self):
        try:
            run(api.summary(scope="ghost", since=str(T0), until=str(T0 + DAY)))
            self.fail("expected HTTPException")
        except Exception as e:
            self.assertEqual(getattr(e, "status_code", None), 404)

    def test_bad_days_is_400(self):
        try:
            run(api.summary(scope="demo", days="abc"))
            self.fail("expected HTTPException")
        except Exception as e:
            self.assertEqual(getattr(e, "status_code", None), 400)

    def test_until_before_since_is_400(self):
        try:
            run(api.summary(scope="demo", since=str(T0 + 5000), until=str(T0)))
            self.fail("expected HTTPException")
        except Exception as e:
            self.assertEqual(getattr(e, "status_code", None), 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
