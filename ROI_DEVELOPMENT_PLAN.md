# ROI / Return on Intelligence — Development Plan

> Version: 0.2 | Updated: 2026-11-01 | Implementation owner: Hermes profile `roi-dev` using a locally deployed Qwen 27B 6-bit model.
>
> Product motto: **Serious engineering. Unserious financial optimism.**

## 0. Product decision and scope

Build a Hermes Desktop community plugin called **ROI — Return on Intelligence**. It reads the same *underlying* activity source as `hermes-activity`, estimates the hypothetical cloud API price of local inference, and shows:

1. **Hardware cost recovered**, in a huge three-decimal percentage: `2.731%`.
2. **Projected break-even date** and a theatrical live countdown.
3. **A highly visible four-tier sarcastic verdict** (single current tier, not four simultaneous status cards).
4. Four compact financial facts: hardware cost, estimated cloud-equivalent value, recent net savings/day, and strict financial ROI.
5. Optional expandable methodology, token breakdown, cumulative trend, and configuration.
6. A separate compact **Hermes Home Dashboard widget** built as an optional integration.

### Definition of done

- Runs inside a current Hermes Desktop installation as a standalone, installable community plugin.
- Correct for mixed local/cloud usage, cache semantics, unknown token usage and multi-profile behavior.
- UI is consistent with native Hermes's understated dark/blue terminal style.
- Features produce reproducible, unit-tested results; the UI labels simulated savings as *estimated*, never realized revenue.
- The Home widget's architecture and dependency on `home-dashboard` are documented honestly.
- A public repository is prepared for Hermes community catalog review and `hermes plugins validate` passes on the development machine.

### Scope policy

**MVP:** source read-only, one selected Hermes profile at a time, selected local-model allowlist, reported-token accounting, custom cloud prices, editable hardware cost, currency and FX, recovery, net ROI, 30-day forecast, countdown, four verdicts, Settings, status-bar chip.

**After MVP:** Home Dashboard adapter; richer comparisons, multiple profiles aggregated with de-duplication, electricity estimate, TPS fallback, cloud-price presets, localized UI, shareable cards.

**Avoid MVP scope creep:** native power telemetry, token-to-quality scoring, GPU utilization benchmarks, social leaderboard, custom window manager, automatic API pricing crawlers.

## 1. Architecture (confirmed baseline vs investigation)

### Confirmed from documentation

- Hermes profiles have independent configuration, `SOUL.md`, sessions and `state.db`; the dedicated `roi-dev` profile has its *own empty history*. Data must come from the user-selected target runtime profile, not accidentally from `roi-dev`.
- `hermes-activity` opens its current profile's SQLite `state.db` in `mode=ro`. Its `sessions` data includes `started_at`, `model`, `billing_provider`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`, `parent_session_id`, and estimates/actual prices where available. The Activity UI uses profile-routed CLI execution for local/remote collection.
- Hermes Desktop plugins register public SDK contributions, expose native settings, and can use the backend via scoped `ctx.rest` if an appropriately mounted `dashboard/plugin_api.py` exists.
- `home-dashboard` has its own widget registry; there is no verified third-party widget injection API. Contribute an adapter via its source repository (or agree an extension API upstream). Do not runtime-patch the other plugin.

### Recommended package

```text
hermes-roi/
├── plugin.yaml
├── __init__.py                # if required to satisfy plugin lifecycle/manifest
├── dashboard/
│   ├── manifest.json         # plugin-scoped API mount
│   └── plugin_api.py          # profile-scoped /settings, /summary, /daily, /health
├── roi/
│   ├── activity_reader.py     # read-only adapter, profile-aware
│   ├── models.py              # typed input/output contracts
│   ├── pricing.py             # Decimal-based money and token prices
│   ├── forecasting.py         # estimated payback + confidence
│   ├── ratings.py             # deterministic four-tier verdict
│   └── storage.py             # plugin settings only
├── src/
│   ├── plugin.tsx             # Hermes Desktop SDK page and chip source
│   ├── components/
│   └── design-tokens.css
├── desktop/
│   └── plugin.js             # built distributable ESM, no raw JSX
├── tests/
│   ├── fixtures/
│   ├── test_activity_reader.py
│   ├── test_pricing.py
│   ├── test_forecasting.py
│   └── test_ratings.py
├── docs/
│   ├── DATA_CONTRACT.md
│   ├── METHODS.md
│   └── screenshots/
├── README.md
├── CHANGELOG.md
├── AGENTS.md
└── LICENSE
```

