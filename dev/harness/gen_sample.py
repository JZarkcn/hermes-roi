"""Generate REAL sample payloads for the visual smoke-test harness.

Builds a deterministic mini-store (600 days of loopback usage + a few real
cloud sessions), points HERMES_TEST_ROOT at it, and calls the actual
endpoint functions — so the harness renders exactly what the app receives.
"""
import asyncio
import json
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("HERMES_ROI_REPO") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(ROOT))

import dashboard.plugin_api as api  # noqa: E402

tmp = tempfile.TemporaryDirectory(prefix="roi-sample-")
root = Path(tmp.name) / ".hermes"
home = root / "profiles" / "main"
home.mkdir(parents=True)
(home / "config.yaml").write_text("profile: main\n")

conn = sqlite3.connect(str(home / "state.db"))
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

rng = random.Random(42)
now = api.time.time()
DAY = 86400
n = 0
for day in range(640, -1, -1):  # 640 days back from today
    if rng.random() < 0.18:
        continue  # idle days
    for k in range(rng.randint(1, 3)):
        ts = now - day * DAY - rng.randint(0, 20000)
        tin = rng.randint(80_000, 900_000)
        tout = rng.randint(4_000, 60_000)
        tcr = rng.randint(0, 200_000)
        local = rng.random() < 0.92
        if local:
            url, prov, model = "http://127.0.0.1:8000/v1", None, "qwen3-local"
        else:
            url, prov, model = "https://api.deepseek.com/v1", "deepseek", "deepseek-chat"
        conn.execute(
            "INSERT INTO sessions (id, source, model, started_at, input_tokens,"
            " output_tokens, cache_read_tokens, billing_provider, billing_base_url)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (f"s{n}", "cli", model, ts, tin, tout, tcr, prov, url))
        n += 1
conn.commit()
conn.close()
print(f"sessions: {n}")

os.environ["HERMES_TEST_ROOT"] = str(root)
# Pin the endpoint's "as of" to the same instant the sessions were generated,
# so the sample (elapsed energy, curve, break-even) is stable within a run.
os.environ["HERMES_ECON_NOW"] = str(now)

async def main():
    # start_at is overridable so the harness can exercise the provisional
    # (<30-day) estimate path end to end (Option B, owner 2026-11-06).
    start_at = os.environ.get("ROI_SAMPLE_START", "2025-01-01")
    eco = await api.economics(
        scope="all", hardware_cost="5000", start_at=start_at, tz="UTC",
        energy_price="0.12", energy_kwh="20")
    summ = await api.summary(scope="all", local_models="")
    health = await api.health()
    out = Path(os.environ.get("ROI_SAMPLE_OUT", "/tmp/roi-sample"))
    out.mkdir(exist_ok=True)
    for name, obj in [("economics", eco), ("summary", summ), ("health", health)]:
        (out / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    v = eco["verdict"]
    print("verdict:", v["tier"], "|", v["label_zh"], "|", v["label"])
    print("break_even:", eco["break_even"]["state"], eco["break_even"]["date"],
          "| pace", eco["break_even"]["pace_per_day_usd"])
    print("gross", eco["gross_usd"], "net", eco["net_usd"],
          "| curve pts", len(eco["curve"]["points"]), "projected", eco["curve"]["projected"])
    print("energy:", json.dumps(eco["energy"], ensure_ascii=False))
    print("summary keys:", sorted(summ.keys()))

asyncio.run(main())
