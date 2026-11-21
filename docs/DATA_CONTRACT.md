# DATA CONTRACT — hermes-roi (P0)

Source schema, billing semantics and access rules for the read-only activity
collector. Every **verified** claim below was checked against the installed
Hermes v0.22.5 (commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e`), the
installed `hermes-activity` v0.2.2 (commit `0335e954b3ab00193720205fcdab7e10ae1194f9`),
and the live default-profile `state.db` (schema version 32, 205 sessions at
audit time) on 2026-11-01 (UTC+08). Items marked **ASSUMED** still need a
provider-doc citation before they may drive billing logic.

Scope of the contract: the collector reads **only** the `sessions` and
`session_model_usage` tables. It never opens `messages`, `messages_fts*`,
`system_prompts` or any other table: no raw user content may enter ROI.

---

## 1. Source file and access mode

- File: `<HERMES_HOME>/state.db`, one per profile (SQLite, WAL mode).
  Default profile's home is the Hermes root itself (`~/.hermes`); named
  profiles live at `<root>/profiles/<name>` (verified: `hermes_constants.py`,
  profiles doc).
- Open pattern (same as `hermes-activity`):
  `sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)`.
  `mode=ro` makes any write attempt fail with `sqlite3.OperationalError`
  ("attempt to write a readonly database") — verified by test.
- **Live-write safety verified:** while the audit ran, the default profile
  kept writing (session row count and token sums grew between two queries).
  Read-only WAL reads returned consistent results throughout. The collector
  must treat the file as append-concurrent: re-read on each refresh, never
  cache a long-lived connection across days, and never take exclusive locks
  (`timeout=5` is enough; no `BEGIN EXCLUSIVE`).
- Missing `state.db` → friendly empty state, not a crash (plan requirement;
  covered by test).

## 2. `sessions` table (verified: full DDL captured, 65 columns, schema v32)

Columns the collector uses (types from `PRAGMA table_info`):

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | Session id, e.g. `20260930_021435_eeb564` |
| `source` | TEXT NOT NULL | Surface: observed `cron, tui, local, oneshot, api_server, whatsapp, subagent, cli` |
| `model` | TEXT | **First accounted route** (see §7), not necessarily the last model used |
| `parent_session_id` | TEXT FK→sessions.id | NULL = root session; set = subagent session |
| `started_at` | REAL NOT NULL | **Unix epoch (absolute UTC time)** — session start |
| `ended_at` | REAL | End, epoch |
| `last_activity_at` | REAL | Effective-activity index column |
| `message_count`, `tool_call_count`, `api_call_count` | INTEGER DEFAULT 0 | |
| `input_tokens` | INTEGER DEFAULT 0 | Uncached input (see §3) |
| `output_tokens` | INTEGER DEFAULT 0 | Output **including** reasoning on OpenAI-family wires (see §3.3) |
| `cache_read_tokens` | INTEGER DEFAULT 0 | |
| `cache_write_tokens` | INTEGER DEFAULT 0 | 0 on this host (local servers don't report it) |
| `reasoning_tokens` | INTEGER DEFAULT 0 | Subset of output where the provider reports it |
| `billing_provider` | TEXT | Observed: `custom`, `lmstudio`, `openai-codex`, NULL |
| `billing_base_url` | TEXT | Observed: `http://127.0.0.1:1234/v1`, `http://127.0.0.1:8000/v1`, `https://chatgpt.com/backend-api/codex`, NULL |
| `billing_mode` | TEXT | Observed: `subscription_included`, `codex_responses`, NULL |
| `estimated_cost_usd`, `actual_cost_usd` | REAL | 0.0/NULL for local sessions; `included` for subscription |
| `cost_status` | TEXT | Observed: `unknown`, `included`, NULL (core Literal: `actual, estimated, included, unknown`) |
| `cost_source`, `pricing_version` | TEXT | Cost provenance (core Literal: `provider_cost_api, provider_generation_api, provider_models_api, official_docs_snapshot, user_override, custom_contract, none`) |
| `profile_name` | TEXT | Profile the session was written under (self-describing, handy for cross-checks) |
| `archived`, `hidden`, `auto_archived` | INTEGER | Lifecycle flags — collector ignores them by default; document if a future filter is added |
| `title`, `title_source` | TEXT | **Never selected by the collector** (user content) |

`session_model_usage` (verified DDL): PK `(session_id, model, billing_provider,
billing_base_url, billing_mode, task)`; same five token counters + costs per
key; `first_seen`/`last_seen` epoch. 318 rows vs 205 sessions on this host →
some sessions span multiple models/routes.