This is a **target layout**, not an assertion that every API hook is already verified. During P0, verify the actual plugin manifest, SDK contribution signatures and backend mount lifecycle against the running Hermes version and working examples. Prefer the simplest supported route. Build self-contained Desktop ESM with React/JSX compiled out; the deployed disk artifact imports only permitted SDK/React modules.

### Runtime data flow

```
Selected Hermes profile + selected local models
                |
       read-only state.db collector
                |
      normalized usage records (typed)
                |
      cloud benchmark rate card + FX
                |
        pricing + net savings engine
                |
   rolling 30-day forecast and four tiers
                |
        plugin API JSON response
             /      \
    Desktop ROI page  Home adapter (phase 2)
       + status chip
```

Read `state.db` **with read-only mode**, parameterized SQL, bounded time ranges and no raw message content. Store settings separately. Profile access must follow supported Hermes profile routing, rather than arbitrary paths to other users' files.

## 2. Data audit — mandatory P0 gate

### Questions the agent must answer with actual evidence

1. Which exact Hermes version and Desktop SDK interfaces are installed?
2. Is the database schema `sessions` the same as the current `hermes-activity` source? Capture column names, types and a sanitized example.
3. Are input/output tokens inclusive or exclusive of cache read/write and reasoning tokens **for this Hermes version**? Verify definitions in code, provider adapters, and representative records. Never infer billing semantics from UI labels.
4. How are subagents represented? Is parent usage aggregated already, or are parent/subagent records independent?
5. What fields reliably identify `local` runtime vs cloud usage? Use an explicit model/provider allowlist, not name matching alone (a model named Qwen may run in the cloud).
6. What happened when some sessions changed model mid-session, or have missing model names?
7. Are session token counters monotonic and persisted, or do per-session totals risk counting earlier turns more than once?
8. Which time zone is used for sessions? Define an exact `start_at` rule and show it in UI.
9. Can the collector access the *default* profile from the dedicated `roi-dev` development profile without modifying it? Test the intended user-facing path.
10. Does the installed Home Dashboard expose a supported external widget registration mechanism? Inspect its actual registry; if none, record the upstream PR integration path.

Deliver P0 artifacts: `docs/DATA_CONTRACT.md`, `docs/ARCHITECTURE_DECISIONS.md`, an anonymized sample dataset, a schema-version compatibility plan, and a **real collector smoke test**. Make no ROI numbers from live usage until P0 is signed off.

## 3. Calculation contract

### 3.1 Terminology

- **H**: configured hardware cost in user's preferred currency, strictly `H > 0`.
- **V**: cloud-equivalent *gross* value of selected local inference, estimated from a chosen reference API price card and actual usage.
- **O**: modeled operating expenses (zero in MVP unless user explicitly enters expenses).
- **S = V - O**: estimated net savings / cost avoidance.
- **Recovery% = 100 * S / H**: primary hero number; display exactly 3 decimal places. It is *not* the standard financial ROI.
- **Net ROI% = 100 * (S - H) / H**: secondary strict financial return.
- **Remaining = max(0, H-S)**.

Use Python `Decimal` (or lossless integer micros + Decimal) for costs and unit prices. Keep full precision internally; round only for display. Negative `S` is possible if modeled operating costs exceed cloud equivalent value; display negative recovery meaningfully, or clamp the progress bar alone, not the underlying number.

### 3.2 Pricing formula

For each eligible usage record `i`, normalize distinct billable buckets **after confirming source-field semantics**:

```
V_i_USD = (
    uncached_input_i * cloud_input_rate_per_1M
  + output_billable_i * cloud_output_rate_per_1M
  + cache_read_i * cloud_cache_read_rate_per_1M
  + cache_write_i * cloud_cache_write_rate_per_1M
) / 1_000_000
V_user_currency = SUM(V_i_USD * FX_USD_to_user_currency_i)
```

- `output_billable` includes reasoning only if provider semantics demand that; **never double-count** if the same reasoning tokens are already in output tokens.
- Cache usage is charged at the corresponding rate or documented fallback; do not multiply a generic full-input rate by 393M cache-read tokens.
- Unknown/unsupported usage -> explicitly marked unknown; optionally show lower bound and coverage percentage, not fictional values.
- Presets may be included later, but user-edited reference pricing is authoritative. Snapshot the rate assumptions with calculations so historical values can be reconstructed.
- With flat-rate subscriptions or self-hosted cloud endpoints, 'API-equivalent value' is a *hypothetical* benchmark and should remain labeled as such.
- Select which models actually run locally, and exclude all cloud model sessions from the recovered value by default. Allow transparent overrides.

