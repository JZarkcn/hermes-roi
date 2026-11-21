# Project Instructions — hermes-roi

This is a long-lived engineering repository. The Hermes profile `roi-dev` uses `SOUL.md` for agent identity; **this file contains project-specific constraints**. Read `ROI_DEVELOPMENT_PLAN.md` for the prioritized implementation plan.

## Canonical user requirements

- Name: `ROI — Return on Intelligence`.
- Standalone native Hermes Desktop community plugin.
- Input: user-selected timestamp, hardware price, currency, cloud benchmark API prices and target Hermes runtime profile/local model allowlist.
- Source: the same underlying, read-only `state.db` activity records as `hermes-activity`; do not take an Activity-plugin dependency unless justified by supported APIs.
- Hero: hardware recovery with 3 decimals, projected break-even date, dramatic but tasteful live countdown, most prominent current 4-tier sarcasm verdict.
- Design: user's Hermes Home/Activity screenshots: dark charcoal, blue highlight, thin gray-blue strokes, small capital labels, compact terminal metrics.
- Home widget: an optional compact ROI tile on the existing community Home Dashboard; integrate through its supported code/maintainer PR path.

## Key math

`Recovery% = 100 * (cloud_equivalent_value - modeled_operating_costs) / hardware_cost`.

`NetROI% = 100 * (cloud_equivalent_value - modeled_operating_costs - hardware_cost) / hardware_cost`.

Use Decimal arithmetic and independently price uncached input, billable output, cache read and cache write. Only count reasoning separately if proven billed separately. Keep source semantics and assumptions auditable in `docs/METHODS.md`.

Projected payback uses recent net savings / calendar day (including inactive days); if pace <=0 or no usable history, return no finite date. Use the same absolute forecast timestamp for the countdown and date.

## Implementation rules

- One reviewed, testable ticket at a time.
- Respect Hermes's current public SDK, not remembered API names or internals.
- Read-only database; parameterized SQL; no raw user messages; no modifying other profiles' state.
- UI must use actual Hermes theme variables wherever feasible, not a large fixed dark-theme stylesheet.
- Ship a self-contained `desktop/plugin.js` ESM distributable; preserve source and build instructions.
- Home Dashboard integration may need a fork/upstream PR. Do not patch its installed widget registry at runtime.
- Store target runtime profile explicitly. `roi-dev` is the development profile, **not the source of the user's historical usage**.
- Public samples must be synthetic and plainly labeled.
- Validate Python tests, UI build/typecheck, plugin installation and catalog validator before declaring ready.

## Suggested directories and durable state

- `roi/`: collectors, pricing, forecasts and tier engine.
- `dashboard/`: backend API namespace when required.
- `src/`: front-end source.
- `desktop/`: shipped ESM artifact.
- `tests/fixtures/`: synthetic cases.
- `docs/DATA_CONTRACT.md`: source schema and billing semantics.
- `docs/ARCHITECTURE_DECISIONS.md`: researched architecture choices.
- `docs/PROGRESS.md`: current phase, tickets, test evidence and next actions.

## Progress entry template

```text
Date/time:
Ticket:
Current phase:
Evidence inspected:
Files changed:
Commands executed + results:
What remains uncertain:
Commit:
Next ticket:
```

## Critical references

- https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk
- https://hermes-agent.nousresearch.com/docs/user-guide/profiles
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
- https://github.com/hassan-kamel/hermes-activity
- https://github.com/albertocvrrbs/hermes-home-dashboard

## Agent workflow and boundaries

*(Moved from the `roi-dev` profile's SOUL.md on 2026-11-05, so the SOUL keeps only identity and voice.)*

### Session start
- Confirm the current repository and Git state.
- Read this file, then `docs/PROGRESS.md` (if present) and the current phase of `ROI_DEVELOPMENT_PLAN.md`.
- Identify exactly one bounded ticket to complete next, with its acceptance test.

### Per ticket
1. Inspect the narrow set of relevant files and the current public SDK API.
2. Write a 3–6 line implementation plan.
3. Change the smallest practical area of the codebase.
4. Run unit tests/typechecks or a relevant integration smoke test.
5. Fix failures or record a concrete blocker with evidence.
6. Update `docs/PROGRESS.md` with decisions, exact tests and results, and the next ticket.
7. Commit the verified change with a focused conventional commit message when the repo is ready.
8. Report a short Chinese summary: 完成 / 验证 / 风险 / 下一个任务.

Do not silently substitute fabricated sample data for live integration.

### Approval boundaries
- Allowed: read docs and project files, add/change files within this repository, run local tests and builds, make local Git commits.
- Requires explicit owner approval: removing other projects' files, overwriting installed plugins, changing system settings, installing unexpected system packages, publishing to GitHub, opening external PRs, sending telemetry anywhere.
- Keep secrets in environment configuration, never in code, commits, logs or reports.
- A Hermes profile is not a security sandbox: act as if you have broad filesystem rights and voluntarily stay within this repository.

### Engineering standards
- Backend: Python, standard library where practical; SQLite `mode=ro`; parameterized SQL; `Decimal` for currency; pure, documented computation helpers.
- Frontend: Hermes Desktop plugin SDK, native UI components and theme tokens, responsive layout, `prefers-reduced-motion` support; no surprise direct app-internal imports.
- Visual language: restrained charcoal, blue accents, low-glare surfaces, thin borders, compact cards, readable monospace metrics. Humor lives in the tier label and understated copy, not visual clutter.
- Tests: normal, empty, malformed, cache-heavy, mixed local/cloud, all four tiers, near/far payback and timezone cases.
- Architecture: core calculation independent of both the Desktop page and the Home Dashboard UI.
- Packaging: reproducible builds, license attribution, catalog validation, clear install/uninstall instructions.

### Product rules
- Hero recovery % is displayed to exactly three decimal places (formula: see Key math).
- Exactly four verdict tiers: LV1 paid off, LV2 within 90 days, LV3 within five years, LV4 farther away or no positive trajectory. Missing history is an onboarding/unknown state.
- Never count a cloud-hosted model as local inference just because its name contains qwen or another local model family.
- Never count reasoning or cache tokens twice. If source semantics are unclear, mark data coverage unknown and write an audit note before charging it.
- The user-selected effective start time and selected runtime profile are always explicit settings.
- The Home Dashboard widget is optional and must not block the standalone plugin's release.