## 3. Token bucket semantics (VERIFIED in code + data)

The canonical definition lives in `agent/usage_pricing.py` (installed copy):

```python
class CanonicalUsage:
    input_tokens; output_tokens; cache_read_tokens; cache_write_tokens; reasoning_tokens
    @property
    def prompt_tokens(self): return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
```

1. **The five buckets are disjoint.** `input_tokens` is *uncached* input:
   - Anthropic shape: reported directly.
   - Codex/Chat shapes: `input = prompt_total − cache_read − cache_write`
     (cached tokens are subtracted back out of the prompt total).
   Therefore `total = input + output + cache_read + cache_write + reasoning`
   never double-counts, **except** the reasoning/output overlap in §3.3.
2. **Cache read/write are separately reported and separately billable.**
   `cache_read_tokens` on the wire: `prompt_tokens_details.cached_tokens`
   (OpenAI), `cache_read_input_tokens` (Anthropic), `prompt_cache_hit_tokens`
   (DeepSeek), `cached_tokens` (Kimi/Moonshot), nested `input_tokens_details`
   (Responses API). Cache write: `prompt_tokens_details.cache_write_tokens` /
   `cache_creation_input_tokens` / `input_tokens_details.cache_write_tokens`.
   ROI must price each bucket at its own rate; never multiply a generic
   input rate by cache-read volume (AGENTS.md hard rule).
3. **Reasoning is a SUBSET of output, not an extra bucket.** It is read from
   `output_tokens_details.reasoning_tokens` (Responses API) or
   `completion_tokens_details.reasoning_tokens` (Chat Completions) — both
   are details *inside* the completion/output total. On Anthropic wire the
   code maps no thinking path at all, so `reasoning_tokens = 0` there
   (thinking, if billed, sits inside `output_tokens` — **ASSUMED** from
   provider docs; does not affect ROI: the default never bills reasoning
   separately, so the overlap can never be charged twice).
   **ROI rule:** bill `output_tokens` once at the output rate; `reasoning_tokens`
   is reported for display/audit only, and is billable only if the user
   explicitly enables it *and* the selected provider is documented to bill
   it as a separate line.
   **Two totals, stated explicitly (collector implements both):**
   - `total_tokens` = five-bucket sum — the *reported* "Tokens" figure,
     same convention as hermes-activity's `_TOKENS` (Activity's own display
     adds all five, so it too over-states the wire total on OpenAI-family
     wires; ROI matches Activity for comparability).
   - `wire_total_tokens` = five-bucket sum − reasoning — the actual
     on-wire approximation used when a single "tokens processed" number is
     needed (TPS, context growth). Never bill from `total_tokens`.
4. **Empirical check (live default profile):** for all 159 root sessions,
   `sessions` counters equal the sum of that session's `session_model_usage`
   rows with `task = ''`, on all four compared buckets (159/159 exact). No
   negative counters anywhere; no session has `api_call_count > 0` and zero
   tokens.

## 4. Subagents (verified: code + data)

- Subagents are **independent `sessions` rows** with `parent_session_id` set
  (47 children across 7 parents on this host). Each child has its own
  counters; the parent's counters do **not** include child usage — proven by
  the 159/159 match in §3.4: if parents aggregated children, the parent's
  own per-call `session_model_usage` rows could not equal the parent counter.
- Core code confirms the mechanism: every agent's loop calls
  `queue_token_counts(agent.session_id, …)` with its **own** session id
  (`agent/codex_runtime.py`); the gateway's absolute path sets, not adds, the
  owning session's counters.
- **ROI rule:** count every `sessions` row exactly once (roots and
  children). Display the root/child split as Activity does
  (`sessions` vs `subagent_sessions`), mirroring its SQL.
- Caveat: subagent children carry the **same** `billing_*` route as their
  own calls (they run the same or a different model; their row says which).
  Classify each row on its own `billing_provider`/`billing_base_url`, never
  inherit the parent's classification.

## 5. Auxiliary (non-main-loop) usage (verified: code + data)

- Auxiliary LLM calls — `compression`, `approval`, `vision`,
  `title_generation`, `background_review` (observed on this host) — are
  recorded **only** in `session_model_usage` with `task != ''`. They do not
  touch the `sessions` counters (gateway absolute path overwrites the
  main-loop totals).
- Volume on this host (32 days): compression ≈ 1.5M input / 0.7M output over
  89 calls; approval 749 calls; vision 24 calls; title_generation 55;
  background_review 4.
