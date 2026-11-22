# PROGRESS — hermes-roi

## 2026-11-06 — SmallPrint removal + marketplace/portability audit (closed 2026-11-21)
- Removed the `Small print` card from `desktop/plugin.js` (owner: 「small print栏目没啥用，删除」): function, call site, `DetailRow`, `details/detailRow/detailKey` styles, dead `ticked` local. Header comment updated. `unknown` state copy fixed: Option B made `<30 days` provisional, so `unknown` now only means *no usage* — new text 「no usage recorded yet — feed it tokens」. Verified: `node --check` OK, 138/138 tests OK (re-verified 2026-11-21).
- Marketplace research (local source `~/.hermes/hermes-agent`): curated catalog = `plugin-catalog/` in-repo directory, one YAML per entry, pinned to a full 40-char commit SHA, admission ONLY via human-merged PR to hermes-agent (no self-serve). Users CAN already install via `hermes plugins install <owner/repo | git-url>` before catalog admission. `hermes plugins validate` on this repo: **all checks pass** (manifest, requires_hermes >=0.21.7, loadable, security scan safe, no core override, desktop surface inside SDK).
- Cross-host portability (runtime code): collector resolves profiles via explicit (root, name) — never process HOME; root via core `get_default_hermes_root()`; stdlib-only; SQLite `mode=ro`; frontend uses SDK REST only. Open risk: repo also contains dev-only `scripts/` + `docs/` with this-machine paths and an `.env` read — must be OUT of the public/published repo (reviewer rule 11).
- INCIDENCE: host-simulation smoke test (fake HERMES_HOME + fixture state.db + real backend mount) BUNDLED a heredoc script in one terminal call → smart-approval gate BLOCKED it after owner absent 5 min (2026-11-06 ~late session, no consent). Per policy: no retry, no rephrasing. Needs owner approval to run the simulation; commit of the SmallPrint work was in the same blocked bundle and still needs to be re-run with approval.
- CLOSE-OUT 2026-11-21 (owner approved commit + re-run + install-to-app, desktop chat): ran the saved `dev/harness/gen_sample.py` as a file (no heredoc) → host simulation OK against a fake `HERMES_TEST_ROOT` store: 1014 fixture sessions, verdict LV4, break-even ok 2099-06-20 (pace 0.184013/day, 347 curve points, energy monthly-estimate applied). Visual harness (`python3 -m http.server 8877`, dev/harness README steps): full view + `?onboard=1` verified in a real browser — renders clean, NO `Small print` text anywhere, LV4 chip + live countdown + 3dp recovery (2.441%) + tier ladder + chart + machine-wide usage present; onboard view shows the settings form + hint + usage, no errors. Work then committed and the artifact installed to the app (hashes recorded below). — hermes-roi
- CLOSE-OUT hashes (2026-11-21): commit `ae5c7ab` (refactor(page): remove Small print card). Artifact sha256 `637750c4164f846e…a8d756b`; installed `~/.hermes/plugins/hermes-roi/desktop/plugin.js` AND app-root copy `~/.hermes/desktop-plugins/hermes-roi/plugin.js` both byte-identical to it. App-root re-synced by Electron's reconcile pass (marker `sourceMtimeMs` refreshed 1795237451530). Caveat learned: the app-root copy only re-syncs when a reconcile runs (renderer root-resolution / Plugins-tab reload / directory-watch event on the root) — a manually-updated installed package does NOT hot-sync on its own.

Durable work journal. One entry per completed ticket; newest last.
Template: see AGENTS.md "Progress entry template".

---

## Entry 2026-11-01 (UTC+08)

Date/time: 2026-11-01 22:50 – 23:55 (UTC+08)
Ticket: **P0/T01** (repo + reference inventory) and **P0/T02** (data audit +
read-only collector smoke test)
Current phase: P0 — Initialize, research, and verify (2 of ~8 checklist items
complete: repo created, versions recorded; data audit done; remaining P0
items: toy SDK page / backend mount = T03, Home Dashboard registry inspection
= P3-prep, partially done in §9 below)