### 3.3 Time and history

- User-defined `start_at` is a timestamp with timezone and an inclusive lower bound. MVP may attribute a session's usage to its `started_at` (matching Activity) with an explicit disclosure for sessions spanning the boundary. A later version may use per-turn timestamps if supported.
- Forecast `as_of` is an explicit timestamp; countdown uses that fixed projection anchor between refreshed API calls.
- Daily 30-day pace uses calendar days *including zero-usage days*. For newer installations, use actual elapsed days since effective start and mark forecasts low confidence when history is short; do not divide by active days alone.
- No usage = recovery 0.000% (when H > 0), pace 0, projected date `null` / `∞`.

### 3.4 Forecast

```
net_pace_30d = SUM(net_savings_in_window) / calendar_days_in_window
if S >= H: status = paid_off; payback_at = known/estimated crossing timestamp
else if net_pace_30d <= 0: payback_at = null; countdown = ∞
else: payback_at = as_of + (H-S) / net_pace_30d days
```

Use `as_of` as the source of truth for countdown. Days in projection can be fractional. Recompute aggregates on user refresh or periodic polling (e.g., every 60–120s); animate countdown every second **only in the client**. Very distant years should format safely; display a year number or `> 99 years` gracefully if date libraries have bounds.

**Confidence labels:** `LOW` for short/infrequent data; `NORMAL` for meaningful history. Decide thresholds after data inspection and unit tests; always explain it in `METHODS.md`. Provide pace selector (7/30/90/lifetime) later.

### 3.5 Four ratings (evaluation priority)

| Priority | Rule | Title | Subtitle |
|---|---|---|---|
| 1 | `S >= H` | `LV1 — PAID OFF. ABSOLUTE LEGEND.` | `The accountants have been defeated.` |
| 2 | projected payback <= 90 days | `LV2 — ALMOST THERE.` | `Maybe keep the GPU running.` |
| 3 | projected payback <= 5 years | `LV3 — STILL A LONG WAY.` | `Keep grinding, hero.` |
| 4 | projected payback > 5 years or no positive pace | `LV4 — PAYBACK IS A DISTANT DREAM.` | `Your next GPU may retire first.` |

`NO DATA` is an onboarding/prediction-unavailable state, not a fifth rating. Level numbers represent a *status tier* where LV1 is highest. Use selected forecast pace consistently for rating and countdown.

## 4. UX / UI spec

### 4.1 Native style

Match the attached screenshots of actual Hermes Home and Activity: charcoal background, monochrome labels, subtle blue accent, one-pixel borders, compact card spacing, monospaced numeric presentation. Use Hermes theme variables and native UI kit; support light/dark and reduced-motion.

**Do not** replicate the first concept's saturated gold/lime, bulky side navigation, duplicated grade strip, excessive icons, or large decorative charts.

### 4.2 Full page layout

```text
> ROI / RETURN ON INTELLIGENCE                             PROFILE: default
+--------------------------------------------------------------------------+
| [ LV4 ] PAYBACK IS A DISTANT DREAM                       {small ASCII}  |
|         At this rate, your next GPU may retire first.                   |
+----------------------------------+---------------------------------------+
| HARDWARE RECOVERED               | PROJECTED BREAK-EVEN                  |
|                                  |                                       |
|             2.731%               |           2044-08-02                  |
|   ---- progress to 100% -----    |      17y 09m 01d 07:12:09            |
+----------------------------------+---------------------------------------+
| HARDWARE   | API EQUIVALENT  | NET / DAY  |  NET ROI                    |
| SGD 5,000  | SGD 136.55      | SGD .75    |  -97.269%                  |
+--------------------------------------------------------------------------+
|  ▸ Methodology & chart [expand]         ⚙ Configure in plugin settings   |
+--------------------------------------------------------------------------+
```

Layout priority: **rating first, then the two large figures, then summary strip**. Responsive UI stacks figures when narrow. Main UI uses English for the public release; Chinese localization follows later. Humor is embedded in precise figures and concise jokes, not noisy visuals.

### 4.3 Home widget (separate integration)

Intended for the Home Dashboard's draggable grid, compact 3-column footprint at normal height:

```text
-- ROI -------------------------------
  2.731%                   LV4
  [█──────────────────────]
  BREAK-EVEN: 2044-08-02
  (hover) Your next GPU retires first.
```

