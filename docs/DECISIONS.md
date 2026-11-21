# DECISIONS — hermes-roi

Durable decision log. Every decision that changes scope, contract, architecture,
or process is recorded here — **including decisions made by the owner**, per
owner directive (D-003). One block per decision; newest last.

- **Time** is UTC+08. Times for owner chat decisions are session-relative and
  approximate (marked `≈`); agent decisions carry the wall-clock time known at
  the moment they were made.
- **Decision-maker** is either `OWNER` or `AGENT` (the ROI dev agent). A grant
  (owner) + execution (agent) pair is shown as `OWNER (grant) → AGENT (executes)`.

---

## D-001 — ROI is machine-global, not per-tab
- Time: 2026-11-02, T03 session (≈, owner chat)
- Problem: The T03 page initially bound its numbers to the active profile tab.
- Consideration: ROI measures the machine's total local-inference value, not one
  profile's slice. Following the active tab would make the hero number jump on a
  tab switch — misleading and not what the product is.
- Decision: ROI is **machine-global**. `/summary` defaults to `scope=all`
  (aggregates every local profile store). The page never re-keys on the active
  profile tab. Per-profile scope remains available as an explicit override.
- Decision-maker: **OWNER**
- Status: implemented — collector `summarize_global`, backend `scope=all`
  default, page requests `scope=all`; 5 global tests + 2 endpoint tests pass.

## D-002 — "Local" is user-declared, not name/URL-guessed
- Time: 2026-11-02, T03 session (≈, owner chat)
- Problem: "Local" was being inferred from loopback URL / model name.
- Consideration: Users run local models over LAN IPs, proxies and docker ports
  that Hermes sees as remote URLs; a model name proves nothing (live trap:
  `Qwen3.8-27B-MLX-6bit` also appears under `openai-codex`). Only the user knows
  which of their models are local — current and historical.
- Decision: **Local = user-ticked multi-select of model names.** The loopback
  URL check is demoted to a *candidate hint*. A session counts as local iff
  (model ∈ tick-list) OR (base_url is loopback). The tick-list is passed as
  `local_models=` and persisted in the desktop plugin's `ctx.storage`; the P2
  settings UI edits it. The backend stays stateless and read-only.
- Decision-maker: **OWNER**
- Status: implemented — collector allowlist union, backend `local_models`
  param, page reads `ctx.storage.local_models`; allowlist tests pass. Tick UI = P2.

## D-003 — Fast preview + full decision transparency + agent autonomy
- Time: 2026-11-02, T03 session (≈, owner chat)
- Problem: Work had stalled on T03 detail questions; owner wanted a usable
  preview fast and complete visibility into who decided what.
- Consideration: Owner granted the agent discretion on in-scope implementation
  choices and required that **all** decisions (owner's and agent's) be recorded
  in the repo with time / consideration / decision / decision-maker.
- Decision: The agent proceeds autonomously on in-scope choices, prioritizes
  delivering the usable preview, does not dither on trivial details, and logs
  every decision in this file.
- Decision-maker: **OWNER (grant) → AGENT (executes)**
- Status: in effect.

## D-004 — Progress-monitor cronjob
- Time: 2026-11-02, T03 session (≈, owner chat)
- Problem: Owner wanted progress monitored proactively, not only on request.
- Consideration: A durable cron job running a deterministic monitor script and
  reporting a one-line status (elaborating only on failure) gives visibility
  without noise, and outlives this session.
- Decision: Create a cronjob (cronjob tool) every 30 minutes running
  `scripts/progress-monitor.sh` and reporting; owner may pause/remove it.
- Decision-maker: **OWNER (grant) → AGENT (designs)**
- Status: created — job `5649fd37efaf` (`roi-progress-monitor`, every 30m,
  delivers to this chat; gateway_running=true at creation, 2026-11-02 01:2x).