Evidence inspected:
- Hermes v0.22.5 stable, git commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e`,
  install `~/.hermes/hermes-agent` (git), Python 3.14.9.
- `hermes-activity` v0.2.2, commit `0335e954b3ab00193720205fcdab7e10ae1194f9`,
  MIT — `activity_data.py`, `commands.py`, `src/sdk.d.ts`, `plugin.yaml`,
  build chain (`package.json`/`tsconfig.json`).
- Core sources (installed copy): `agent/usage_pricing.py` (`CanonicalUsage`,
  `normalize_usage`, provider usage shapes), `hermes_state_usage.py`
  (counter write paths, `session_model_usage` upsert, first-accounted-route
  rule), `hermes_constants.py` (`get_hermes_home`, issue #18594 fallback
  warning, `named_profile_home`/`profile_name_for_home`),
  `gateway/session_usage.py`, `agent/codex_runtime.py`.
- Live default-profile `state.db` (150 MB, schema v32, 205 sessions at audit
  time, 2026-09-30 → 2026-11-01): full `sessions` DDL (65 columns) +
  `session_model_usage` DDL; sanitized distributions of
  `billing_provider` × `billing_base_url` × `billing_mode`, `source`, model,
  `cost_status`; 159/159 exact match between `sessions` counters and
  per-call `session_model_usage` (task='') rows; 47 subagent rows across 7
  parents; 45 zero-token placeholder sessions; live writes observed during
  the audit (WAL concurrent read verified safe under `mode=ro`).
- Official docs (fetched 2026-11-01): desktop-plugin-sdk, profiles.
- Installed `home-dashboard` 1.5.0: fixed widget set
  (`ascii, clock, gateway, tokens, host, matrix, sessions, cron, errors`),
  built frontend only → **no verified third-party widget registration API**;
  P3 must go via the upstream source repo.

Files changed:
- `AGENTS.md`, `ROI_DEVELOPMENT_PLAN.md` — from starter kit (repo root).
- `docs/REFERENCES.md` — T01 reference inventory (exact versions/commits).
- `docs/DATA_CONTRACT.md` — T02 data contract; all 10 P0 audit questions
  answered with evidence (see its §1–§13).
- `roi/activity_reader.py` — minimal read-only collector: profile home
  resolution (explicit `(root, name)`, traversal-safe, identity markers),
  `mode=ro` connect, required/optional column probing, `collect()` with
  `[since, until)` epoch ranges, typed `UsageRecord` (5 disjoint buckets,
  `total_tokens` vs `wire_total_tokens`), route classification
  (base_url/provider-based; model names never decide), model allowlist
  filter, totals.
- `tests/fixtures/build_fixture.py` — deterministic synthetic fixture
  builder (11 sessions incl. the cloud-served-local-name trap, parent/child,
  mid-session switch, zero-token placeholder, reasoning, boundaries).
- `tests/fixtures/fixture_sessions.json` — sanitized sample dataset,
  clearly labeled SYNTHETIC.
- `tests/test_activity_reader.py` — 26 tests, stdlib `unittest` only.
- `.gitignore`.

Commands executed + results:
- `python3 -m unittest discover -s tests -v` → **Ran 26 tests in 0.019s — OK**
  (all pass; includes `test_cross_profile_read_only` which opened the real
  default-profile `state.db` from a process with a different `HERMES_HOME`,
  read the last 24 h read-only, and verified writes are refused).
- Read-only live queries (SELECT only, `?mode=ro`): schema dump,
  distributions, parity checks — outputs cited above; no writes performed.

What remains uncertain (carried into P1):
1. Anthropic `output_tokens` includes extended-thinking tokens — ASSUMED from
   provider docs; needs citation before any "bill reasoning separately"
   option for Anthropic routes (DATA_CONTRACT §13).
2. Desktop plugin backend mount context (which profile's gateway process
   serves `/api/plugins/<id>/`) — re-verify at T03 when the real
   `dashboard/plugin_api.py` mounts; collector's explicit `(root, profile)`
   contract already makes it safe either way.
3. Remote profile access path (`host.requestProfile` vs remote CLI) —
   out of MVP; picker must disable `mode: "remote"` routes.
4. `session_model_usage` is required for correct per-model pricing of
   mixed-route sessions (DATA_CONTRACT §7); P1 pricing must read it.

Commit: see `git log` (two commits: T01 scaffold + T02 collector/contract).

Next ticket: **T03** — minimal standalone Desktop plugin registration
(`plugin.yaml` + `desktop/plugin.js` toy page + `dashboard/manifest.json` /
`plugin_api.py` returning a read-only `/summary` from the collector) with a
visible native page and a log-free UI smoke test. Verify the backend mount
lifecycle against the installed v0.22.5 first (see uncertainty #2).

---

## Entry 2026-11-02 (UTC+08)

Date/time: 2026-11-02 ~00:20 – 01:30 (UTC+08)
Ticket: **P0/T03** (minimal desktop plugin + read-only `/summary` backend +
installed preview, ready for the owner's one-command gateway restart)
Current phase: P0 — T03 code **done and committed**; live mount pending the
owner-run gateway restart (D-010/D-014).

Owner decisions absorbed this round (all logged in `docs/DECISIONS.md`):
- **D-001** ROI is machine-global — the page must never follow the active
  profile tab.
- **D-002** "Local" = user-ticked multi-select of models (current +
  historical; LAN IP / proxy / docker deployments); loopback demoted to a
  candidate hint.
- **D-003** Fast usable preview; agent autonomy granted; ALL decisions
  (owner's + agent's) logged with time / consideration / decision /
  decision-maker. → `docs/DECISIONS.md` created.
- **D-004** Cronjob authorized for progress monitoring.
- **D-005** Access granted (later extended: explicit install + restart
  authorization, 2026-11-02).

Evidence inspected:
- Desktop Plugin SDK docs (re-fetched 2026-11-02): unified-package layout
  `~/.hermes/plugins/<id>/{dashboard,desktop}`; `ctx.rest<T>(path, opts?)` →
  `/api/plugins/<id>` (profile-aware, rejects traversal); `ctx.storage`
  plugin-namespaced; only importable specifiers
  `@hermes/plugin-sdk` / `react` / `react/jsx-runtime`; `--ui-*` theme
  tokens; Python backend gated by `plugins.enabled` + gateway restart.
- Installed `home-dashboard` desktop bundle: plugin `id` == dashboard
  `manifest.json` name → confirms the `ctx.rest` scoping contract.
- Live gateway topology: ONE default-profile multiplexer (single PID) for
  all 9 profiles; listeners `:8642` (Tailscale) / `:57399` (local API,
  per-connection token gate — `API_SERVER_KEY` is NOT the gate for
  `/api/plugins/`); `Plugin <id>:` load lines in `~/.hermes/logs/gateway.log`
  — **ERRATUM 2026-11-02 07:1x (D-015): refuted** — v0.22.5 logs nothing on
  successful plugin load, and the backend mounts lazily on the first desktop
  request; replaced by the 3-state model (discovery / freshness /
  error-log), see DATA_CONTRACT §9b.
- Gateway lifecycle guard source (`cron/lifecycle_guard.py`,
  `tools/code_execution_tool.py`, `tools/terminal_tool.py`): agent-side
  restart hard-blocked at 3 layers; `launchctl submit/bootstrap`
  label-independent; referenced scripts scanned; hazard = SIGTERM-respawn
  loop (#62891/#80260/#87033).
- `docs/FINDINGS-global-aggregate-roi-dev.md` (prior roi-dev session): 9
  live stores, all v32, one empty store (`jev-local-executor`), full-history
  rollup numbers — used as the global acceptance oracle.

Files changed:
- `plugin.yaml` — agent-plugin manifest (v2, requires_hermes >=0.21.7).
- `dashboard/manifest.json` + `dashboard/plugin_api.py` — read-only backend:
  `GET /health`, `GET /summary` (scope=all default; days/since/until;
  `local_models` CSV), `CONTRACT_VERSION=0`; `hermes_root()` via
  `get_default_hermes_root()` with `HERMES_TEST_ROOT` test hook; fastapi
  import guarded so the endpoints unit-test standalone.
- `desktop/plugin.js` — native page (hand-written ESM, no JSX): global hero
  (all-profiles scope), 5-bucket totals, local/unknown counts, daily list
  (last 7), audit notes; tick-list read from `ctx.storage.local_models`;
  `--ui-*` theme tokens with fallbacks.
- `scripts/install-local.mjs` — host-scope unified-package installer
  (recovers the machine root from a profile `HERMES_HOME`; `--profile`
  fallback; `--enable`); `scripts/progress-monitor.sh` — the monitor behind
  the cronjob (git / tests / selftest / install / config / gateway-log
  mount evidence; exit 0=OK).
- `roi/activity_reader.py` — `Summary.profiles`; `_accumulate()` extracted;
  `iter_profiles()`; `summarize_global()` (per-store `mode=ro`, day-bucket
  merge, per-profile audit prefixes, max schema version).
- `tests/test_activity_reader.py` — +`GlobalAggregateTest` (5 tests:
  enumeration, cross-store sums, allowlist-per-profile, empty range, no
  stores) and +`LiveGlobalSmokeTest` (live host: all 9 stores read
  read-only, writes refused). `tests/test_plugin_api.py` — 10 endpoint
  tests (default global scope, single-profile scope, `local_models`
  declaration semantics, calendar-day window, content-leak, 400/404).
- `docs/DECISIONS.md` (new — 14 decisions); `docs/DATA_CONTRACT.md` (§6
  amended per D-002; §9a global scope; §9b live mount facts; §14
  cross-reference); `docs/FINDINGS-global-aggregate-roi-dev.md` (committed
  from the working tree).

Commands executed + results:
- `python3 -m unittest discover -s tests` → **Ran 32 tests in 0.151s — OK**
  (includes `LiveGlobalSmokeTest` on the live host: 9 stores enumerated,
  all read `mode=ro`, UPDATE refused).
- `python3 roi/activity_reader.py` → selftest `{"ok": true}`.
- `node --check desktop/plugin.js` → SYNTAX OK.
- `node scripts/install-local.mjs` → installed into
  `~/.hermes/plugins/hermes-roi/` (host scope; a stray profile-scope copy
  made by an earlier script version was removed).
- `hermes --profile default config set plugins.enabled "[<9 existing>,
  hermes-roi]"` → `config get` verified: 10 entries incl. `hermes-roi`.
  (Official CLI path per the never-hand-edit-config rule.)