Click opens ROI page if public navigation is available. If cross-plugin navigation is not supported by Home Dashboard, show the number/date without making promises. Widget polls a plugin-scoped data endpoint, has skeleton/loading/error states, and uses its parent grid's resize/hover editing behaviors.

### 4.4 Deliberate comedy moments

- Exactly three decimal places in the hero (`0.003%` is a legitimate sight).
- LV4 title is large and completely deadpan.
- Countdown ticks at 1 Hz without UI-wide rerender; tiny flip or digit blink, reduced-motion fallback.
- When crossing 100%, brief non-blocking celebration; do not interrupt normal operation.
- Mini-card only shows current grade; no legend in its normal state.
- Distinguish `SAVINGS ESTIMATE` vs actual money earned visibly.

## 5. Phases, tasks, acceptance gates

### P0 — Initialize, research, and verify (first)

- [ ] Create `roi-dev` profile and configure Qwen 27B Q6 model endpoint.
- [ ] Set `terminal.cwd` to absolute path of `hermes-roi` repository (do not assume profile home = workspace).
- [ ] Add supplied `SOUL.md` to the profile; put supplied `AGENTS.md` at repo root.
- [ ] `git init` project; create `docs/` and `tests/`; record exact Hermes version and commit.
- [ ] Read official Desktop SDK, official plugin manifest and catalog validation docs.
- [ ] Inspect current `hermes-activity` activity-data reader code (license compliance) and relevant database columns.
- [ ] Reproduce a minimal read-only profile usage query and a toy SDK page.
- [ ] Inspect existing Home Dashboard widget registry and supported external integration options.

**Exit gate:** documented data semantics + SDK compatibility + one working data fetch + one native Hello ROI page. Do not proceed from guesses.

### P1 — Correct and tested economics engine

- [ ] Implement typed normalized activity records and model/provider allowlist.
- [ ] Implement source-field normalization with cache/reasoning safeguards.
- [ ] Implement cloud rate card and FX with Decimal arithmetic.
- [ ] Implement `Recovery`, strict `Net ROI`, and cumulative/daily cost avoidance.
- [ ] Implement selected-start-date filtering and transparent data coverage.
- [ ] Implement rolling 30-day projection, null/∞ states, paid-off state.
- [ ] Implement the four-tier evaluation in a pure function.
- [ ] Add deterministic unit tests and fixture SQLite DB.

**Exit gate:** a small test fixture produces exactly known cost, percentages, tier and payback timestamp; data outside the selected models/dates does not affect results.

### P2 — Desktop MVP

- [ ] Create one native SDK route/page and sidebar/palette integration.
- [ ] Implement top rating banner, hero recovery, payback date and countdown.
- [ ] Implement four-value metric strip and minimal collapsed analytics.
- [ ] Implement Settings for purchase price, start_at/timezone, profile/model allowlist, benchmark input/output/cache rates, currency and FX.
- [ ] Persist settings via plugin-scoped storage on correct host/profile; avoid secrets in UI.
- [ ] Add status-bar chip `ROI 2.731% / LV4` as a small fallback when Home integration is unavailable.
- [ ] Add loading/empty/unpriced/error and reconnect states; support locale and reduced motion.
- [ ] Test UI with recorded demo fixture, then actual private local data (no private data in screenshots).

**Exit gate:** cold-start Hermes Desktop, load the plugin, choose target profile, edit rates, observe mathematically correct recovery and countdown, disable/re-enable without affecting Hermes.

### P3 — Optional Home Dashboard widget

- [ ] Extract or expose a stable read-only summary endpoint `/summary` with versioned JSON.
- [ ] Build compact ROI card in a **separate branch/fork of `home-dashboard`**, registering through its documented source `src/home/widgets/registry.tsx` (subject to upstream review).
- [ ] Handle the other plugin being absent, ROI plugin being disabled, and backend offline.
- [ ] Run Home Dashboard's existing typecheck, tests and build; confirm layout/resize/save works.
- [ ] Propose upstream PR (or ask maintainers for third-party widget extension API).

**Exit gate:** Home card works in unmodified Hermes Desktop with the tested Home Dashboard integration branch; ROI's standalone plugin remains installable without Home Dashboard.

### P4 — Packaging, performance, safety, community release