- **ROI MVP decision:** price the **main-loop** usage (`sessions` counters),
  i.e. exactly what Activity displays, so ROI and Activity agree. Auxiliary
  usage is real cloud spend if local inference were replaced, but charging
  it requires the per-task table and a per-task rate policy; it is documented
  here and deferred (data coverage note in the UI later). The collector
  exposes `task` so P1 can add an "include auxiliary" mode without a schema
  change.

## 6. Local vs cloud classification (HARD RULE — verified trap in live data)

**A model name proves nothing.** Live evidence from this host: the model
`lmstudio-community/Qwen3.8-27B-MLX-6bit` appears under provider `custom`
(80 sessions, `http://127.0.0.1:8000/v1`), `lmstudio` (18, `127.0.0.1:1234`),
NULL provider (45), **and `openai-codex` (1 session, chatgpt.com backend)**.
Name-matching would misclassify that session.

Classification contract (all user-editable settings, explicit in the UI):

> **Owner decision D-002 (2026-11-02):** local-model deployment is opaque to
> Hermes — a local model on a LAN IP, docker port or behind a reverse proxy
> looks like a remote cloud route in `billing_base_url`. The user's tick-list
> is therefore the **primary** signal; the URL check only narrows candidates.

1. **`local_model_allowlist`** (a.k.a. the user tick-list) — exact model ids
   the user says run locally, current and historical. Stored in the desktop
   plugin's `ctx.storage`, passed per request as `local_models=` (D-013).
   Starts empty; the user populates it.
2. **Loopback candidate hint** — base_url hosts `127.0.0.1`, `localhost`,
   `::1`, `0.0.0.0`, `*.local`. A session with such a URL is *local-candidate*.
   A hint only: it can never by itself confirm a LAN-IP/docker/proxy local.
3. A record is **local** iff (model ∈ tick-list) OR (base_url is loopback) —
   the union, so neither signal is silently dropped. The user can review both
   contributions: the UI shows ticked models and the loopback-candidate count
   separately (P2), and the audit notes stay in the `/summary` payload.
4. Everything else is **cloud** and excluded from recovered value by default
   (transparent override allowed per the plan).
5. NULL `billing_base_url` + NULL provider (the 45 older sessions here) →
   **unknown route**: excluded from V, counted in a "unclassified" coverage
   figure, never silently priced.

## 7. Mid-session model switches and missing models (verified: code + data)