## D-005 — Access grant
- Time: 2026-11-02, T03 session (≈, owner chat)
- Problem: Live delivery (install, enable, verify) needs real host access.
- Consideration: Owner explicitly granted the necessary access rights.
- Decision: The agent may install the plugin into the host tree, enable it in
  config, and prepare + verify the live mount. The gateway restart itself is
  owner-executed (see D-010).
- Decision-maker: **OWNER (grant)**
- Status: in effect. Owner later explicitly authorized both the plugin
  install and the gateway restart (2026-11-02, chat); see D-010/D-014 for
  how that authorization was executed.

## D-010 — Gateway restart is an owner-run step
- Time: 2026-11-02 01:03
- Problem: The one multiplexer gateway (PID 24483) hosts this very agent
  session; the Hermes CLI hard-blocks `gateway restart` from inside a gateway
  process (SIGTERM propagates to child processes) — a self-restart would kill
  the running turn before it could report.
- Consideration: A restart physically cannot be self-executed from within the
  gateway process tree. It must be run from a separate shell outside the
  gateway.
- Decision: The agent prepares everything (install + enable + monitor) and hands
  the owner a single command to run from a separate shell:
  `hermes --profile default gateway restart`. The cronjob then confirms the
  backend mounted (gateway-log evidence) and reports.
- Decision-maker: **AGENT** (forced by CLI invariant)
- Status: owner explicitly approved the restart (2026-11-02); execution
  remains owner-run per D-014. Command: `hermes --profile default gateway restart`.

## D-014 — Agent will not bypass the gateway lifecycle guard
- Time: 2026-11-02 01:25
- Problem: With the restart authorized, the only agent-side paths are all
  hard-blocked: the terminal and execute_code layers block gateway
  lifecycle commands from inside the gateway (and scan *referenced
  scripts*); `launchctl submit/bootstrap` is blocked label-independently;
  the cron layer rejects restart jobs. The documented hazard is the
  SIGTERM-respawn loop: the supervisor revives the gateway, auto-resume
  re-runs the interrupted turn, and a restart-again loops the session into
  a broken state (`cron/lifecycle_guard.py`, refs #62891/#80260/#87033).
- Consideration: Owner authorization covers the *operation* (restart the
  gateway), not the method of circumventing a hard safety boundary.
  Bypassing a guard that can permanently break this very session is beyond
  the agent's unilateral remit (SOUL: explicit approval for risky/
  irreversible operations; truthful risk reporting). The guard's own
  message names the legitimate path — a separate shell outside the
  gateway — a 30-second owner action.
- Decision: No bypass attempts (no encoded helpers, no launchctl
  trickery, no cron restart jobs). The owner runs `hermes --profile default
  gateway restart` from a separate terminal (or the desktop app's gateway
  controls). The 30-minute monitor cronjob then reports the mount state
  (3-state check per D-015); instant check: `bash
  scripts/progress-monitor.sh`.
- Decision-maker: **AGENT** (within the owner's authorization; the owner may
  override — an explicit instruction to bypass would be required, and even
  then the loop hazard stands)
- Status: in effect.

## D-015 — Mount-evidence premise refuted; 3-state monitor model
- Time: 2026-11-02 07:12
- Problem: This repo documented (DATA_CONTRACT §9b, PROGRESS 2026-11-02)
  "mount verification: gateway-log evidence (`Plugin <id>:` lines)" as a
  verified fact. The premise is wrong: v0.22.5 logs NOTHING on successful
  plugin load (zero lines for home-dashboard/hermes-activity after the
  2026-11-01 21:44 start), and `web_server_plugin_profiles.py` shows the
  backend is **lazily mounted on the first desktop request** (module
  `hermes_dashboard_plugin_<name>`) — a mount log line could not exist
  anyway. The old monitor logic (raw grep for "hermes-roi" in the logs)
  produced a false-positive ATTENTION from agent tool-error lines that
  mention the repo path (observed in the 07:10 run).
