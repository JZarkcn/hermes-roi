#!/usr/bin/env python3
"""Hermes cron monitor script.

Each tick prints a single deterministic line:
    FREQ=<5min|hourly>;HOLIDAY=<0|1>;DOW=<0-6>

NOW is deliberately omitted: the scheduler runs this only on */5 boundaries,
and including :00/:05/:10... would make every tick look "changed" and wake
the agent 12x per hour even in the quiet 5-minute regime. The agent prompt
computes on-the-hour gating from the current clock instead.
"""
from datetime import datetime

now = datetime.now()
dow = now.weekday()  # 0=Mon
hour = now.hour

holiday = 0
try:
    # optional dependency; falls back to weekday-only when absent
    from chinese_calendar import is_holiday  # type: ignore
    holiday = 1 if is_holiday(now.date()) else 0
except Exception:
    holiday = 0

workday = (dow < 5) and (not holiday)
hourly = workday and (1 <= hour < 20)
freq = "hourly" if hourly else "5min"

print("FREQ=%s;HOLIDAY=%d;DOW=%d" % (freq, holiday, dow))