- [ ] Add `README.md` (English-first), screenshots, setup, limitations, architecture, privacy, demo dataset.
- [ ] Run plugin tests, TypeScript typecheck, build, `hermes plugins validate /path/to/hermes-roi --install-deps`.
- [ ] Verify read-only DB access, rate/purchase validation, no credentials copied/logged, no user-message content exported.
- [ ] Test an empty profile, mixed cloud/local usage, a remote profile, an unavailable backend, zero/negative pace, already-paid-off state and far-future dates.
- [ ] Run app with activity plugin concurrently; confirm no changes to its data files.
- [ ] Tag release (`v0.1.0` proposed) and pin a full 40-character SHA for catalog submission.
- [ ] Submit `plugin-catalog/<name>.yaml` PR with supported surfaces, permissions, screenshots and limitations disclosed.

**Exit gate:** repeatable installation from a public repo and passing validation; PR ready for human review. A merged listing depends on community maintainers.

## 6. Test matrix — minimum required

| Scenario | Expected behavior |
|---|---|
| H=5000, S=136.55, O=0 | Recovery `2.731%`, Net ROI `-97.269%` |
| No selected model sessions | `0.000%`, no fabricated ETA, prompt to select models |
| 393M cache-read tokens + 59M input | Normalize/price buckets independently; no double count |
| Local Qwen plus cloud GPT sessions | Only allowlisted local sessions counted in V |
| Reasoning included in output | Reasoning is not priced again |
| Reasoning billed separately where proven | Apply documented billable output definition exactly once |
| Parent session + subagent sessions | Count each actual usage contribution exactly once |
| Hardware cost zero | Validation error, no division by zero |
| Negative daily net pace | No finite payback date; LV4 |
| S >= H | LV1, recovered ≥100%, countdown resolved |
| 90-day boundary | LV2 at <=90 days; LV3 above |
| 5-year boundary | LV3 at <=5 years; LV4 above |
| 30 days with 2 active days | Calendar-day denominator includes zeros |
| Started_at exactly start_at | Included |
| Active profile switches | Data from correct target profile only, no leakage |
| Missing `state.db` | Helpful empty state, no crash |
| Offline gateway | Cached last result clearly labeled stale or clear error |
| 2044+ date / leap year / DST | Same absolute timestamp for forecast and countdown |
| Reduced-motion preference | Countdown remains readable without flip animation |

## 7. Agent operating system (optimized for local 27B)

- **One task per work cycle**: scope each change so that one module + its tests can be reasoned about without loading all repo files.
- **Before coding**: read `AGENTS.md`, `docs/PROGRESS.md`, `docs/DATA_CONTRACT.md` and just the relevant source files.
- **After coding**: run tests, cite commands and outputs in a short report, write one durable progress update, make a focused Git commit.
- **Never claim tests ran unless they actually ran.** Never claim Hermes APIs exist unless checked against docs or installed code.
- **Context recovery**: put durable decisions and next tasks in `docs/PROGRESS.md`; use fresh chats as needed.
- **Stop/escalate** only for truly blocking permissions, ambiguous data semantics, or irreversible commands; otherwise choose a documented conservative default and proceed.
- **Work journal template**: `Goal / Inspected / Changed / Tests and results / Risks / Commit / Next task`.
- **Autonomy limits**: avoid destructive commands, `git push`, public PRs, remote publishing or modifying Hermes's core installs without explicit user authorization.

## 8. Suggested first six agent work tickets

1. **T01** — Create repository and reference inventory. Output: `docs/REFERENCES.md`, commit.
2. **T02** — Audit `hermes-activity/activity_data.py`, installed SQLite schema and profile routing. Output: `docs/DATA_CONTRACT.md`, sanitized DB fixture, test.
3. **T03** — Build minimal standalone Desktop plugin registration and a basic readonly summary response. Output: visible native page and log-free UI smoke test.
4. **T04** — Normalize billable token buckets and add pricing tests. Output: `roi/pricing.py`, `tests/test_pricing.py`.
5. **T05** — Implement break-even and four-tier verdict tests. Output: `roi/forecasting.py`, `roi/ratings.py` + tests.
6. **T06** — Build the hero UI to closely match the user screenshot, with placeholder fixture then real API payload. Output: screenshot, validation and commit.

## 9. Reference documentation

- Profiles and SOUL: https://hermes-agent.nousresearch.com/docs/user-guide/profiles
- Hermes Desktop SDK: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk
- Official catalog submission: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
- Activity source: https://github.com/hassan-kamel/hermes-activity
- Home dashboard source: https://github.com/albertocvrrbs/hermes-home-dashboard

Always verify against the installed version, since Hermes updates rapidly.