- `sessions.model` holds the **first accounted route**: the writer sets it
  when `api_call_count == 0` and keeps the row as-is afterwards ("one row
  cannot represent mixed usage" — `hermes_state_usage.py` comment). It is
  *not* the last model, and *not* a per-token attribution.
- **`session_model_usage` is the per-model source of truth**: per-call
  deltas are keyed by the live `(model, provider, base_url, mode, task)`
  (issue #51607). The collector's per-model breakdown must come from this
  table, with `sessions.model` only as a fallback when a session has no
  model-usage rows.
- On this host 318 model-usage rows > 205 sessions (multi-model sessions
  exist). `model IS NULL` count in `sessions`: 0 (the writer backfills from
  the first accounted usage; placeholder rows may still be NULL — the
  collector must COALESCE to `'unknown'`, as Activity does).
- A mid-session switch between a local and a cloud model is handled by
  pricing each `session_model_usage` row with **its own** route
  classification. This is why ROI's pricing layer is per-model-row, not
  per-session, even though the MVP default (main-loop only) can start from
  `sessions` rows: the moment a session mixes routes, `sessions` counters
  are a blended total and the per-model table is required for a correct V.
  **MVP rule:** if a selected-profile session mixes local and cloud
  model-usage rows, price its local rows individually and mark the session
  "mixed-route" in the audit note; do not apply the session-level blended
  counters to the local rate card.

## 8. Time, time zones, boundaries (verified: code + data)

- `started_at` is a **unix epoch REAL in absolute time** (UTC-based). No
  timezone is stored. `date(started_at,'unixepoch','localtime')` is how
  Activity buckets days — i.e. the *machine's* local timezone. Host here:
  UTC+08. The UI must state the display rule ("days shown in <tz>") and the
  `start_at` setting is a timezone-aware timestamp normalized to epoch.
- Range filters (matching Activity): `started_at >= since AND started_at < until`
  — **inclusive lower, exclusive upper**. A session starting exactly at
  `start_at` is included (plan test case).
- Session attribution: MVP attributes the whole session to its `started_at`
  (Activity's rule), with the disclosed caveat that long sessions straddling
  the boundary are all-or-nothing. Per-turn timestamps exist in
  `session_model_usage.first_seen/last_seen` (per route) and `messages`
  (forbidden to read) — a future refinement, not MVP.
- Forecast anchor `as_of` is a fixed absolute timestamp chosen at refresh;
  countdown and projected date must derive from the same `as_of`.

## 9. Profile routing (verified: code + docs + smoke test)

- `get_hermes_home()` = context-local override → `HERMES_HOME` env → platform
  default. **Danger (code warning, issue #18594):** a process whose
  `HERMES_HOME` is unset/mismatched silently uses the *default* profile home.
  The ROI collector therefore **never** resolves the target from the
  process's own `HERMES_HOME`; it takes an explicit `(hermes_root, profile_name)`.
- Resolution contract (using core helpers' semantics):
  - `profile_name == "default"` → home = `<hermes_root>` itself.
  - else → home = `<hermes_root>/profiles/<name>`; must exist and carry at
    least one identity marker (`config.yaml`, `.env`, `SOUL.md`,
    `profile.yaml`, `auth.json`, `state.db` — profiles doc). Name must not
    start with `.` and must contain no path separator (no traversal).
  - `hermes_root` = the machine's default Hermes root (e.g. `~/.hermes`),
    discoverable from the running gateway's environment; in the desktop
    backend it is the gateway process's resolved default root, not the
    window's active profile.
- **P0 Q9 answered (smoke-tested):** a process with
  `HERMES_HOME=~/.hermes/profiles/roi-dev` can open and query
  `~/.hermes/state.db` (the default profile) in `mode=ro` without touching
  it — see `tests/test_activity_reader.py::test_cross_profile_read_only`.
  No gateway restart, no Activity-plugin dependency.
- Alternative supported pattern (Activity's own): the desktop page shells out
  to `hermes --profile <p> activity summary --json` via the gateway
  `cli.exec` RPC (fresh process, correct `HERMES_HOME`). ROI does not need
  this for read-only aggregates, but the CLI path remains the fallback if a
  future read requires core in-process APIs.
- `host.profileRoutes()` (SDK) supplies `{connectionId, mode: local|remote,
  profile, targetProfile}` to the UI for the profile picker; `remote`
  profiles are out of MVP scope (no local file access) — the picker must
  disable them with a visible reason.

### 9a. Global scope (owner decision D-001, 2026-11-02)

- ROI's primary scope is **machine-global**:
  `summarize_global(hermes_root, since, until, allowlist)` enumerates
  `<root>/state.db` (→ `"default"`) plus `<root>/profiles/<name>/state.db`
  for every live profile (identity-marker gated) and folds all stores into
  one `Summary(profile_name="all", profiles=[...])`. A store with zero rows
  in range is a valid contribution, not an error (empty-store edge case,
  FINDINGS §5). The desktop page requests `scope=all` and never re-keys on
  the active profile tab.
- Live-host acceptance (FINDINGS §2, 2026-11-02): **9 stores, all schema
  v32, identical 65-column `sessions` sets, one empty store**
  (`jev-local-executor`). Structural live test:
  `tests/test_activity_reader.py::LiveGlobalSmokeTest`.
- The in-row `profile_name` is a redundant label; the global `profiles`
  list is derived from **directories**, never from the in-row label
  (FINDINGS §4).

### 9b. Backend mount on this host (verified 2026-11-02)

- Topology: **one default-profile multiplexer gateway** (single PID) serves
  all 9 profiles; shared listener `:8642` (Tailscale) + `:57399`
  (127.0.0.1 API, per-connection token gate). Launch scope = `~/.hermes`.
- Install: unified package at `~/.hermes/plugins/hermes-roi/` (host scope —
  the desktop app is app-level; one install is visible in every profile
  window).
- Enablement: `hermes-roi` appended to the **default** profile's
  `plugins.enabled` via `hermes --profile default config set` (2026-11-02,
  official CLI path).
- **Agent-executed restarts are hard-blocked** by the gateway lifecycle
  guard (terminal + execute_code + cron layers; SIGTERM-respawn-loop hazard,
  `cron/lifecycle_guard.py`). The restart is an owner-run step from a
  separate shell: `hermes --profile default gateway restart` (D-010/D-014).
- Mount verification (D-015): the backend is **lazily mounted** on the
  first desktop request (module `hermes_dashboard_plugin_hermes-roi`,
  `web_server_plugin_profiles.py`) — v0.22.5 logs NO line on successful
  plugin load (confirmed: zero lines for home-dashboard/hermes-activity
  after the 2026-11-01 21:44 start). CLI signals: discovery via
  `hermes plugins list`; freshness (last `Gateway control socket
  listening` vs install mtime); absence of import failure in
  `gateway.error.log`. Checked by `scripts/progress-monitor.sh` and the
  30-minute cronjob (D-004). (An earlier claim that `Plugin <id>:` log
  lines were the mount evidence is REFUTED — D-015.)

## 10. Cost fields (verified: code + data)

- Writer precedence: `actual_cost_usd` wins; Activity displays
  `COALESCE(actual_cost_usd, estimated_cost_usd)`.
- `cost_status` (core Literal): `actual` (provider-reported), `estimated`
  (model card), `included` (subscription — "no provider invoice"),
  `unknown`. Local sessions on this host: `actual = estimated = 0.0`,
  status `unknown`/NULL.
- **ROI must not treat stored cost as savings.** The cloud-equivalent value
  is a *hypothetical benchmark* computed from user-configured rate cards;
  stored cost fields are audit/display context only (e.g. "what this
  session actually cost in the cloud" for cloud sessions, shown in the
  methodology panel, never summed into recovered hardware).

## 11. Observed edge cases and required behavior

| Case | Observed? | Required behavior |
|---|---|---|
| Zero-token sessions (pre-first-call placeholders, dead sessions) | 45 of 205 | Count as 0; do not crash; exclude from "active sessions" in coverage notes |
| Negative counters | none (writer clamps) | Defensively `COALESCE(MAX(x,0),0)` anyway |
| Missing `api_call_count` on old schemas | guarded in Activity (`PRAGMA table_info`) | Collector probes columns once; optional columns degrade to 0/NULL |
| `model` NULL | 0 (writer backfills) | COALESCE `'unknown'`, classify as unknown route |
| Live WAL growth during read | yes (observed) | Snapshot semantics are fine; re-query on refresh; short statement time |
| Dangling `parent_session_id` (FK not enforced by SQLite) | possible | Parent lookup is display-only; never required for correctness |
| `hidden`/`archived` sessions | flags exist | Included by default (they are real usage); document in methodology |
| `source = 'subagent'` | 3 rows | Same accounting as `parent_session_id` children; no special pricing |

## 12. Schema-version compatibility plan

- Read `schema_version` on connect (currently `32`). Record it in every API
  response envelope (`schema_version`, `hermes_version` if available) so a
  bad number is auditable.
- **Required columns** (collector refuses to run without, with a clear
  "please upgrade Hermes" error): `id, source, model, parent_session_id,
  started_at, input_tokens, output_tokens, cache_read_tokens,
  cache_write_tokens, reasoning_tokens, billing_provider, billing_base_url`.
- **Optional columns** (probe via `PRAGMA table_info`, degrade gracefully):
  `billing_mode, estimated_cost_usd, actual_cost_usd, cost_status,
  cost_source, pricing_version, api_call_count, message_count,
  tool_call_count, ended_at, last_activity_at, profile_name`.
- `session_model_usage`: required for P1 per-model pricing; optional in P0
  (fallback: session-level counters). If absent, mark data coverage
  "session-level only".
- Unknown future columns: ignored. Unknown missing optional columns: logged
  to the audit note, never fatal.

## 13. Known unknowns (must be resolved before P1 billing logic)

1. **ASSUMED:** Anthropic `output_tokens` includes extended-thinking tokens
   (so thinking is never separately billable on that wire for ROI defaults).
   Needs a provider-doc citation before any "bill reasoning separately"
   option is offered for Anthropic routes.
2. Per-turn timestamps for boundary attribution (would need `messages` table
   — currently forbidden by the no-raw-content rule; `session_model_usage`
   `first_seen/last_seen` is a partial, allowed alternative).
3. Whether a desktop *plugin backend* can be launched per-profile or always
   runs in the gateway's own profile context — resolved in practice by the
   collector's explicit `(root, profile)` contract (§9); re-verify at T03
   when the real `plugin_api.py` mounts.
4. Remote profiles (`mode: "remote"` in `profileRoutes()`): access path
   unknown (likely `host.requestProfile` against a remote CLI); out of MVP.
5. The one `openai-codex`-routed Qwen session (§6): whether it was a
   user-configured route or a fallback artifact is unknown; either way it
   must be priced as cloud (rule holds).

## 14. Product-scope decisions (2026-11-02)

Owner and agent decisions that changed this contract's scope are logged in
`docs/DECISIONS.md`: **D-001** global scope, **D-002** user-declared local
models (tick-list primary, loopback a hint), **D-012** `/summary`
contract, **D-013** allowlist storage, **D-010/D-014** restart policy.
This section exists so the contract and the decision log cross-reference.
