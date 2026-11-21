"""Deterministic synthetic test fixture for the hermes-roi activity collector.

SYNTHETIC DATA — every row below is invented for testing. No real session ids,
model deployments, accounts or usage patterns appear here. It deliberately
reproduces the edge cases documented in docs/DATA_CONTRACT.md:

* local vs cloud routes (loopback base URLs, cloud endpoints)
* the TRAP: a locally-named model served by a cloud endpoint
* a parent + subagent pair (independent rows, no aggregation)
* a mid-session model switch (sessions.model = first accounted route)
* a zero-token placeholder session with no route info
* reasoning tokens (subset of output — must not be double counted)
* boundary sessions exactly at since (included) / until (excluded) / before since

Time reference: day 0 = 2026-10-01 00:00:00 UTC = epoch 1790812800.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DAY0 = 1790812800.0          # 2026-10-01 00:00:00 UTC
SINCE = DAY0                 # inclusive lower bound for the default test range
UNTIL = DAY0 + 7 * 86400     # exclusive upper bound: 2026-10-08 00:00:00 UTC

H = 3600.0

LOCAL_MODEL = "qwen-local-27b"
OTHER_LOCAL_MODEL = "other-local-7b"
CLOUD_MODEL = "gpt-6-luna"
LOCAL_BASE = "http://127.0.0.1:1234/v1"
LOCAL_BASE_ALT = "http://127.0.0.1:8000/v1"
CLOUD_BASE = "https://chatgpt.com/backend-api/codex"
CLOUD_PROXY_BASE = "https://api.example-cloud.example/v1"

# (id, source, model, parent, started_at, in, out, cr, cw, r, provider, base_url,
#  billing_mode, cost_status, api_calls)
ROWS = [
    ("s_local_1", "tui", LOCAL_MODEL, None, DAY0 + 6 * H,
     1000, 100, 500, 50, 0, "lmstudio", LOCAL_BASE, None, "unknown", 4),
    ("s_cloud_1", "cli", CLOUD_MODEL, None, DAY0 + 86400 + 6 * H,
     2000, 300, 800, 0, 50, "openai-codex", CLOUD_BASE, "subscription_included", "included", 3),
    # THE TRAP: locally-named model on a cloud endpoint -> must classify CLOUD
    ("s_trap_1", "cli", LOCAL_MODEL, None, DAY0 + 2 * 86400 + 6 * H,
     900, 90, 0, 0, 0, "custom", CLOUD_PROXY_BASE, None, "unknown", 1),
    # parent + subagent: independent rows, parent does NOT include child usage
    ("s_parent_1", "local", LOCAL_MODEL, None, DAY0 + 3 * 86400 + 6 * H,
     4000, 200, 100, 0, 0, "lmstudio", LOCAL_BASE, None, "unknown", 5),
    ("s_child_1", "subagent", LOCAL_MODEL, "s_parent_1", DAY0 + 3 * 86400 + 7 * H,
     1500, 150, 0, 0, 0, "lmstudio", LOCAL_BASE, None, "unknown", 2),
    # mid-session switch: sessions row keeps the FIRST accounted route
    ("s_switch_1", "local", LOCAL_MODEL, None, DAY0 + 4 * 86400 + 6 * H,
     3000, 300, 0, 0, 0, "lmstudio", LOCAL_BASE, None, "unknown", 6),
    # zero-token placeholder, no route info at all
    ("s_zero_1", "local", None, None, DAY0 + 5 * 86400 + 6 * H,
     0, 0, 0, 0, 0, None, None, None, None, 0),
    # reasoning tokens are a SUBSET of output (OpenAI-family wire)
    ("s_reason_1", "local", LOCAL_MODEL, None, DAY0 + 6 * 86400 + 6 * H,
     100, 1000, 0, 0, 700, "lmstudio", LOCAL_BASE_ALT, None, "unknown", 2),
    # boundary: exactly at SINCE -> included
    ("s_boundary_in", "local", OTHER_LOCAL_MODEL, None, SINCE,
     250, 10, 0, 0, 0, "lmstudio", LOCAL_BASE, None, "unknown", 1),
    # boundary: exactly at UNTIL -> excluded
    ("s_boundary_out", "local", LOCAL_MODEL, None, UNTIL,
     500, 50, 0, 0, 0, "lmstudio", LOCAL_BASE, None, "unknown", 1),
    # before range: excluded
    ("s_before_1", "local", LOCAL_MODEL, None, SINCE - 1.0,
     777, 77, 0, 0, 0, "lmstudio", LOCAL_BASE, None, "unknown", 1),
]

# session_model_usage rows (session_id, model, provider, base_url, task, in, out)
MODEL_USAGE_ROWS = [
    ("s_local_1", LOCAL_MODEL, "lmstudio", LOCAL_BASE, "", 1000, 100),
    ("s_switch_1", LOCAL_MODEL, "lmstudio", LOCAL_BASE, "", 2000, 200),
    ("s_switch_1", CLOUD_MODEL, "openai-codex", CLOUD_BASE, "", 1000, 100),
]

EXPECTED = {
    "in_range": {
        "sessions": 8,          # roots
        "subagents": 1,         # s_child_1
        "input": 1000 + 2000 + 900 + 4000 + 1500 + 3000 + 0 + 100 + 250,   # 12750
        "output": 100 + 300 + 90 + 200 + 150 + 300 + 0 + 1000 + 10,        # 2150
        "cache_read": 500 + 800 + 0 + 100 + 0 + 0 + 0 + 0 + 0,             # 1400
        "cache_write": 50,
        "reasoning": 50 + 700,                                             # 750
        "local_input": 1000 + 4000 + 1500 + 3000 + 100 + 250,              # 9850
        "cloud_input": 2000 + 900,                                         # 2900
    },
    "schema_version": 32,
}


def build(db_path: str | Path) -> dict:
    """Create the synthetic state.db at db_path; return EXPECTED constants."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE schema_version (version INTEGER NOT NULL)
        """)
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (EXPECTED["schema_version"],))
        conn.execute("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                model TEXT,
                parent_session_id TEXT,
                started_at REAL NOT NULL,
                ended_at REAL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                reasoning_tokens INTEGER DEFAULT 0,
                billing_provider TEXT,
                billing_base_url TEXT,
                billing_mode TEXT,
                estimated_cost_usd REAL,
                actual_cost_usd REAL,
                cost_status TEXT,
                cost_source TEXT,
                pricing_version TEXT,
                api_call_count INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                tool_call_count INTEGER DEFAULT 0,
                profile_name TEXT
            )
        """)
        for r in ROWS:
            (sid, source, model, parent, started, inp, out, cr, cw, rsn,
             provider, base, bmode, cstatus, calls) = r
            conn.execute(
                """INSERT INTO sessions
                   (id, source, model, parent_session_id, started_at,
                    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                    reasoning_tokens, billing_provider, billing_base_url, billing_mode,
                    estimated_cost_usd, actual_cost_usd, cost_status, cost_source,
                    api_call_count, profile_name)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sid, source, model, parent, started, inp, out, cr, cw, rsn,
                 provider, base, bmode,
                 0.0, 0.0, cstatus, "none", calls, "default"))
        conn.execute("""
            CREATE TABLE session_model_usage (
                session_id TEXT NOT NULL,
                model TEXT NOT NULL,
                billing_provider TEXT NOT NULL DEFAULT '',
                billing_base_url TEXT NOT NULL DEFAULT '',
                billing_mode TEXT NOT NULL DEFAULT '',
                task TEXT NOT NULL DEFAULT '',
                api_call_count INTEGER NOT NULL DEFAULT 0,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cache_read_tokens INTEGER NOT NULL DEFAULT 0,
                cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd REAL NOT NULL DEFAULT 0,
                actual_cost_usd REAL NOT NULL DEFAULT 0,
                cost_status TEXT,
                cost_source TEXT,
                first_seen REAL,
                last_seen REAL,
                PRIMARY KEY (session_id, model, billing_provider,
                             billing_base_url, billing_mode, task)
            )
        """)
        for (sid, model, provider, base, task, inp, out) in MODEL_USAGE_ROWS:
            conn.execute(
                """INSERT INTO session_model_usage
                   (session_id, model, billing_provider, billing_base_url, billing_mode,
                    task, api_call_count, input_tokens, output_tokens, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (sid, model, provider, base, "", task, 1, inp, out, SINCE, UNTIL))
        conn.commit()
    finally:
        conn.close()
    return EXPECTED


def write_json_sample(out_path: str | Path) -> Path:
    """Write the human-readable sanitized sample (clearly labeled synthetic)."""
    sample = {
        "_label": ("SYNTHETIC TEST FIXTURE — invented rows for hermes-roi unit tests. "
                   "No real sessions, models, accounts or usage patterns."),
        "_source_schema": "Hermes state.db v32 subset (sessions, session_model_usage)",
        "since_epoch": SINCE,
        "until_epoch": UNTIL,
        "sessions": [
            {
                "id": sid, "source": source, "model": model, "parent_session_id": parent,
                "started_at": started,
                "input_tokens": inp, "output_tokens": out, "cache_read_tokens": cr,
                "cache_write_tokens": cw, "reasoning_tokens": rsn,
                "billing_provider": provider, "billing_base_url": base,
                "billing_mode": bmode, "cost_status": cstatus, "api_call_count": calls,
            }
            for (sid, source, model, parent, started, inp, out, cr, cw, rsn,
                 provider, base, bmode, cstatus, calls) in ROWS
        ],
        "session_model_usage": [
            {"session_id": sid, "model": model, "billing_provider": provider,
             "billing_base_url": base, "task": task,
             "input_tokens": inp, "output_tokens": out}
            for (sid, model, provider, base, task, inp, out) in MODEL_USAGE_ROWS
        ],
        "expected": EXPECTED,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sample, indent=2) + "\n")
    return out_path


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("activity_fixture.db")
    build(target)
    write_json_sample(target.with_suffix(".json"))
    print(f"fixture written: {target}")
