"""Tests for roi.activity_reader (T02 acceptance).

Covers: normal, empty, malformed schema, cache-heavy, mixed local/cloud,
all route classes, subagent independence, read-only enforcement, cross-profile
isolation, WAL concurrency, and timezone day bucketing.

Run:  python3 tests/test_activity_reader.py
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from roi import activity_reader as ar  # noqa: E402

# Deterministic epoch: 2025-11-01 00:00:00 UTC
T0 = 1_762_000_000.0
DAY = 86_400.0

# Expected totals for the 5 in-range fixture rows (window from T0, excl. s-old):
#   input:       1000 + 100 + 2000 + 700 + 300 = 4100
#   output:       500 +  50 +  800 + 200 + 100 = 1650
#   cache_read:   300 +   0 +  100 +   0 +   0 = 400
#   cache_write:  400 +   0 +    0 +   0 +   0 = 400
#   reasoning:     60 +   0 +  200 +   0 +   0 = 260
#   local_tokens (loopback only, no allowlist):
#                (1000+500+300+400) + (100+50) = 2350
#   unknown_route_tokens: 700 + 200 = 900
EXP_INPUT = 4100
EXP_OUTPUT = 1650
EXP_CR = 400
EXP_CW = 400
EXP_REASONING = 260
EXP_LOCAL_NO_ALLOW = 2350
EXP_UNKNOWN = 900


def _make_store(root: Path) -> Path:
    """Build a synthetic profile tree with a WAL-mode state.db + fixture rows."""
    home = root / "profiles" / "demo"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text("profile: demo\n")
    (root / "config.yaml").write_text("profile: default\n")

    db = home / "state.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE schema_version (version TEXT);
        INSERT INTO schema_version VALUES ('32');
        CREATE TABLE sessions (
          id TEXT PRIMARY KEY, source TEXT, model TEXT, parent_session_id TEXT,
          started_at REAL, ended_at REAL, input_tokens INTEGER DEFAULT 0,
          output_tokens INTEGER DEFAULT 0, cache_read_tokens INTEGER DEFAULT 0,
          cache_write_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0,
          billing_provider TEXT, billing_base_url TEXT, billing_mode TEXT,
          estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT,
          api_call_count INTEGER DEFAULT 0
        );
        CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, content TEXT);
        """
    )
    rows = [
        # root local session, loopback route, cache-heavy
        ("s-root-local", "gui", "m-local", None, T0, 1000, 500, 300, 400, 60,
        "custom", "http://127.0.0.1:8000/v1", "hybrid", 12),
        # subagent child — independent usage, counted exactly once
        ("s-child", "subagent", "m-local", "s-root-local", T0 + 60, 100, 50, 0, 0, 0,
        "custom", "http://127.0.0.1:8000/v1", "hybrid", 2),
        # cloud session with reasoning
        ("s-cloud", "cli", "gpt-x", None, T0 + 7200, 2000, 800, 100, 0, 200,
        "openai", "https://api.openai.com/v1", "standard", 30),
        # unknown route (NULL/NULL) — never priced, never counted as local
        ("s-unknown", "cron", "m-old", None, T0 + 14400, 700, 200, 0, 0, 0,
        None, None, None, 5),
        # local-named model served by a CLOUD endpoint — must be cloud w/o allowlist
        ("s-cloud-impersonator", "cli", "cloud-only-model", None, T0 + 20000, 300, 100, 0, 0, 0,
        "openai", "https://api.openai.com/v1", "standard", 4),
        # outside the default probe range (45 days earlier)
        ("s-old", "gui", "m-local", None, T0 - 45 * DAY, 50, 10, 0, 0, 0,
        "custom", "http://127.0.0.1:8000/v1", "hybrid", 1),
    ]
    conn.executemany(
        "INSERT INTO sessions (id, source, model, parent_session_id, started_at,"
        " input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens,"
        " billing_provider, billing_base_url, billing_mode, api_call_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.execute("INSERT INTO messages (session_id, content) VALUES ('s-root-local', 'SECRET USER TEXT')")
    conn.commit()
    conn.close()
    return db


class ActivityReaderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="roi-test-")
        self.root = Path(self._tmp.name) / ".hermes"
        self.db = _make_store(self.root)
        self.addCleanup(self._tmp.cleanup)

    def _summarize(self, since=None, until=None, **kw):
        return ar.summarize(self.root, "demo", since=since, until=until, **kw)

    # --- happy path ------------------------------------------------------

    def test_full_range_totals_and_route_split(self):
        # Windowed "full" range: everything from T0 onward (excludes s-old,
        # 45 days earlier — the unbounded full-history case is covered by
        # test_range_inclusive_lower_exclusive_upper's boundaries).
        s = self._summarize(since=T0)
        t = s.totals
        self.assertEqual(t["input_tokens"], EXP_INPUT)
        self.assertEqual(t["output_tokens"], EXP_OUTPUT)
        self.assertEqual(t["cache_read_tokens"], EXP_CR)
        self.assertEqual(t["cache_write_tokens"], EXP_CW)
        self.assertEqual(t["reasoning_tokens"], EXP_REASONING)
        self.assertEqual(s.total_sessions, 5)
        self.assertEqual(s.total_subagent_sessions, 1)
        self.assertEqual(s.schema_version, "32")
        self.assertEqual(t["local_tokens"], EXP_LOCAL_NO_ALLOW)
        self.assertEqual(t["unknown_route_tokens"], EXP_UNKNOWN)
        self.assertEqual(s.local_candidate_sessions, 2)
        self.assertEqual(s.unknown_route_sessions, 1)

    def test_model_name_never_classifies_local(self):
        """HARD RULE: a model name alone never classifies local.
        s-cloud-impersonator ('qwen3.5-27b' on api.openai.com) is only local
        when the allowlist explicitly names it; without the allowlist it is
        cloud."""
        s_no_allow = self._summarize(since=T0)
        self.assertEqual(s_no_allow.local_candidate_sessions, 2)  # loopback only
        s_allow = self._summarize(since=T0, local_model_allowlist=("cloud-only-model",))
        self.assertEqual(s_allow.local_candidate_sessions, 3)  # + impersonator via allowlist

    def test_subagent_not_double_counted(self):
        s = self._summarize(since=T0)
        self.assertEqual(s.totals["input_tokens"], EXP_INPUT)
        self.assertEqual(s.totals["subagent_sessions"], 1)

    # --- range boundaries --------------------------------------------------

    def test_range_inclusive_lower_exclusive_upper(self):
        s = self._summarize(since=T0, until=T0 + 61)
        self.assertEqual(s.total_sessions, 2)  # root + child only

    def test_empty_range_is_empty_not_error(self):
        s = self._summarize(since=T0 + DAY, until=T0 + 2 * DAY)
        self.assertEqual(s.total_sessions, 0)
        self.assertEqual(s.totals["input_tokens"], 0)
        self.assertTrue(any("no sessions in range" in n for n in s.audit_notes))

    # --- degradation -------------------------------------------------------

    def test_missing_store_raises_friendly_error(self):
        with self.assertRaises(FileNotFoundError):
            ar.open_read_only(self.root / "profiles" / "demo" / "missing.db")

    def test_missing_profile_raises(self):
        with self.assertRaises(ar.ProfileNotFoundError):
            ar.db_path(self.root, "nope")

    def test_unsafe_profile_names_rejected(self):
        for bad in ("", ".", "..", "a/b", "a\\b", ".hidden"):
            with self.assertRaises(ar.ProfileNotFoundError):
                ar.resolve_profile_home(self.root, bad)

    def test_non_profile_dir_rejected(self):
        stray = self.root / "profiles" / "stray"
        stray.mkdir(parents=True)
        (stray / "readme.txt").write_text("x")
        with self.assertRaises(ar.ProfileNotFoundError):
            ar.resolve_profile_home(self.root, "stray")

    def test_missing_required_column_refused(self):
        home = self.root / "profiles" / "stale"
        home.mkdir()
        (home / "config.yaml").write_text("p\n")
        db = home / "state.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE sessions (id TEXT, source TEXT, model TEXT, parent_session_id TEXT,"
            " started_at REAL, input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,"
            " reasoning_tokens INTEGER, billing_provider TEXT, billing_base_url TEXT)")
        conn.close()
        with self.assertRaises(ar.SchemaError) as ctx:
            ar.summarize(self.root, "stale")
        self.assertIn("cache_write_tokens", str(ctx.exception))

    # --- read-only enforcement ---------------------------------------------

    def test_write_through_ro_connection_fails(self):
        conn = ar.open_read_only(self.db)
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            conn.execute("INSERT INTO sessions (id) VALUES ('x')")
        self.assertIn("readonly", str(ctx.exception).lower())
        conn.close()

    def test_collector_never_selects_message_content(self):
        """The collector's SQL must never read or mutate the messages table.

        Only SELECT/UPDATE/DELETE literals are scanned: the module's own
        _selftest fixture setup INSERTs one message row deliberately (to
        prove it can't be read back), and mode=ro forbids any write anyway
        (see test_write_through_ro_connection_fails).
        """
        import inspect
        source = inspect.getsource(ar)
        sql_strings = re.findall(
            r'"\s*(?:SELECT|UPDATE|DELETE)\b[^"]*"', source, re.IGNORECASE)
        self.assertGreater(len(sql_strings), 0, "no SQL statements found in module?")
        for s in sql_strings:
            self.assertNotIn("messages", s.lower(), f"SQL references messages: {s}")

    # --- cross-profile isolation --------------------------------------------

    def test_process_hermes_home_cannot_redirect_resolution(self):
        """The target must come from the explicit (root, name) pair."""
        other = self.root / "profiles" / "other"
        other.mkdir(parents=True)
        (other / "state.db").write_bytes(b"x")
        (other / "config.yaml").write_text("p\n")
        old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(other)
        try:
            home = ar.resolve_profile_home(self.root, "demo")
            self.assertEqual(home, self.root / "profiles" / "demo")
            s = ar.summarize(self.root, "demo")
            self.assertGreater(s.total_sessions, 0)
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old

    # --- WAL concurrency ------------------------------------------------------

    def test_wal_concurrent_writer_does_not_block_reader(self):
        conn = ar.open_read_only(self.db)
        writer = sqlite3.connect(str(self.db))
        try:
            writer.execute("BEGIN")
            writer.execute("UPDATE sessions SET input_tokens = input_tokens + 1 WHERE id = 's-cloud'")
            rows = list(ar.iter_sessions(conn, since=T0 - DAY, until=T0 + 2 * DAY))
            total_in = sum(r.input_tokens for r in rows)
            self.assertEqual(total_in, EXP_INPUT)  # uncommitted update invisible
            writer.rollback()
            rows2 = list(ar.iter_sessions(conn, since=T0 - DAY, until=T0 + 2 * DAY))
            self.assertEqual(sum(r.input_tokens for r in rows2), EXP_INPUT)
        finally:
            writer.close()
            conn.close()

    # --- day bucketing (local timezone) -------------------------------------

    def test_day_bucketing_uses_local_timezone(self):
        s = self._summarize(since=T0, until=T0 + 8 * 3600)
        self.assertLessEqual(len(s.days), 2)
        for d in s.days:
            self.assertRegex(d.day, r"^\d{4}-\d{2}-\d{2}$")


