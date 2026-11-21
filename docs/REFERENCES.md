# References — hermes-roi

Every source actually inspected for P0, with the exact version/commit/URL used.
Re-verify before relying on any of these: Hermes updates rapidly.

Inspected: 2026-11-01 (UTC+08) on the `roi-dev` profile.

## 1. Installed software (this machine)

| Item | Version / commit | Path |
|---|---|---|
| Hermes Agent | `v0.22.5 (2026.9.24) stable`, git commit `bf0203a794a07aac3ff764972ab9087baa4e4f4e` (2026-10-22), Python 3.14.9 | `~/.hermes/hermes-agent` (install method: git) |
| `hermes-activity` plugin | `v0.2.2`, git commit `0335e954b3ab00193720205fcdab7e10ae1194f9` (2026-10-15, "Merge pull request #6 … provider-history"), license MIT, `requires_hermes: >=0.21.7` | `~/.hermes/plugins/hermes-activity` |
| `home-dashboard` plugin (backend) | `1.5.0` (`dashboard/manifest.json`); frontend "ships separately" (installed artifact is built, no `src/`) | `~/.hermes/plugins/home-dashboard` |
| Installed desktop plugins (app-level, all profiles) | `hermes-activity`, `hermes-home-dashboard`, `splash-monitor` | `~/.hermes/desktop-plugins/` |
| `state.db` schema version (default profile) | `32` (`schema_version` table) | `~/.hermes/state.db` (150 MB, 205 sessions at audit time) |
| `state.db` schema version (roi-dev profile) | `32` (same install) | `~/.hermes/profiles/roi-dev/state.db` |

## 2. Core Hermes source files (installed copy, commit above)

| File | Why it matters |
|---|---|
| `agent/usage_pricing.py` | `CanonicalUsage` dataclass + `normalize_usage()` — **the** definition of the five token buckets and provider usage shapes. `prompt_tokens = input + cache_read + cache_write` proves buckets are disjoint. |
| `hermes_state_usage.py` | `SessionUsageMixin`: how `sessions` counters are written (delta vs absolute paths), `session_model_usage` upsert, first-accounted-route rule for `sessions.model`, auxiliary-usage separation (`task != ''`). |
| `hermes_constants.py` | `get_hermes_home()` (context override → `HERMES_HOME` env → platform default), the issue-#18594 fallback warning, `named_profile_home()` / `profile_name_for_home()` helpers, profile identity marker files. |
| `gateway/session_usage.py` | Viewer-side projection of the same counters (context for what Activity/Desktop display). |
| `agent/codex_runtime.py` | Example call site: `queue_token_counts(session_id, **counts)` per API call. |

## 3. `hermes-activity` plugin source (installed copy, v0.2.2)

| File | Why it matters |
|---|---|
| `activity_data.py` | Read-only reader: `mode=ro` URI connect, `db_path() = get_hermes_home()/state.db`, day bucketing `date(started_at,'unixepoch','localtime')`, the 5-bucket `_TOKENS` sum, `COALESCE(actual_cost_usd, estimated_cost_usd)`, `api_call_count` schema-drift guard. |
| `commands.py` | Desktop data path: `hermes --profile <p> activity summary --json` through the gateway `cli.exec` RPC — fresh process per target profile. |
| `src/sdk.d.ts` | Real-world minimal type declarations for `@hermes/plugin-sdk` (host.state, profileRoutes, requestProfile, areas, useQuery, storage). |
| `plugin.yaml` | Plugin manifest shape v2 (`manifest_version: 2`, `api_version: 1`, `config_schema`, `provides_commands`). |
| `package.json` / `tsconfig.json` | Build chain: `tsc` → `scripts/bundle-desktop-plugin.ts` → `desktop/plugin.js` ESM; typecheck and `hermes plugins validate .`. |

## 4. Official documentation (fetched 2026-11-01)

| Doc | URL |
|---|---|
| Desktop Plugin SDK (`@hermes/plugin-sdk`) | https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk |
| Profiles | https://hermes-agent.nousresearch.com/docs/user-guide/profiles |
| Plugin catalog submission | https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission (URL from plan; content not yet needed for T01/T02) |
| SDK type source (per sdk.d.ts comment) | `apps/desktop/src/sdk/index.ts` in the hermes-agent repo |

Key SDK facts used (from the desktop-plugin-sdk page + installed `sdk.d.ts`, cross-checked):

- Desktop plugin = one ESM file default-exporting `HermesPlugin { id, name?, defaultEnabled?, capabilities?, register(ctx) }`; desktop plugins live in app-level `$HERMES_HOME/desktop-plugins/<id>/plugin.js` (one root for every profile) or ship as a unified package with `desktop/plugin.js` + `dashboard/manifest.json`.
- Contribution areas: `ROUTES_AREA`, `SIDEBAR_NAV_AREA`, `PALETTE_AREA`, `STATUSBAR_AREAS.left/right`, `PANES_AREA`, `SETTINGS_PLUGINS_AREA` (via `ctx.registerSettingsPage`), …
- `ctx.storage.get/set` (plugin-scoped string storage), `ctx.rest` (scoped backend namespace), `host.state.profile`, `host.profileRoutes()`, `host.requestProfile(route, method, params)`, `host.profiles`, `host.navigate`.
- Backend `dashboard/manifest.json` (`{"name", "api": "plugin_api.py"}`) mounts routes at `/api/plugins/<id>/` **inside the gateway process**; backend code may import hermes-agent modules directly. Routes mount at gateway startup — a restart is needed to add/remove routes.
- Theme: use `var(--ui-*)` theme variables, never hardcoded colors.
- Validation: `hermes plugins validate /path --install-deps`.
- Pitfall from docs: `ctx.socket` is a no-op on OAuth remotes → polling fallback required (MVP polls `/summary`).

## 5. Upstream repositories (links only, not cloned in P0)

| Repo | Role |
|---|---|
| https://github.com/hassan-kamel/hermes-activity | Data-reader reference (MIT). Installed copy inspected instead of cloning. |
| https://github.com/albertocvrrbs/hermes-home-dashboard | Home Dashboard upstream. Installed copy has **no `src/`** and a fixed widget set (`ascii, clock, gateway, tokens, host, matrix, sessions, cron, errors`) → **no verified third-party widget registration API**; P3 must go through its source repo (`src/home/widgets/registry.tsx` per plan) or an upstream extension API. |

## 6. Local environment facts

- Host: macOS 27.x, user `<developer-user>`, machine timezone `UTC+08` (Asia/Shanghai).
- Default profile home: `~/.hermes` (real `state.db`, live — writes observed during audit).
- Dev profile home: `~/.hermes/profiles/roi-dev` (dev profile; **not** the usage source).
- Local inference endpoints observed in the default profile: `http://127.0.0.1:1234/v1` (LM Studio), `http://127.0.0.1:8000/v1` (custom local Qwen).
- Cloud routes observed: `openai-codex` → `https://chatgpt.com/backend-api/codex` (`billing_mode`: `subscription_included` / `codex_responses`, `cost_status: included`).
