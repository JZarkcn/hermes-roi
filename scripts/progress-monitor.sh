#!/usr/bin/env bash
# ROI progress monitor — invoked by the cronjob (docs/DECISIONS.md D-004).
# Deterministic and read-only. Prints a compact status block; exit 0 = healthy,
# exit 1 = needs attention. Designed to run unattended every 30 minutes.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Host (machine) Hermes root: strip /profiles/<name> when HERMES_HOME is a
# profile home — install + config + logs live at the host scope (D-011).
HH_RAW="${HERMES_HOME:-$HOME/.hermes}"
case "$HH_RAW" in
  */profiles/*) HH="${HH_RAW%/*/*}" ;;
  *)            HH="$HH_RAW" ;;
esac
HOST_CFG="$HH/config.yaml"
PLUGIN_DIR="$HH/plugins/hermes-roi"
LOGS="$HH/logs"

fail=0
say() { printf '%s\n' "$*"; }

# --- 1. repo + git -----------------------------------------------------------
if ! cd "$REPO" 2>/dev/null; then
  say "git: REPO MISSING at $REPO"
  exit 1
fi
last=$(git log -1 --format='%h %s' 2>/dev/null)
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
say "git: ${last:-<no commits yet>} | dirty_files=$dirty"

# --- 2. unit tests -----------------------------------------------------------
tout=$(python3 -m unittest discover -s tests 2>&1)
if printf '%s' "$tout" | grep -q '^OK'; then
  n=$(printf '%s\n' "$tout" | grep -oE 'Ran [0-9]+' | grep -oE '[0-9]+' | head -1)
  say "tests: OK ($n tests)"
else
  say "tests: FAIL"
  printf '%s\n' "$tout" | tail -6
  fail=1
fi

# --- 3. collector selftest ---------------------------------------------------
if python3 roi/activity_reader.py 2>/dev/null | grep -q '"ok": true'; then
  say "collector: selftest ok"
else
  say "collector: selftest FAIL"
  fail=1
fi

# --- 4. install + enablement -------------------------------------------------
if [ -d "$PLUGIN_DIR" ]; then
  say "install: present ($PLUGIN_DIR)"
else
  say "install: MISSING -> run 'node scripts/install-local.mjs' from $REPO"
  fail=1
fi
if [ -d "$PLUGIN_DIR" ] && [ ! -f "$PLUGIN_DIR/__init__.py" ]; then
  say "install: BROKEN — no top-level __init__.py (directory-plugin contract; re-run installer from the current repo)"
  fail=1
fi
if grep -qE '^[[:space:]]*-[[:space:]]*hermes-roi[[:space:]]*$' "$HOST_CFG" 2>/dev/null; then
  say "config: hermes-roi in default plugins.enabled"
else
  say "config: hermes-roi NOT in default plugins.enabled (D-011)"
  fail=1
fi

# --- 5. backend mount state ---------------------------------------------------
# Verified 2026-11-02 (source: web_server_plugin_profiles.py): the backend is
# LAZILY mounted on the first desktop request (module
# hermes_dashboard_plugin_<name>) — there is NO "mounted" log line, and the
# `Plugin <id>:` pattern assumed in an earlier version of this script does
# not exist in v0.22.5. The CLI-verifiable signals are:
#   a. discovery — `hermes plugins list` shows hermes-roi enabled;
#   b. freshness — gateway last start AFTER the install mtime;
#   c. no import failure for the plugin in gateway.error.log since the
#      current install/start (time-floored, erratum 2026-11-04).
# A raw grep for "hermes-roi" in the logs is NOT usable: agent tool-error
# lines mention the repo path and false-positive (observed 2026-11-02).
if hermes --profile default plugins list 2>/dev/null | grep -q "hermes-roi"; then
  say "discovery: hermes-roi enabled (plugins list)"
else
  say "discovery: hermes-roi NOT listed (install/enable broken?)"
  fail=1
fi
last_start_line=$(grep -h "Gateway control socket listening" "$LOGS/gateway.log" 2>/dev/null | tail -1)
start_m=0
if [ -n "$last_start_line" ]; then
  ts=$(printf '%s\n' "$last_start_line" | awk '{print $1" "$2}' | cut -d, -f1)
  start_m=$(date -j -f "%Y-%m-%d %H:%M:%S" "$ts" +%s 2>/dev/null || echo 0)
fi
install_m=$(stat -f %m "$PLUGIN_DIR" 2>/dev/null || echo 0)
# Time floor (erratum 2026-11-04): only import failures logged AFTER
# max(last gateway start, install mtime) can describe the CURRENT install
# state; older lines (e.g. pre-fix copies in other profiles' plugin dirs)
# are history and must not pin the status at ATTENTION every tick.
floor_m=$(( start_m > install_m ? start_m : install_m ))
floor_s=$(date -j -f "%s" "$floor_m" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "0000-00-00 00:00:00")
mount_err=$(grep -h "hermes-roi" "$LOGS/gateway.error.log" 2>/dev/null \
  | grep -iE "traceback|importerror|modulenotfound|failed" \
  | awk -v floor="$floor_s" '{ ts = substr($1 " " $2, 1, 19); if (ts > floor) print }' | tail -3)
if [ -n "$mount_err" ]; then
  say "backend: MOUNT ERROR (import failure in gateway.error.log):"
  printf '%s\n' "$mount_err"
  fail=1
elif [ "$start_m" -eq 0 ] || [ "$install_m" -eq 0 ]; then
  say "backend: unknown (cannot date the last gateway start or the install)"
elif [ "$start_m" -lt "$install_m" ]; then
  say "backend: PENDING RESTART (gateway started before install; owner-run: hermes --profile default gateway restart)"
else
  say "backend: ready (gateway fresh + no import errors; lazy mount — confirm the ROI page in the desktop)"
fi

# --- verdict -----------------------------------------------------------------
if [ "$fail" -eq 0 ]; then
  say "STATUS: OK"
else
  say "STATUS: ATTENTION"
fi
exit "$fail"