def _make_default_store(root: Path) -> Path:
    """Build the DEFAULT profile's store (root/state.db) for global tests.

    Two rows in the T0 window: one cloud, one local via a ``localhost``
    base_url (a second loopback host form).
    """
    (root / "config.yaml").write_text("profile: default\n")
    db = root / "state.db"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE schema_version (version TEXT);
        INSERT INTO schema_version VALUES ('32');
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
    rows = [
        ("d-cloud", "cli", "gpt-y", None, T0 + 100, 100, 20, 0, 0, 0,
         "openai", "https://api.openai.com/v1", "standard", 3),
        ("d-local", "gui", "m-local", None, T0 + 200, 200, 40, 10, 5, 0,
         "custom", "http://localhost:8080/v1", "hybrid", 2),
    ]
    conn.executemany(
        "INSERT INTO sessions (id, source, model, parent_session_id, started_at,"
        " input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, reasoning_tokens,"
        " billing_provider, billing_base_url, billing_mode, api_call_count)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


class GlobalAggregateTest(unittest.TestCase):
    """ROI's primary scope: machine-global, never the active profile tab.

    Window [T0, T0+DAY) per-store expectations (no allowlist):
      demo:    5 sessions, in 4100, out 1650, cr 400, cw 400, reasoning 260,
               local 2350 (loopback), unknown 900
      default: 2 sessions, in 300, out 60, cr 10, cw 5, local 255 (localhost)
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="roi-global-")
        self.root = Path(self._tmp.name) / ".hermes"
        _make_store(self.root)
        _make_default_store(self.root)
        self.addCleanup(self._tmp.cleanup)

    def test_iter_profiles_default_first_and_store_only(self):
        # A live profile without a store is not listed (nothing to read).
        empty = self.root / "profiles" / "empty"
        empty.mkdir(parents=True)
        (empty / "config.yaml").write_text("p\n")
        self.assertEqual(ar.iter_profiles(self.root), ["default", "demo"])

    def test_global_totals_are_sum_of_profiles(self):
        s = ar.summarize_global(self.root, since=T0, until=T0 + DAY)
        self.assertEqual(s.profile_name, "all")
        self.assertEqual(s.profiles, ["default", "demo"])
        self.assertEqual(s.schema_version, "32")
        t = s.totals
        self.assertEqual(t["sessions"], 7)
        self.assertEqual(t["subagent_sessions"], 1)
        self.assertEqual(t["input_tokens"], 4400)
        self.assertEqual(t["output_tokens"], 1710)
        self.assertEqual(t["cache_read_tokens"], 410)
        self.assertEqual(t["cache_write_tokens"], 405)
        self.assertEqual(t["reasoning_tokens"], 260)
        self.assertEqual(t["local_tokens"], 2605)
        self.assertEqual(t["unknown_route_tokens"], 900)
        # Day buckets merge across stores; per-bucket sums stay exact.
        self.assertEqual(sum(d.sessions for d in s.days), 7)
        self.assertEqual(sum(d.local_tokens for d in s.days), 2605)

    def test_global_allowlist_applies_to_every_profile(self):
        # The cloud-hosted lookalike name is local only because the user
        # ticked it — the URL is api.openai.com.
        s = ar.summarize_global(
            self.root, since=T0, until=T0 + DAY,
            local_model_allowlist=("cloud-only-model",),
        )
        self.assertEqual(s.totals["local_tokens"], 2605 + 400)
        self.assertEqual(s.local_candidate_sessions, 4)  # demo 3 + default 1

    def test_global_empty_range_is_empty_not_error(self):
        s = ar.summarize_global(self.root, since=T0 + 3 * DAY, until=T0 + 4 * DAY)
        self.assertEqual(s.total_sessions, 0)
        self.assertTrue(
            any("no sessions in range across any profile" in n for n in s.audit_notes))

    def test_global_without_any_store(self):
        empty_root = self.root.parent / "empty-root"
        empty_root.mkdir(parents=True, exist_ok=True)
        s = ar.summarize_global(empty_root, since=T0, until=T0 + DAY)
        self.assertEqual(s.total_sessions, 0)
        self.assertEqual(s.profiles, [])
        self.assertTrue(any("no local profiles" in n for n in s.audit_notes))


class LiveGlobalSmokeTest(unittest.TestCase):
    """P0 Q9 + D-001 (live): the machine-global aggregate against the real host.

    Structural assertions only — stable under live WAL writes:
    * every listed profile has a state.db file;
    * the global rollup reads ALL stores without error (schema probe per store);
    * an empty store (0 rows in range) is a valid contribution, not an error;
    * totals are non-negative; writes are refused on the live stores.
    Exact live counts drift under writes — see
    docs/FINDINGS-global-aggregate-roi-dev.md §2 for this host's full-history
    acceptance numbers (9 stores, all schema v32, one empty store).
    Skipped when no real host store is present.
    """

    def test_live_global_rollup(self):
        import time
        root = Path(os.environ.get("HERMES_TEST_ROOT", "~/.hermes")).expanduser()
        if not (root / "state.db").is_file():
            self.skipTest(f"no default-profile store at {root}")
        profiles = ar.iter_profiles(root)
        self.assertIn("default", profiles)
        for name in profiles:
            self.assertTrue(ar.db_path(root, name).is_file(), name)
        now = time.time()
        s = ar.summarize_global(root, since=now - 86400, until=now)
        self.assertEqual(s.profile_name, "all")
        self.assertEqual(s.profiles, profiles)
        self.assertGreaterEqual(s.total_sessions, 0)
        for k, v in s.totals.items():
            self.assertGreaterEqual(v, 0, k)
        # Read-only guarantee against the LIVE production stores.
        conn = ar.open_read_only(ar.db_path(root, profiles[0]))
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("UPDATE sessions SET input_tokens = 0 WHERE id IS NOT NULL")
        finally:
            conn.close()


class LiveCrossProfileSmokeTest(unittest.TestCase):
    """P0 Q9 (live): read the DEFAULT profile's state.db from a process whose
    own HERMES_HOME points at a different profile, via the explicit
    (root, name) contract. Skipped when no real default store is present."""

    def test_cross_profile_read_only(self):
        import time
        root = Path(os.environ.get("HERMES_TEST_ROOT", "~/.hermes")).expanduser()
        if not (root / "state.db").is_file():
            self.skipTest(f"no default-profile store at {root}")
        old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(root / "profiles" / "roi-dev")
        try:
            home = ar.resolve_profile_home(root, "default")
            self.assertEqual(home, root)
            now = time.time()
            s = ar.summarize(root, "default", since=now - 86400, until=now)
            self.assertGreaterEqual(s.total_sessions, 0)
            for k, v in s.totals.items():
                self.assertGreaterEqual(v, 0, k)
            # read-only guarantee against the LIVE production store
            conn = ar.open_read_only(root / "state.db")
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("UPDATE sessions SET message_count = 0 WHERE id IS NOT NULL")
            finally:
                conn.close()
        finally:
            if old is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
