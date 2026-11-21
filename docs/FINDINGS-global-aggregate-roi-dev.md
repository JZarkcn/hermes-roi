# Findings — global aggregate data layer (from roi-dev, FYI)

Date: 2026-11-02 (UTC+08). Source: read-only probes against the **live** host
`~/.hermes` (all 9 `state.db`), run from the `roi-dev` profile. This is a
supplement to `PROGRESS.md` / `DATA_CONTRACT.md` §9, not a replacement.

Scope of this note: everything I re-verified for the **machine-global**
aggregate scope (product decision #1: ROI reads ALL profiles, not the active
one). Items `DATA_CONTRACT.md` already answered with evidence are NOT repeated
here — only the deltas and the live acceptance numbers.

## 1. The global scope is feasible and already half-built

`roi/activity_reader.py` (working tree, uncommitted) already carries the data
model for global: `Summary.profile_name` documents `"all" for a machine-global
aggregate` and `Summary.profiles` is `list[str]` ("the included list for a
global scope"). What is **not** there yet: `summarize()` (line ~280) still opens
exactly one `db_path(hermes_root, profile_name)` per call — there is no
cross-db enumeration/loop. The global path is a thin orchestration over the
existing single-profile `summarize()` (or a shared row iterator): enumerate
`<root>/state.db` + `<root>/profiles/*/state.db`, fold each into one `Summary`
with `profile_name="all"` and `profiles=[<each>]`.

No new table, no new column, no new access mode is required. `mode=ro` per-db
is unchanged.

## 2. Live host profile inventory (acceptance numbers for global)

Nine stores on this machine, **all schema v32, all 65 `sessions` columns,
identical column SETS** (verified via `PRAGMA table_info` set comparison —
three stores have a different *physical column order*, but `set` equality
holds, so `_probe_schema`'s set-based required/optional check is unaffected):

| profile | db bytes | sessions | note |
|---|---:|---:|---|
| default | 152,051,712 | 211 | the machine's main profile |
| vog-kb | 36,253,696 | 7 | |
| archiver | 14,524,416 | 5 | |
| roi-dev | 8,736,768 | 5 | (was 4 at probe start; grew under WAL live writes — expected) |
| life | 7,073,792 | 6 | |
| job-hunt | 6,770,688 | 7 | |
| deepseek | 1,179,648 | 2 | column order differs (set identical) |
| whatsapp-bot | 475,136 | 2 | |
| jev-local-executor | 397,312 | **0** | empty store — must be a valid "no sessions" input, not an error |

Global rollup (full history, `sessions` counters, no range filter):
**244 sessions, 9,498 messages, input 69,311,964 / output 8,178,932 /
cache_read 600,511,872 / cache_write 0 / reasoning 4,893,701 / tool_calls
4,954 / api_calls 8,257.** Five-bucket `total_tokens` = 682,896,469;
`wire_total_tokens` (five-bucket minus reasoning, per contract §3) =
678,002,768.

These are the numbers a correct global `summarize(root, "all")` must reproduce
on this host. Treat as a fixture for the global acceptance test (note: they
drift under live writes, so pin the test to a `[since,until)` window, not
full-history, to be deterministic).

## 3. Schema is UNIFORM — do not build version-drift handling

I initially suspected per-profile schema drift (the `PRAGMA table_info` output
looked differently ordered). It does not exist on this host: every store
reports `MAX(version)=32`, exactly one `v32` row, and an identical 65-column
`sessions` set. **Do not** add a per-profile schema-negotiation branch on the
strength of this machine. `DATA_CONTRACT.md` §12 (one version, probe columns)
already covers the real risk (future versions), and it is sufficient.

## 4. `profile_name` is self-describing and reliable for the global rollup

`SELECT DISTINCT profile_name FROM sessions` returns the profile's own name in
every store: default's store says `default`, roi-dev's says `roi-dev`, etc.
This is a redundant-but-correct label (matches the directory name). For the
global `profiles=[...]` list in `Summary`, prefer deriving the name from the
**directory** (`<root>` → `"default"`, `<root>/profiles/<name>` → `<name>`),
and use the in-row `profile_name` only as a cross-check / audit note when it
disagrees. Never trust the in-row label as the sole source — a copy of a store
could carry a stale label.

## 5. The `jev-local-executor` empty store is the global path's edge case

One store has 0 sessions. The global loop must treat "store opened, schema
valid, zero rows in range" as a valid contribution (adds nothing, appears in
`profiles` with a 0-count day), **not** as an error. This is the direct
analogue of the single-profile "no sessions in range (empty state, not an
error)" audit note in `summarize()`, now at the store level.

## 6. Activity-plugin cross-profile visibility (context for T03 mount)

While working in `roi-dev` I made `hermes-activity` visible to every profile by
symlinking `profiles/<name>/plugins/hermes-activity -> ~/.hermes/plugins/hermes-activity`
and adding `hermes-activity` to each profile's `config.yaml` `plugins.enabled`.
Relevant to T03's desktop-mount question (`DATA_CONTRACT.md` §9 item 3): the
desktop page's `cli.exec` shells out per-profile, so a plugin's *visibility* is
per-profile while its *data* can be global. If the ROI desktop page needs to be
reachable from every profile's window (so the global dashboard is always
available regardless of which profile's session is focused), the same symlink
pattern makes the ROI plugin loadable in each profile's gateway process. The
global **data** still comes from the collector's cross-db enumeration, not from
the plugin being "in" each profile. This is a packaging/visibility concern,
separate from the read-only data contract — flagging it so T03 doesn't
conflate "plugin must be installed per profile to be visible" with "plugin must
read per profile to be global" (it only needs the former).

## 7. What I did NOT touch

- Did not modify `roi/activity_reader.py`, `dashboard/`, `desktop/`, or any
  committed ROI file — read only.
- Did not write to any `state.db` (all probes were `?mode=ro` SELECTs).
- The only changes I made were to the **installed `hermes-activity`** plugin
  (the §6 symlinks + `plugins.enabled` entries) to fix its profile
  self-adaptation, which was approved separately from the ROI work.

## Suggested next step for the main session (FYI, not a directive)

Add `summarize_all(hermes_root, since, until, allowlist)` (or a
`profile_name="all"` branch in `summarize`) that enumerates the stores in §2,
folds them into one `Summary(profile_name="all", profiles=[...])`, carries the
§5 empty-store and §4 label-cross-check audit notes, and is covered by a test
pinned to a fixed epoch window so the live-host numbers in §2 stay a valid
acceptance oracle. The single-profile contract stays as the primitive; global
is orchestration over it.