- Consideration: The monitor is the owner's progress signal (D-004); a
  false positive is worse than a quiet pending. The CLI-verifiable signals
  that actually exist: (a) discovery — `hermes plugins list` shows
  `hermes-roi | enabled | 0.1.0 | user` (verified 07:10); (b) freshness —
  last `Gateway control socket listening` vs install mtime (verified:
  21:45:00 < 01:13:15 → PENDING RESTART); (c) no import failure in
  `gateway.error.log`. Definitive confirmation (page renders) needs the
  desktop session; the curl 401 gate is uniform (home-dashboard also 401),
  hence not a signal.
- Decision: Monitor §5 rebuilt as a 3-state check (discovery / PENDING
  RESTART / ready or MOUNT ERROR); PENDING is the expected pre-restart
  state, not a failure (exit 0), but is reported every tick; DATA_CONTRACT
  §9b and the PROGRESS entry corrected in place with dated errata.
- Decision-maker: **AGENT** (correcting its own unverified claim; D-003's
  record-everything applies to corrections too)
- Status: in effect; re-verify at the owner's restart (state flips to
  "ready" once the gateway starts after the install; page confirmation by
  the owner in the desktop).

## D-016 — Sidebar row absent: opt-in posture by design (GHSA-mcfc-hp25-cjv7)
- Time: 2026-11-02 07:55
- Problem: After the owner's gateway restart (07:42:19) no ROI row appeared
  in the desktop sidebar ("restart done，但是没看到侧边栏的roi"). Diagnosis
  (apps/desktop source, v0.22.5 dev build):
  - Electron materialized our desktop half at app start (app PID started
    07:43:37): `~/.hermes/desktop-plugins/hermes-roi/` copied 07:43 WITH the
    `.hermes-package.json` marker — the file is exactly where the loader
    reads it; all four SDK imports (`useQuery`, `Skeleton`,
    `ROUTES_AREA`, `SIDEBAR_NAV_AREA`) verified present in
    `apps/desktop/src/sdk/index.ts`.
  - `desktop.log` contains ZERO hermes-roi mentions: the bundle was never
    loaded — no import/runtime error; it was simply not activated.
  - Root cause: `src/contrib/runtime-loader.ts:924` loads a marked
    materialized half with `defaultEnabled: marker ? false : undefined`;
    with no user decision in localStorage
    (`hermes.desktop.pluginDecisions.v2`), `pluginActive()` → false → the
    record is inventoried as DISABLED (Plugins settings page) and no nav
    row is registered. Our bundle's own `defaultEnabled: true` is capped by
    the loader option (line 523).
  - This is deliberate: the marker comment cites GHSA-mcfc-hp25-cjv7 —
    "the Python half is installed-but-inert until allowlisted — so the
    desktop half matches."
- Consideration: Enabling is the user's consent step (Plugins page toggle,
  live — no app reload). Pre-seeding a decision into the app's localStorage
  would circumvent the designed consent flow, so the agent does not do it.
  The toggle is app-level (one decision, visible in every profile window),
  consistent with D-001: once visible, the page's DATA is machine-global
  regardless of the active tab.
- Decision: Owner action — Desktop → Settings → Plugins (or ⌘K →
  "Plugins"), find the **ROI** row (package `hermes-roi`, status
  disabled), toggle ON. Sidebar row + `/roi` page appear immediately; the
  first page view lazily mounts the backend into the fresh gateway. Import
  path pre-verified before asking the owner to act: `plugin_api.py` inserts
  the plugin root into `sys.path` before `from roi import activity_reader`
  (stdlib-only module); fastapi confirmed present in the gateway venv;
  monitor's MOUNT ERROR state would catch any import failure on the next
  30-minute tick.