- `bash scripts/progress-monitor.sh` dry runs: pre-install ATTENTION
  (expected); post-install+enable OK with backend "pending" (expected until
  restart).
- cronjob created: `5649fd37efaf` `roi-progress-monitor`, every 30m,
  terminal-only toolset, continuity on, delivers to this chat;
  `gateway_running: true` at creation.

Remaining / handoff (the ONLY blocker):
- **Owner step:** from a separate terminal (outside the gateway):
  `hermes --profile default gateway restart`. The ROI page (sidebar "ROI",
  route `/roi`) then renders live machine-global data. Agent-side restart
  is hard-blocked and was deliberately not bypassed (D-014).
- Verification after restart: cronjob reports mount evidence within 30m;
  instant check `bash scripts/progress-monitor.sh`. If the backend does not
  mount, D-011 fallback: install `--profile roi-dev` + enable in that
  profile's config.

Next ticket: **P1/T04 — pricing layer**: price snapshots (Decimal,
per-bucket, FX), per-model rows from `session_model_usage` for mixed-route
sessions, hero recovery % at exactly 3 decimals
(`100 × net_savings / hardware_cost`), trailing-30-day break-even
projection, the four-level verdict. P2: settings page (hardware cost,
start_at, local-model tick UI over historical models).

### Addendum 2026-11-02 (T03.1, 07:44–08:00) — sidebar row absent after restart

- Owner restarted the gateway (new start 07:42:19; monitor flipped to
  `backend: ready`). The ROI sidebar row did NOT appear.
- Diagnosis (D-016): NOT a bundle bug, NOT a restart problem. Electron
  materialized the desktop half (`~/.hermes/desktop-plugins/hermes-roi/`,
  marker stamped 07:43) but the loader loads marked unified-package halves
  **opt-in** (`runtime-loader.ts:924`, GHSA-mcfc-hp25-cjv7 posture): no
  user decision in the desktop's `pluginDecisions.v2` → inventoried as
  disabled, no nav row. `desktop.log` has zero hermes-roi lines (never
  loaded, no error). All four SDK import names verified in
  `apps/desktop/src/sdk/index.ts`.
- Fix: owner toggles **ROI** ON on the Desktop Plugins settings page (live
  toggle, app-level). Import path to the backend pre-verified
  (`sys.path` insert in `plugin_api.py`; stdlib-only `roi` package;
  fastapi in gateway venv).
- In parallel: T04 pure economics layer (pricing + verdict) delegated to a
  subagent (deleg_13eaa5c5) — new files only, zero overlap with T03.1.

### Entry 2026-11-02 (T04a, 07:47–08:10) — pure economics layer

Ticket: **P1/T04a** (pure pricing + verdict layer). T04b wiring deferred —
see D-017 (blocked on the owner's price-card decision).
Deliverable (subagent deleg_13eaa5c5; verified by the orchestrator, not
self-report):
- `roi/pricing.py` (306 lines): `BUCKETS` (5 disjoint), `BucketPrices`,
  `PriceSnapshot` (single currency + as_of date; FX out of scope),
  `compute_cost` (exact int×Decimal products, ONE /1e6 at the end, 6dp
  `ROUND_HALF_UP`), `price_model_usage` → `CostBreakdown`
  (`UnknownPrice` singleton — never a silent 0.0; coverage accounting;
  floats refused; unknown/negative bucket keys raise).
- `roi/verdict.py` (440 lines): `recovery_pct` (100×net/hw, EXACTLY 3dp
  `ROUND_HALF_UP`), `net_roi_pct` (100×(net−hw)/hw), `format_percent`
  (3dp, −0.000 normalized), `project_break_even` (trailing 30 CALENDAR
  days incl. zero-usage days; exact Decimal `divmod` day math; states
  ok / already_paid_off / no_positive_pace / unknown), `make_verdict`
  (LV1 net≥hw inclusive; LV2 ≤90 days; LV3 ≤1825 days; LV4 >1825 or
  pace≤0; unknown onboarding is a state, NOT a tier; tz-aware only).
- Tests: +44 (`tests/test_pricing.py` 18, `tests/test_verdict.py` 26) —
  boundary pins (day 90 → LV2, day 1825 → LV3, net==hw → LV1,
  12.3455→12.346 HALF_UP), UTC+8 day-boundary case, cache-heavy mix,
  unknown-model coverage, empty history → unknown, float refusal.
Evidence (orchestrator re-run):
- `python3 -m unittest discover -s tests` → **Ran 76 tests — OK**
  (32 pre-existing + 44 new).
- `python3 roi/pricing.py` / `python3 roi/verdict.py` selftests →
  `{"ok": true}`.
- `git status` → exactly 4 new untracked files; zero existing files
  modified.
- Code review of both modules against the fixed product rules (formulas,
  tier boundaries, rounding, timezone, float-free money path,
  no-double-count rule vs DATA_CONTRACT §3/§3.3): all conforming.
Handoff: T04b wiring (per-model DB rows → `/summary` economics → page
hero) starts when the owner answers the price-card source question
(D-017). The v1 page remains the usable preview meanwhile.

---

## Entry 2026-11-02 (UTC+08) — T04b-data

Date/time: 2026-11-02 ~09:10–09:40 (UTC+08)
Ticket: **P1/T04b-data** (price card + FX + energy modules — the
T04b wiring's data layer; all financial definitions closed by the
owner this morning: #1–#5 answered, option A approved, sub-decisions
approved → D-018 ~ D-022)
Current phase: P1 — T04b half done (data layer shipped; `/summary`
economics + page hero/verdict UI remain)

Implementation:
- `roi/price_cards/deepseek.json` — committed DeepSeek rate card:
  official USD values verified 2026-11-02 from
  `api-docs.deepseek.com/quick_start/pricing/` (flash/pro,
  peak+off-peak for input/cache_read/output; cache_write & reasoning
  = 0 with documented reasons; bucket mapping to the collector's
  disjoint buckets; peak rule text; default benchmark =
  deepseek-flash; refresh = manual re-fetch + commit).
- `roi/price_cards/fx-xe.json` — committed Xe mid-market snapshot
  (fetched 2026-11-02 from xe.com converter pages): CNY 6.64910834,
  EUR 0.89194653, GBP 0.74534421, CHF 0.819842, ZAR 16.6402 per USD.
  Real fetched values, as-of dated, source-stamped.
- `roi/cards.py` — `load_card(path=None, basis="peak") -> Card`:
  strict loader (decimal strings only, floats/bools/negatives/missing
  buckets/bad default model/bad as_of all raise `CardError`);
  returns one `PriceSnapshot` for the chosen basis + raw JSON for
  audit/P2. No network.
- `roi/fx.py` — `load_fx_table()` + `to_usd(amount, ccy, table)`:
  1 USD = rate quote convention (CNY→USD DIVIDES), USD passthrough,
  unknown currency raises (never assumed 1:1), Decimal-only.
- `roi/energy.py` — optional D-020 model: `energy_cost(price, kwh)`
  exact ×, `net_savings(gross, energy=None)` (None = "not modeled" →
  gross; negative net allowed and honest).

Verification:
- `python3 -m unittest discover -s tests` → **Ran 113 tests — OK**
  (76 pre-existing + 37 new: test_cards 15, test_fx 14, test_energy 8).
  Pins the exact card rates, off-peak basis, Xe rates, division
  direction (100 CNY → 15.039625... USD), unknown-currency loud
  failure, float refusal everywhere, negative-net honesty.
- One test written against a guessed `CostBreakdown` shape
  (`priced is None` for unknown models) failed immediately; corrected
  to the actual verified contract (priced is always Decimal; unknown
  tokens carried in `unknown_tokens`/`unknown_models`) — "inspect
  before asserting" held.

State / next:
- The installed copy at `~/.hermes/plugins/hermes-roi/` is now stale
  relative to the repo (no pricing/verdict/cards/fx/energy). That is
  expected: nothing serves them yet. The NEXT ticket (T04b-wire)
  re-runs `scripts/install-local.mjs` after wiring `/summary`
  economics + the page hero/verdict UI, then owner re-opens the
  desktop opt-in if needed.
- T04b-wire: per-model rows → `price_model_usage` with the card
  snapshot (default model deepseek-flash, peak basis) → FX to USD →
  optional energy subtraction → verdict via `roi/verdict` →
  `/summary` extension (typed JSON) → page hero (3dp recovery %) +
  four-tier verdict + unknown-onboarding state (D-022 option A).

---

## Entry 2026-11-04 (UTC+08) — T03.2 packaging fix (missing __init__.py) + monitor erratum

Date/time: 2026-11-04 ~14:30–15:00 (UTC+08)
Ticket: **T03.2** (root-cause fix for the 2-day monitor ATTENTION loop;
D-023)
Current phase: P1 — T04b-data done; T04b-wire next (after the running
gateway picks up the fixed host copy)

Problem: monitor flagged MOUNT ERROR for ~2 days on
`No __init__.py in .../profiles/{housing*,}/plugins/hermes-roi`
lines. Standing theory: stale per-profile copies need owner cleanup.

Investigation (all verified from source/logs, not assumed):
- v0.22.5 `plugins_loader.py:814-816`: directory plugins REQUIRE a
  top-level `__init__.py` + `register(ctx)`. hermes-roi had none in
  the repo OR the installer copy list → every copy (host included)
  was unloadable. default/roi-dev had no error line only because no
  gateway of theirs had scanned the host copy (lazy mount, D-015).
- Reference: hermes-activity ships `__init__.py` + `register`;
  home-dashboard needs none (layout.json-only path).
- housing profiles do NOT list hermes-roi in plugins.enabled — their
  copies trigger directory-plugin load only (log noise, no backend).
- Backend lazy-mount source confirmed (`web_server_plugin_profiles.py:
  68-78`): profile's own plugins/ + host `~/.hermes/plugins/` — the
  Electron `desktop-plugins/` dir holds only the frontend plugin.js.
  So the host copy is authoritative for the backend.

Fix (all in the authorized repo; reinstalled to host):
- `__init__.py` at repo root: docstring + intentional no-op
  `register(ctx)` (v1 surface = lazy dashboard backend).
- `scripts/install-local.mjs`: copies `__init__.py` (was missing from
  the item list).
- `tests/test_packaging.py` (3 tests): presence, import + callable
  register, register is a true no-op (stub ctx raises on any touch).
- `scripts/progress-monitor.sh`: §4 flags a missing installed
  `__init__.py`; §5 error grep time-floored at max(last gateway
  start, install mtime) — the ungated grep re-raised days-old lines
  every tick (erratum).

Verification:
- `python3 -m unittest discover -s tests` → **116/116 OK**
  (113 + 3 packaging).
- Host reinstalled; installed copy has `__init__.py` + full `roi/`
  (pricing/verdict/cards/fx/energy/price_cards).
- Loader simulation on the INSTALLED copy with exact v0.22.5 mechanics
  (namespace pkg + spec_from_file_location +
  submodule_search_locations) → imports as `hermes_plugins.hermes_roi`,
  register clean. OK.
- Monitor re-run → `STATUS: OK`; backend = PENDING RESTART (honest:
  gateway started before the new install).

Residual / next:
- Owner cleanup (other profiles, D-010/D-014): `profiles/housing` and
  `profiles/housing-agent` hold pre-fix copies (not in their
  plugins.enabled). Delete, or `node scripts/install-local.mjs
  --profile <name>`.
- Owner: `hermes --profile default gateway restart`, then open the
  desktop Plugins opt-in (D-016) → /roi page.
- T04b-wire (economics in /summary + hero/verdict UI) unblocked;
  remains the next build ticket.

Addendum 2026-11-04 ~15:20: owner instructed to fix the housing
copies ("先修复 #2"). Agent re-synced (not deleted) `profiles/housing`
and `profiles/housing-agent` via `node scripts/install-local.mjs
--profile <name>` (no --enable — their configs untouched). Both copies
now have the top-level `__init__.py` + full roi/ (incl. price_cards)
and pass the v0.22.5 loader simulation. Only the owner-run gateway
restart remains before the /roi page can be opened.

---

## Entry 2026-11-04 (UTC+08) — T04b-wire

Date/time: 2026-11-04 23:35 – 00:20 (UTC+08)
Ticket: **P1/T04b-wire** (economics endpoint + page hero/verdict UI)

Context: owner restarted the default gateway at 23:30:03 — post-restart
log has zero hermes-roi error lines, host copy clean, monitor
`backend: ready`. Owner then instructed "继续".

Implementation:
- `dashboard/plugin_api.py`: new `GET /economics` endpoint (kept
  separate from `/summary` — daily-aggregation contract stays
  untouched). Params: scope (all|profile), hardware_cost (Decimal,
  >0), start_at (effective start, date or ISO), tz, benchmark
  (default: card's default_benchmark_model = deepseek-flash), basis
  (default peak, D-022), local_models ticks, energy_price +
  energy_kwh (+ optional energy_ccy, both-or-neither).
  Pipeline: `load_price_card` → `price_model_usage` per local session
  (allowlist + URL/provider rules — a tick alone makes it local,
  D-018) → FX to USD when needed (missing rate = 500, never assume
  1:1) → `energy_cost` flat offset → `project_break_even` (trailing
  30 calendar days, start-anchored, unknown <30 days = option A,
  D-022) → `make_verdict` (LV1–LV4 + unknown). Response: all money
  as 6dp decimal strings, recovery/net-ROI as 3dp strings (hard
  product rule), tier/label/reason, break-even state (ok /
  already_paid_off / no_positive_pace / unknown) + ISO date +
  days_remaining, benchmark + card_as_of + fx + energy echo,
  coverage counters.
- `desktop/plugin.js`: persisted hardware settings row (cost /
  start date / benchmark / $/kWh / kWh via the SDK storage),
  second useQuery for /economics (no-op until both cost + start are
  filled), EconBlock: 3dp recovery hero, verdict card (tier +
  sarcastic label + reason + break-even line when finite),
  gross/energy/benchmark/coverage detail card; footer now says
  "cloud-equivalent estimate — hypothetical, never money earned".

Verification:
- `tests/test_economics.py` (15 tests, deterministic 2-session store:
  1M in + 1M out local @ T0 → exactly $1.500000 at flash peak,
  hand-computed): gross/net/coverage, LV1 paid-off, LV4 no-pace,
  strict unknown onboarding (D-022 A), off-peak basis ($0.750000),
  energy offset (net 1.5−1.0=0.5 → 33.333%), allowlist
  cloud-lookalike (1.500270 incl. 100 output tokens), global scope,
  8 parameter-error cases (400/404). One initial test annotation was
  wrong (forgot the cloud session's output tokens) — fixed the TEST,
  code was right.
- `python3 -m unittest discover -s tests` → **131/131 OK**.
- `node --check` on the frontend (ESM copy) → syntax OK.

Residual / next:
- Live acceptance: in the DEFAULT profile the page renders (owner
  confirmed 2026-11-05 ~01:15). In the ROI-DEV profile the same page
  404'd — root cause: the /api/plugins/<name>/ lazy mount is
  per-profile: the backend serves a profile's scope only when the
  plugin is (a) present in that profile's own plugins/ dir AND
  (b) in that profile's plugins.enabled. default had both; roi-dev
  had neither (its dir is profiles/roi-dev/plugins/, separate from
  the host ~/.hermes/plugins/). Fix (agent, owner-scope config):
  `node scripts/install-local.mjs --profile roi-dev` +
  `hermes --profile roi-dev plugins enable hermes-roi` — the CLI
  rewire hot-loaded the plugin in the RUNNING gateway ("Gateway
  reloaded plugins; nothing needs a session or restart"); roi-dev
  scope plugin row verified enabled, error=None. Consequence for
  future installs: the roi-dev profile copy must be re-synced on
  every code change, alongside the host copy.
- P2: local-model tick UI (currently fed from storage key
  local_models, read defensively), price-card refresh workflow.

---

## Entry 2026-11-05 (UTC+08) — design pass + UX fixes + all-profile rollout

Date/time: 2026-11-05 01:35 – 02:10 (UTC+08)
Ticket: owner feedback on the live page (6 items) — see decisions below.

Owner feedback (verbatim, 2026-11-05 ~01:30):
1. "计算 roi based on 机器价格看上去正常"
2. "输入电费，日期也没变，感觉没真正计算"
3. "模型不是下拉菜单，随便输就报错，计算不了"
4. "这个插件只在 default profile 里面工作，我需要它在任何 profile
   里面工作，但是数值只取总数"
5. "我也不知道统计的 token 是不是根据模型统计的，我有一个 profile
   是 deekseek，不知道也算进来没有"
6. "UI 完全没有美感，甚至也没有重点，不知道到底做没做过设计"

Changes:
- #6/#2 page redesign (desktop/plugin.js rewritten, ~20 KB):
  hero-first layout — one hero panel (3dp recovery number 44px,
  verdict chip + sarcastic label + reason + explicit break-even
  STATE line for all four states incl. no_positive_pace / strict
  unknown), math row (gross / energy / net, net in accent),
  "Small print" de-emphasized detail grid (benchmark, card as of,
  FX, applied energy echo `-$X = p $/kWh × k kWh`, coverage, pace
  window), inputs in their own labeled section (label above every
  field; half-set energy fields get an inline yellow warning;
  applied offset echoed below). T03 usage section preserved and
  grouped under "Machine-wide usage — all profiles". Real app
  tokens used: --ui-bg-chrome hero panel, --ui-widget-surface-
  background cards, --ui-stroke-tertiary hairlines, --ui-yellow
  warning, --ui-text-primary/secondary/tertiary scale.
- #3 benchmark is now a <select> fed by /health
  (`benchmark_models` + `benchmark_default`, from the card's model
  list; broken card degrades to None, never 500s the probe) and by
  /economics (`benchmark.options`). No free-typed model name can
  reach the backend anymore.
- #4 all-profile rollout: plugin installed + enabled in ALL 9
  profiles (archiver, deepseek, housing, housing-agent, job-hunt,
  life, roi-dev, vog-kb, whatsapp-bot) via installer --profile +
  `hermes --profile <p> plugins enable` (live rewire, no restart).
  Data stays machine-global (scope=all sums every store) — the
  per-profile plugin presence only makes the backend servable in
  that profile's tab. Future code changes: re-run the installer for
  host + every profile (noted for the install flow).
- #5 per-profile classification scan (read-only, real stores, all
  10 profile stores incl. default): deepseek profile = 2 sessions,
  0 local — both on https://api.deepseek.com/v1 → CLOUD, correctly
  NOT in the local gross (ROI prices what local inference AVOIDED;
  real DeepSeek API spend is not a local save). Machine-wide: 556
  local-candidate sessions (loopback 127.0.0.1:8000 LM Studio);
  988 non-local, of which 922 are legacy rows with NO billing route
  at all (never priced, auditable as unknown) and ~66 are true cloud
  routes (codex x60, deepseek API x5, ...). Tokens are per-session;
  v1 prices every local session
  at ONE benchmark model (deepseek-flash, D-018) — per-model
  pricing stays P2.

Verification:
- `tests/test_economics.py` +2 (health exposes model list;
  economics response carries options) → **132/132 OK**.
- `node --check` (ESM copy) OK.
- All 9 profiles: installer + enable OK; gateway rewire confirmed
  ("Re-wired plugin handlers on 3 adapter(s)").
- Default scope's already-mounted router carries the pre-change
  module: /economics works as before; the /health dropdown options
  appear after the next gateway restart (frontend degrades
  gracefully: select shows "default — deepseek-flash" meanwhile).
- Frontend changes reach the app on next app start or the
  Capabilities→Plugins refresh (Electron materializes the desktop
  half at app start).

Residual / next:
- Owner: re-open the ROI page (app refresh/restart for the new
  layout; optional gateway restart for full backend freshness).
- P2: local-model tick UI, per-model pricing, price-card refresh.

## Entry 2026-11-05 (02:00–03:10, UTC+08) — Design-mockup pass: verdict banner, live countdown, savings chart (AGENT)

Date/time: 2026-11-05 02:00 – 03:10 (UTC+08)
Decisions: agent (overnight autonomy granted 2026-11-02; owner asleep,
explicit "不要问我的意见和 approval. 你先改着, 自己决策")

Owner handed over the original "Proposal v0.1" mockup (dark "ROI /
Return on Intelligence — A brutally honest ROI for your local AI rig",
LV4 sleeping-skull banner, 2044 break-even countdown, cumulative
savings chart, LV1–LV4 ladder) and instructed: iterate on the mockup,
make the UI good and complete the basic functionality first,
extensions later, report in the morning.

Decisions (agent):
- Follow the mockup's copy and layout verbatim (bilingual tier labels,
  roast line, tagline, footer, countdown format).
- Keep USD: the mockup's SGD is a placeholder; the rate card and all
  math are USD (D-018). Multi-currency hardware input = P2.
- Keep App-native --ui-* tokens; "neon" = accent glow on dark chrome
  (low-glare principle), not hardcoded hex.
- Chart is CUMULATIVE NET (energy offset included via the start-day
  negative event already in the stream) so the curve, hero percent and
  break-even date are mutually consistent.
- Projection segment drawn to the break-even date where the curve
  meets the cost line exactly by construction; de-emphasized (faint
  dashed) so actuals stay the subject when the date is far off.

Backend (dashboard/plugin_api.py, roi/verdict.py):
- Verdict copy per mockup: EN punchlines ("PAID OFF. ABSOLUTE
  LEGEND." / "ALMOST THERE." / "STILL A LONG WAY. KEEP GRINDING." /
  "PAYBACK IS A DISTANT DREAM.") + new `label_zh` ("回本遥遥无期！" …) +
  `roast` ("// At this rate, your next GPU will retire first." …).
  Additive Verdict fields (defaults "") — old contract intact.
- New `curve` object on /economics: daily cumulative net from the
  effective start day; linear projection to the break-even date when
  pace > 0; `crossed` = first real day cum-net reached cost; decimated
  to ≤ 500 points; future start date → empty points (frontend
  placeholder).

Frontend (desktop/plugin.js — full v3 rewrite, ~600 lines):
- Verdict banner: tier icons (trophy/rocket/barbell/skull, "z z z" on
  LV4), `[ LV4 · 回本遥遥无期！ ]` chip, 19px EN headline, italic
  roast; tier-colored rail + glow (LV1 green / LV2 cyan / LV3 yellow /
  LV4 purple / unknown muted).
- Panels: HARDWARE RECOVERY (42px 3dp percent, tier-colored,
  "$167.17 / $5,000.00") | PROJECTED BREAK-EVEN (date + LIVE 1/s
  countdown "48 Y 04 MO 03 D 05 H 41 M 06 S" — "MO" kills the M/M
  ambiguity; "REACHED" on paid-off; explicit state lines otherwise).
- Stat strip: Hardware Cost / Cloud-Equivalent / Pace (30d) / Net ROI
  (red when negative). Money 2dp in the UI (display-only; backend
  keeps 6dp strings; small print stays exact).
- CUMULATIVE SAVINGS SVG chart (no library): solid accent actuals,
  faint dashed projection, dashed purple cost line + label, area
  fill, terminal dot, $ y ticks, start/now/end x ticks (edge-safe
  anchors), empty-state placeholder.
- SETTINGS as mockup list rows (cost / start / benchmark select /
  electricity pair) — half-set-energy warning + applied-echo kept.
- Tier ladder (4 cards, active glow, others 40%), header "> ROI /
  Return on Intelligence" + tagline, mockup footer + estimate-only
  disclaimer, T03 usage section preserved verbatim.

Verification:
- 133/133 tests OK. New: bilingual copy on 3 states; curve on
  no-pace / paid-off-crossed / future-start-empty / projected cases
  (endpoint value == hw by construction).
- `node --check` OK.
- VISUAL SMOKE TEST (new this pass): browser harness
  (scratch/roi-harness): local UMD React 18 + @hermes/plugin-sdk stub
  + REAL payloads (actual endpoint functions run against a 1014-session
  deterministic fixture store). Full page rendered with LV4 state:
  banner copy, ticking countdown, 3.343%, $167.17/$5,000.00,
  2075-02-24 + 17644 days, chart shape per mockup (flat actuals, faint
  projection, cost line, 3 x labels), settings rows, LV4 ladder
  highlighted; onboarding state renders primary settings. Two
  vision-review rounds → fixes: chip alignSelf flex-start, M→MO,
  2dp money, projection 0.4 opacity, cost line 1.8px, area 0.14,
  x-label edge anchors.
- Reinstalled all 10 locations (host + 9 profiles); disable→enable
  hot-reload ×10 ("Gateway reloaded plugins; nothing … needs a
  session or restart"); zero hermes-roi errors in the gateway log
  after reload; installed copies spot-checked (_build_curve /
  VerdictBanner present).

Residual / next:
- Owner wakes: ROI page refresh (or app restart) shows v3; backend
  hot — no gateway restart needed this pass.
- Chart area fill is a sliver while gross ≪ cost (mockup same shape);
  grows visible as recovery approaches the cost line.
- P2 extensions (owner: "再说拓展功能"): home-dashboard widget
  (mockup right sidebar), local-model tick UI, per-model pricing,
  multi-currency hardware input.

---

## Entry 2026-11-05 (UTC+08) — electricity → monthly usage estimate

Date/time: 2026-11-05 (post-v3, owner awake). Ticket: **electricity
input re-scope** (owner chat, verbatim): "electricity 的瓦数是日还是周
还是月单位？没有人会统计 cumulative electricity，换成让用户输成月用量
估算。改完自检好，用 computer use 视觉自检，然后汇报。"
Git before: `5cfe6f7` (v3 design pass, clean).

Owner question answered: the old field was a single **cumulative kWh
total** (placeholder literally "kWh") — not watts, not a rate, no time
unit. Nobody tracks that, so it is re-scoped to **kWh / month**.

Changes:
- `roi/verdict.py`: `project_break_even` + `make_verdict` gained
  `recurring_cost_per_day` (default 0). `pace = window_net/30 −
  recurring`; `pace_per_day` is now the **net** pace (recurring=0 ⇒
  byte-identical to legacy, prior tests pass). No-pace + ok notes carry
  the gross−recurring breakdown.
- `dashboard/plugin_api.py`: energy is a monthly estimate. Outer block
  only validates; `_compute` builds `rate USD/mo = price × kWh/mo` (FX'd
  when ccy≠USD), applies the **elapsed** portion (`rate/30 × days`) as a
  start-day flat offset (feeds `total_net`), and passes
  `recurring = rate/30` to both verdict calls so the **future** keeps
  paying electricity. Response `energy` flattened to `{applied, basis,
  price, kwh_per_month, ccy, monthly_usd, per_day_usd, elapsed_days,
  total_applied_usd}`. Added `HERMES_ECON_NOW` determinism seam (else
  `time.time()`).
- `desktop/plugin.js`: placeholder "kWh / mo"; half-set warning + applied
  hint rewritten to the monthly breakdown; footer small-print energy row
  fixed to the new flat fields (the old code read `energy.usd`/
  `energy.input.*` which never existed — a latent "undefined" bug now
  gone).
- `tests/test_economics.py`: `test_energy_offset_subtracts_from_net` →
  `test_energy_monthly_estimate` + new `test_energy_monthly_nets_the_pace`
  (pinned `HERMES_ECON_NOW`; in-window session helper). 997 days WITH
  electricity vs 820 WITHOUT (energy pushes the date LATER).
- `dev/harness/gen_sample.py`: pins `HERMES_ECON_NOW` + prints the energy
  block. `docs/DECISIONS.md`: D-020r.

Verification:
- 134/134 tests OK (was 133; −1 flat-offset, +2 monthly).
- `node --check desktop/plugin.js` OK.
- Computer-use visual self-check: harness render, screenshot, verify the
  "kWh / mo" input + monthly applied-echo + footer energy row (below /
  at install step).

Residual / next:
- Desktop half needs the same-inode `cp -f` into
  `~/.hermes/desktop-plugins/hermes-roi/plugin.js` (app-root, #91503).
- Backend mounted module still PENDING gateway restart (owner-run) to
  serve the new `energy` block + netted pace.

---

## Entry 2026-11-06 (UTC+08)

Date/time: 2026-11-06 (UTC+08)
Ticket: **<30-day history → Option B provisional estimate** (D-025, supersedes
D-022a)

Owner change of mind (re-verified against the session transcript): D-022a
(2026-11-02) had chosen a strict "unknown" wall for <30 days; the owner now
wants the first 30 days to ALSO give an estimate (a provisional pace).

Changes:
- `roi/verdict.py`: `project_break_even` — when `elapsed < 30` AND usage
  exists, compute a provisional pace = cumulative net / (elapsed+1 calendar
  days) instead of returning unknown; `BreakEvenProjection`/`Verdict` gained
  `provisional` + `pace_days`; notes carry a "PROVISIONAL (based on N days)"
  prefix; no-usage is still `unknown`. Module + function docstrings updated.
- `dashboard/plugin_api.py`: `/economics` exposes `break_even.provisional` /
  `break_even.pace_days` + `verdict.provisional`.
- `desktop/plugin.js`: amber "临时估算 · 基于 N 天（满 30 天转正式口径）" badge
  in the verdict hero (next to the tier chip) + "Pace (Nd · 临时)" stat label.
- `tests/test_verdict.py`: `test_insufficient_history_is_unknown` →
  `..._is_provisional` + 4 new pins (divides-by-actual-days,
  no-usage-still-unknown, day-30-boundary-standard, standard-not-provisional).
- `dev/harness/gen_sample.py`: `start_at` overridable via `ROI_SAMPLE_START`
  (exercises the provisional path end-to-end). `dev/harness/index.html`:
  dynamic `import("/plugin.js?bust=")` so the harness never renders a cached
  (stale) frontend module.

Verification:
- 138/138 tests OK (was 134; −1 renamed, +4 new).
- `node --check desktop/plugin.js` OK; verdict selftest OK.
- Harness render of a REAL provisional sample (gen_sample with
  ROI_SAMPLE_START=12d ago, through the actual endpoint): verdict.provisional
  = true, break_even.pace_days = 13, pace $0.082/day, both the hero badge
  ("临时估算 · 基于 13 天") and "PACE (13D · 临时)" render. Screenshot:
  scratch/roi-provisional-badge.png.

Residual / next:
- Backend `/economics` shape changed (new `provisional`/`pace_days` fields) →
  gateway restart (owner-run) to serve the live endpoint; the frontend
  hot-reload picks up the badge regardless (missing field ⇒ falsy ⇒ no badge).


## 2026-11-22 — Manual refresh button on the ROI pane (closed 2026-11-22)
- Owner want: 「我希望把它合入PR,所以刷新需要在其他人的主机上也能工作」 — the click-to-refresh must be part of the plugin itself, not a this-machine dev-dashboard script. Added `⟳ REFRESH` button to the SCOPE header in `desktop/plugin.js`: onClick re-runs the summary (and economics, when configured) queries via `useQuery().refetch()`; `isFetching` drives the 「REFRESHING…」 label + disabled state. Built purely on the public SDK surface (`ctx.rest`, TanStack `useQuery`) — backend recomputes on the spot; no cron, no self-update (rule-3 clean); identical on any host.
- Version bump 0.1.0 → 0.2.0 (`plugin.yaml`, `docs/catalog-entry.draft.yaml`). The catalog PR's entry yaml (fork branch) must get the same version bump + new pinned dist sha when pushed.
- Harness support: `dev/harness/sdk-stub.js` `useQuery` gained `refetch`/`isFetching` (fire-once stub silently swallowed the button); `index.html` ctx.rest now counts calls (`window.__rest_calls`) + 250 ms latency so the refresh state is observable. Remember: harness `plugin.js` is a copy — `cp ../../desktop/plugin.js plugin.js` after edits (README).
- Verified: `python3 -m unittest discover -s tests` → 138/138 OK. Browser (served harness, real Chrome): load → 3 rest calls; one onClick → exactly summary+economics re-run (+2, health untouched), button 「REFRESHING…」 mid-flight → 「⟳ REFRESH」 settled, page intact (screenshot `roi-refresh-button-20261122.png`).
- PITFALL: `python3 -m http.server` sends no Cache-Control → Chrome heuristic-caches `sdk-stub.js`; module-graph debugging must use a fresh query (`?v=N`) or CDP `Network.setCacheDisabled` — a plain reload can keep serving the stale stub. Also: the harness stub returns cached objects from `ctx.rest` (no network per refetch) — fetch-count checks there are meaningless; assert `__rest_calls` instead.
- PENDING (needs owner): re-run `scripts/make-dist.sh` → new dist commit → push `hermes-roi-dist` (deploy key) → update catalog PR branch entry (version 0.2.0 + new sha) — fork push needs a fresh short-lived GitHub token. → **CLOSED 2026-11-22 same day**: dist `5bc901ef879bf34d912957996bc9c4197e11e65c` pushed, validate green, PR branch got version 0.2.0 + that sha (`f2b2945a`), token deleted by owner. See next entry.


## 2026-11-22 — English-first verdict UI (catalog review round 1, closed 2026-11-22)
- Review received: `teknium1` CHANGES_REQUESTED on catalog PR #158530 (reviewed at `5bc901ef`): security read clean (ro-only stores, metadata-only, no network, SDK-only page). Single blocker = **catalog English-first rule**: verdict chip, provisional chip, pace label and tier-ladder rows led with Chinese. Required: English headline everywhere; Chinese may stay as secondary subtitle. Also: catalog YAML version bump to 0.2.0 is *theirs at merge* — our entry keeps `version: "0.1.0"`; they re-pin `sha:` here ourselves after the fix, then comment on the PR.
- Changes (`desktop/plugin.js`, comments in `roi/verdict.py` + plugin.js header): verdict chip now `[ LV4 · PAYBACK IS A DISTANT DREAM. ]` (EN `v.label`); new `S.bannerZh` Chinese subtitle under the EN headline; provisional chip → `Provisional estimate · based on N days (switches to the 30-day basis on day 30)` (chip `whiteSpace` nowrap→normal, EN text is longer); stat label `Pace (Nd · provisional)`; tier ladder rows swapped to EN headline + new `S.tierSub` Chinese secondary (replaces `S.tierEn` slot). Data fields (`label`/`label_zh`/roasts) unchanged — backend contract intact.
- PITFALL: editing the ladder rows — the second child line closes **three** parens (`)));` = row div + flex-col div + map-callback outer h); dropping one passes fuzzy-match but breaks `node --check`. Run `node --check` after every plugin.js patch. Also harness `sample/economics.json` is NOT git-tracked — regenerate via `gen_sample.py` to restore after provisional flips.
- Verified: `node --check` clean; `python3 -m unittest discover -s tests` → 138/138 OK; harness (served :8991, fresh `cp` of plugin.js) DOM-text asserts: chip EN + no Chinese-led chip, banner zh subtitle under EN headline, `PACE (30D)`/`PACE (12D · PROVISIONAL)`, EN provisional chip (flipped fixture), no 临时估算 residue; vision check: chip wraps cleanly, EN-primary/ZH-secondary hierarchy correct in banner + all 4 ladder rows, no overflow/overlap. Fixture restored (provisional=False regenerated).
- Residual / next: new dist commit → push dist → catalog PR entry **revert version to 0.1.0** + re-pin new sha (maintainer bumps version at merge) → PR comment「fix in, sha re-pinned」. Fork push + comment need another one-time GitHub token (owner).