- Decision-maker: **AGENT** (diagnosis) + **OWNER** (consent toggle)
- Status: awaiting the owner's toggle.

  Erratum 2026-11-05 01:15 (AGENT): the "Settings → Plugins" location in
  this entry was WRONG — the owner confirmed ROI is absent there
  ("ROI 在设置-plugins 里面也不存在"). Verified in source
  (apps/desktop, v0.22.5 dev build):
  - `src/contrib/settings-pages.ts:221-224` (`pluginSettingsEntries`):
    an agent row only becomes a Settings entry when
    `row.settings_schema?.length` is non-empty; hermes-roi has no
    settings schema (0 tools / no config fields), so its agent row is
    silently skipped. Desktop halves only appear there via a
    `SETTINGS_PLUGINS_AREA` contribution — ours registers none.
    Settings → Plugins can therefore NEVER show a plain
    page-only plugin.
  - Correct location: **Capabilities → Plugins tab**
    (`src/app/capabilities/plugins/plugins-tab.tsx`): unified-package
    rows with both halves' state and switches (`desktopOn` = record
    status !== 'disabled', `agentOn` = row enabled;
    `toggleDesktop` → `setPluginEnabled`). Backend row verified live
    (plugin manager scan: key='hermes-roi', enabled, error=None —
    identical posture to known-good hermes-activity); desktop half
    present on disk and app session (00:49) postdates the install;
    all four SDK imports re-verified in `src/sdk/index.ts`.
  - Owner action (corrected): Desktop → **Capabilities → Plugins**,
    find the **ROI / hermes-roi** row, toggle the DESKTOP half ON.
    The sidebar row (label "ROI", codicon pulse) appears immediately;
    first `/roi` view lazily mounts the backend.

## D-017 — T04 split: pure layer (T04a) shipped; wiring (T04b) awaits the price-card decision
- Time: 2026-11-02 08:05
- Problem: T04 (per the PROGRESS 2026-11-02 handoff) covers both the pure
  economics layer AND its wiring (per-model rows from
  `session_model_usage`, `/summary` economics, the hero + verdict UI).
  Subagent deleg_13eaa5c5 delivered the pure layer
  (`roi/pricing.py` + `roi/verdict.py`, 44 new tests).
- Consideration: Wiring without a price card produces dead numbers — with
  no `PriceSnapshot` the hero would read 0.000% / "unknown" forever, and
  the price card's data source is an OPEN OWNER question (who
  authors/maintains the rate card: user-editable settings, provider docs,
  or a provider API?). Per SOUL, unresolved financial definitions go to
  the owner. The pure layer is complete, tested, and independent of that
  decision — shipping it now loses nothing.
- Decision: Commit T04a as delivered (verified by the orchestrator:
  76/76 tests, both selftests, code review against the fixed product
  rules — all conforming). T04b = wiring: (1) per-model usage rows from
  the collector, (2) `/summary` economics extension (hardware_cost +
  start_at + snapshot from `ctx.storage`), (3) page hero block (recovery
  3dp, break-even countdown, four-tier verdict + onboarding state). T04b
  starts when the owner decides the price-card source; until then the v1
  page (bucket totals, local/unknown counts) is the usable preview.
  Open owner questions (forwarded from the subagent's report):
  price-card data source; FX policy; the energy/operating-cost model
  behind "net savings"; whether a "bill reasoning separately" toggle is
  wanted (DATA_CONTRACT §13.1 still lacks a provider-doc citation);
  whether the unknown (<30-day) state may show a provisional pace.
- Decision-maker: **AGENT** (scope split) + **OWNER** (price-card question, pending)
- Status: in effect; price-card question ANSWERED 2026-11-02 (D-018–D-021).

## D-018 — Price-card source: official docs fetch + manual input; standard = DeepSeek
- Time: 2026-11-02, owner answers #1 (chat)
- Owner decision (verbatim intent): price card is fetched from the
  provider's official docs and also supports manual user input; the
  standard benchmark object is **DeepSeek**.
- Recorded interpretation: cloud-equivalent value for ALL local usage is
  priced against DeepSeek's official API rate card (the benchmark), not
  per-local-model cloud twins. Official page verified 2026-11-02:
  `https://api-docs.deepseek.com/quick_start/pricing/` (EN + ZH tables
  cross-consistent, ~6.67 USD/CNY). Current card (per 1M tokens, USD):
  `deepseek-flash` (V4.1-Flash-1017) — input cache hit 0.003/0.006
  (off/peak), input cache miss 0.15/0.30, output 0.60/1.20;
  `deepseek-v4-pro` (V4-Pro-0813) — 0.022/0.044, 0.66/1.32, 1.98/3.96.
  Peak = 01:00–04:00 + 06:00–10:00 UTC Mon–Fri excl. CN holidays;
  off-peak = exactly half peak. No cache-write line (→ 0), no separate
  reasoning line (thinking included in output).
- Agent sub-decisions (recorded per D-003): card stores BOTH peak and
  off-peak; v1 default basis = **peak** (conservative for the avoided-cost
  claim, simple; time-aware per-timestamp rates are a P2 refinement).
  Default benchmark model = `deepseek-flash` (standard general-purpose
  tier; both models ship in the card, user-switchable in P2 settings).
  "Official docs fetch" ships as a committed snapshot (source URL + as-of
  date) + a manual refresh action; no silent runtime network calls
  (privacy-first). Manual user input overrides the snapshot per model.
- Decision-maker: **OWNER** (#1) + **AGENT** (sub-decisions above)
- Status: in effect; snapshot file lands with T04b-data.

## D-019 — FX: xe.com data, target currency USD
- Time: 2026-11-02, owner answers #2 (chat)
- Owner decision: use the xe.com API or data for currency conversion to
  USD.
- Agent sub-decision: v1 ships a committed rate snapshot (Xe-sourced,
  as-of dated) + manual rate entry; live Xe API fetch is opt-in
  (user-supplied API key, no default network calls — privacy-first).
  All displayed money is USD; the card currency and hardware-cost
  currency convert through this module (Decimal, rate stamped in the
  audit notes).
- Decision-maker: **OWNER** (#2) + **AGENT** (snapshot-first sub-decision)
- Status: in effect.

## D-020 — Energy/operating cost: optional, electricity rate × usage
- Time: 2026-11-02, owner answers #3 (chat)
- Owner decision: make it an optional setting; support entering
  electricity price × energy usage (电费 × 用电量).
- Implementation shape: `energy_cost = unit_price_per_kwh × kwh` (Decimal);
  empty setting → net savings = gross cloud-equivalent (labeled "gross,
  energy not modeled"); set → net = gross − energy_cost. kWh can be
  entered directly or derived (watts × hours) — direct entry first.
- Decision-maker: **OWNER** (#3) + **AGENT** (formula shape)
- Status: in effect. **Revised by D-020r (2026-11-05).**

### D-020r — Energy input is a MONTHLY usage estimate (not cumulative)
- Time: 2026-11-05, owner (chat): "electricity 的瓦数是日还是周还是月单位？
  没有人会统计 cumulative electricity，换成让用户输成月用量估算。"
- Question resolved: the old field was a single **cumulative kWh total** with
  no time unit (placeholder literally "kWh") — i.e. neither watts nor a
  rate. It was modeled as a **flat one-time offset** on the start day (the v1
  simplification noted above), so it never scaled with elapsed time.
- New semantics (DECISION, decision-maker **OWNER** = the "monthly estimate"
  change; **AGENT** = the allocation formula + the net-pace deduction):
  the field is now **kWh / month** (an estimate).
  - rate `USD/month = price × kWh/month` (FX'd to USD when the price ccy
    differs, D-019).
  - **Elapsed** portion `rate/30 × days_since_start` → a flat negative event
    on the start day (feeds `total_net` / hero % exactly as before).
  - **Ongoing** portion `rate/30 per day` → deducted from the break-even
    pace (`pace = window_net/30 − recurring_cost_per_day`), so the projection
    keeps paying for electricity. Net pace ≤ 0 ⇒ `no_positive_pace` (a rig
    that burns more electricity than it saves has no finite break-even).
  - `recurring_cost_per_day = 0` (no energy) ⇒ byte-identical to the legacy
    path; `project_break_even` gained the param, all prior verdict tests
    pass unchanged.
  - Determinism seam: the endpoint reads `HERMES_ECON_NOW` (else
    `time.time()`), so monthly elapsed cost is testable; production unchanged.
- Why net the pace (not just scale the past offset): a $60/mo rig on a
  $5,000 card has a *much* later break-even than the gross pace implies;
  ignoring future electricity would be exactly the "unserious financial
  optimism" the motto forbids. Past and future are both net of recurring.
- Evidence: `tests/test_economics.py::test_energy_monthly_estimate` (rate,
  elapsed, net) and `::test_energy_monthly_nets_the_pace` (997 days with
  electricity vs 820 without — energy pushes the date LATER). 134/134 OK.
- Status: in effect (supersedes the flat-offset simplification).

## D-021 — Reasoning billing: exact when available, rough otherwise
- Time: 2026-11-02, owner answers #4 (chat)
- Owner decision (verbatim): 能取到准确值就计算，取不到就大略估算 —
  bill the exact value when the source reports one; estimate roughly when
  it does not.
- Consequence for the DeepSeek card (D-018): DeepSeek's official card has
  NO separate reasoning line (thinking is inside the output price), so
  the "exact value" does not exist → the rough-estimate path applies →
  reasoning rate = 0 (bill output once; double-count forbidden per
  DATA_CONTRACT §3.3). If a future card has an explicit reasoning line,
  it bills that exact line. The per-model user tick-list and card
  override still allow a user to set a non-zero reasoning rate manually.
- Decision-maker: **OWNER** (#4) + **AGENT** (card consequence)
- Status: in effect.

## D-022 — #5 resolved: strict unknown for <30-day history; sub-decisions approved
- Time: 2026-11-02, owner answer (chat)
- Owner decisions: (a) option **A** for the insufficient-history state —
  the verdict area shows a strict "unknown" onboarding state until 30
  calendar days have elapsed since the effective start (the hero recovery
  % still renders from day one, cumulative-only); no provisional pace.
  (b) The two D-018 sub-decisions are known and approved: v1 default
  rate basis = **peak** (off-peak stored in the card for P2 time-aware
  rates); default benchmark model = **deepseek-flash**.
- Decision-maker: **OWNER**
- Status: in effect; unblocks T04b-data (card snapshot, FX, energy).

## D-023 — MOUNT ERROR root cause: missing top-level __init__.py (repo defect, fixed)
- Time: 2026-11-04 ~14:40, agent investigation after a 2-day monitor
  ATTENTION loop
- Problem: monitor flagged `Failed to load plugin 'hermes-roi': No
  __init__.py in .../profiles/{housing,housing-agent,housing-dev}/
  plugins/hermes-roi` repeatedly. Working theory (monitor + agent,
  D-015 era): "stale per-profile copies need owner cleanup" — only
  half right.
- Verified root cause (v0.22.5 source, `hermes_cli/plugins_loader.py`
  :814-816 + :615-619): the directory-plugin loader REQUIRES a
  top-level `__init__.py` exposing `register(ctx)` for any directory
  plugin (imported as `hermes_plugins.<slug>`). hermes-roi shipped
  WITHOUT one — in the repo AND in the installer's copy list — so
  EVERY copy, including the host install, was unloadable wherever a
  gateway scans it. default/roi-dev showed no error line only because
  none of their gateways had scanned the host copy yet (backend
  lazy-mount, D-015). Reference check: hermes-activity (working)
  ships `__init__.py` + `register`; home-dashboard needs none
  (layout.json-only discovery path).
- Fix (agent, within the authorized repo; reinstalled to host):
  repo-root `__init__.py` (documented no-op `register(ctx)` — v1
  surface is the lazy dashboard backend); `scripts/install-local.mjs`
  copies it; `tests/test_packaging.py` pins the contract (3 tests).
  Verified with a loader simulation on the INSTALLED copy using the
  exact v0.22.5 import mechanics: OK.
- Monitor fix (erratum): `progress-monitor.sh` §5 grep of
  gateway.error.log was time-ungated, so days-old lines pinned
  STATUS=ATTENTION every tick even after fixes. Now time-floored at
  max(last gateway start, install mtime); §4 also checks the installed
  copy has `__init__.py`.
- Residual RESOLVED 2026-11-04 (owner instructed "先修复 #2"): agent
  RE-SYNCED (not deleted — non-destructive, matching the "修复"
  instruction) the pre-fix copies under `profiles/housing` and
  `profiles/housing-agent` via `node scripts/install-local.mjs
  --profile <name>` (no --enable: those profiles' configs untouched).
  Both copies now carry the top-level `__init__.py` + full roi/ and
  pass the v0.22.5 loader simulation (imported as
  hermes_plugins.<slug>, register clean). `housing-dev`'s copy was
  already gone.
- Decision-maker: **AGENT** (diagnosis + repo + monitor fix); **OWNER**
  (approved housing copy repair; gateway restart still owner-run)
- Status: repo fix committed + installed; housing copies re-synced and
  loader-verified; only the owner-run gateway restart remains.

## D-024 — Design-mockup pass: follow Proposal v0.1 verbatim; UI + basic features first, extensions later
- Time: 2026-11-05 ~02:00, owner instruction (chat, before sleep):
  "行了，你参考着我们的原始设计图迭代着吧，先把 UI 做好看了，基本功能都
  做上。再说拓展功能。我要睡了，你先迭代着，我起来检查。不要问我的意见
  和 approval。你先改着，自己决策"
- Owner decisions embedded in the instruction: (a) the original
  Proposal v0.1 mockup is the design source of truth; (b) priority =
  UI polish + complete basic functionality; extensions explicitly
  deferred ("再说拓展功能"); (c) full implementation autonomy for the
  overnight pass — no approval questions; the owner reviews in the
  morning.
- Agent decisions (within that authority, all recorded per the
  2026-11-02 decision-logging mandate):
  - Mockup copy verbatim: bilingual tier labels (zh headline + EN
    punchline), roast lines, tagline, footer, live countdown format
    (month unit rendered "MO" to avoid M/M ambiguity — a fix, not a
    deviation).
  - Currency stays USD (mockup's SGD is placeholder; card + math are
    USD per D-018). Multi-currency hardware input deferred to P2.
  - Theme stays the app's real --ui-* tokens; the mockup's "neon" is
    realized as accent glow on the tier-colored elements (low-glare
    principle), no hardcoded palettes.
  - New /economics `curve` (daily cumulative NET + linear projection
    to break-even, ≤500 points) so the chart, hero percent and
    break-even date are one consistent story; projection drawn faint
    so actuals stay the subject.
  - New verification method: browser harness with local UMD React +
    SDK stub + REAL endpoint payloads (see PROGRESS 2026-11-05
    02:00 entry) — frontend is now visually smoke-tested, not just
    node --check.
  - Deferrals to P2 (the "拓展功能" list): home-dashboard widget
    (mockup right sidebar), local-model tick UI, per-model pricing,
    multi-currency input.
- Decision-maker: **OWNER** (instruction + priorities); **AGENT**
  (all sub-decisions above)
- Status: in effect. v3 shipped: 133/133 tests, visual smoke test
  green, reinstalled + hot-reloaded on all 10 locations. Owner review
  pending (2026-11-05 morning).

## D-011 — Install location + enablement scope
- Time: 2026-11-02 01:03
- Problem: Where does the backend live, and which profile's config gates it?
- Consideration: The desktop page is app-level (one install, visible in every
  profile's window). The Python backend is imported only when the plugin is in
  the `plugins.enabled` allow-list of the config the mounting gateway reads.
  This machine runs a single default-profile multiplexer serving all 9 profiles.
- Decision: Install the unified package to `~/.hermes/plugins/hermes-roi/` and
  enable `hermes-roi` in the **default** profile's `plugins.enabled`
  (the multiplexer's home). Verify empirically via the monitor; if it does not
  mount after restart, also enable it in `roi-dev`'s config.
- Decision-maker: **AGENT**
- Status: install + default-enable done; mount pending owner restart.

## D-012 — `/summary` contract
- Time: 2026-11-02 01:03
- Problem: Define the read-only backend contract for the preview.
- Consideration: Keep the backend a pure function of (stores, window, allowlist);
  no shared mutable state; version the shape so the page can pin it.
- Decision: `GET /summary?scope=all|<profile>&days=N|since=..&until=..&local_models=a,b`
  returns `CONTRACT_VERSION=0` JSON (totals, per-day buckets, local/unknown
  counts, profiles list, audit notes). `GET /health` reports version + store
  presence. Errors: 400 bad window, 404 missing profile/store, 500 schema.
- Decision-maker: **AGENT**
- Status: implemented + tested (10 endpoint tests).

## D-013 — Allowlist persistence location
- Time: 2026-11-02 01:03
- Problem: Where is the user's local-model tick-list stored?
- Consideration: It is a desktop-side preference; the backend must stay
  stateless and read-only. `ctx.storage` is plugin-namespaced JSON persistence.
- Decision: Store the tick-list in the desktop plugin's `ctx.storage`
  (`local_models`, JSON array string); the page passes it per request as
  `local_models=`. No backend-side state, no config.yaml coupling.
- Decision-maker: **AGENT**
- Status: implemented (page reads storage; P2 writes it via the settings UI).

## D-025 — <30-day history: Option B provisional estimate (supersedes D-022a)
- Time: 2026-11-06, owner answer (chat)
- Context: D-022a (2026-11-02) had chosen Option A — a strict "unknown"
  onboarding wall until 30 calendar days elapsed (no provisional pace). The
  owner re-raised this on 2026-11-06 and stated the requirement as "the first
  30 days should ALSO give an estimate" (Option B). The original exchange was
  re-verified against the session transcript: the owner was offered A vs B with
  the instability trade-off spelled out and had picked A — so this is a
  deliberate change of mind, not a correction of a mis-record.
- Decision: **Option B.** When <30 calendar days have elapsed since the
  effective start AND there is recorded usage, compute a PROVISIONAL pace from
  ALL available days: pace = cumulative net / (elapsed+1 calendar days,
  zero-usage days included — the same calendar-day convention as the standard
  window), and project the break-even from it. The result is flagged
  `provisional` (BreakEvenProjection.provisional / Verdict.provisional) and
  surfaced in the UI as an amber "临时估算 · 基于 N 天（满 30 天转正式口径）"
  badge plus a "Pace (Nd · 临时)" stat. From day 30 the standard trailing-30-
  day window applies (provisional=False); that one-time number shift is
  expected and disclosed. NO usage at all remains the strict "unknown"
  onboarding state (there is nothing to estimate).
- Trade-off accepted by the owner: with a small sample the provisional pace is
  unstable (a heavy day or a 3-day idle can swing it ~2–4×), and it jumps once
  on day 30 when the basis flips to the trailing 30 days. Both disclosed in
  the UI badge.
- Implementation: roi/verdict.py (project_break_even provisional branch +
  BreakEvenProjection/Verdict `provisional`/`pace_days`), dashboard/plugin_api.py
  (expose `provisional`/`pace_days` on /economics), desktop/plugin.js (hero
  badge + pace stat label). Tests: tests/test_verdict.py (1 renamed + 4 new
  provisional pins: divides-by-actual-days, no-usage-still-unknown,
  day-30-boundary-standard, standard-not-provisional). 138/138 OK.
- Decision-maker: **OWNER** (A→B) + **AGENT** (semantics + UI)
- Status: in effect; supersedes D-022a. The backend shape change requires a
  gateway restart (`hermes --profile default gateway restart`) before the live
  /economics endpoint returns the new fields.
