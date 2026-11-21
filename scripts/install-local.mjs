// Install hermes-roi as a unified desktop+backend plugin for local dev.
//
//   node scripts/install-local.mjs [--profile <name>] [--enable]
//
// Default target is the HOST (machine) Hermes root — this plugin is a
// host-level unified package: the desktop app is app-level (one root for
// every profile window) and the multiplexer launches from the host scope.
// $HERMES_HOME may point at a profile home; the host root is recovered by
// stripping /profiles/<name> (same rule as dashboard/plugin_api.py).
//
// Layout (per desktop-plugin-sdk docs, "The Python side"):
//
//   <host-root>/plugins/hermes-roi/
//     ├── __init__.py        # directory-plugin entry (loader REQUIRES it; no-op register)
//     ├── plugin.yaml        # agent-plugin manifest (discovery + allow-list)
//     ├── dashboard/         # Python backend → /api/plugins/hermes-roi/
//     │   ├── manifest.json
//     │   └── plugin_api.py
//     ├── desktop/plugin.js  # native page (loaded by the desktop watcher)
//     └── roi/               # read-only collector (imported by the backend)
//
// With --profile <name> the same tree is installed under
// <host-root>/profiles/<name>/plugins/hermes-roi/ instead (per-profile
// agent-plugin scope — D-011 fallback if the multiplexer mounts backends
// from profile configs).
//
// The Python backend is gated separately: plugin_api.py is imported only
// when the plugin is in the `plugins.enabled` allow-list of the config the
// mounting gateway reads. Pass --enable to append it there (idempotent);
// otherwise this script prints the exact line to add.

import { cp, mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const id = "hermes-roi";

// Host root: strip /profiles/<name> from HERMES_HOME when present.
let host = process.env.HERMES_HOME || join(homedir(), ".hermes");
const parts = host.split("/").filter(Boolean);
if (parts.length >= 2 && parts[parts.length - 2] === "profiles") {
  host = "/" + parts.slice(0, -2).join("/");
}

const argv = process.argv.slice(2);
const profileIdx = argv.indexOf("--profile");
const profile = profileIdx >= 0 ? argv[profileIdx + 1] : null;
const enable = argv.includes("--enable");

const base = profile
  ? join(host, "profiles", profile, "plugins", id)
  : join(host, "plugins", id);

await mkdir(base, { recursive: true });
for (const item of ["__init__.py", "plugin.yaml", "dashboard", "desktop", "roi"]) {
  const src = join(root, item);
  if (!existsSync(src)) throw new Error(`missing source: ${src}`);
  await cp(src, join(base, item), { recursive: true, force: true });
}
console.log(`Installed ${id} into ${base}`);
console.log("The desktop plugin watcher should load desktop/plugin.js automatically.");

// --- backend enablement (plugins.enabled in the right config.yaml) ----------
const cfgPath = profile
  ? join(host, "profiles", profile, "config.yaml")
  : join(host, "config.yaml");
let cfg = null;
try {
  cfg = await readFile(cfgPath, "utf8");
} catch {}

const scopeLabel = profile ? `profile '${profile}'` : "default/host";
if (cfg === null) {
  console.log(`\nNo config.yaml at ${cfgPath}; add:`);
  console.log("  plugins:\n    enabled:\n      - hermes-roi");
} else if (new RegExp(`^\\s*-\\s*${id}\\s*$`, "m").test(cfg)) {
  console.log(`\nAlready in plugins.enabled (${scopeLabel}) — restart the gateway to import the backend.`);
} else if (enable) {
  let next;
  if (/^plugins:\s*$/m.test(cfg) && !/enabled:/m.test(cfg)) {
    next = cfg.replace(/^plugins:\s*$/m, `plugins:\n  enabled:\n    - ${id}`);
  } else if (/enabled:\s*\n/m.test(cfg)) {
    next = cfg.replace(/(enabled:\s*\n)/, (m) => `${m}    - ${id}\n`);
  } else {
    next = cfg + `\nplugins:\n  enabled:\n    - ${id}\n`;
  }
  await writeFile(cfgPath, next);
  console.log(`\nAdded '${id}' to plugins.enabled in ${cfgPath} (${scopeLabel})`);
  console.log("Restart the gateway for the backend mount to take effect.");
} else {
  console.log(`\nBackend not yet enabled (${scopeLabel}). Add to ${cfgPath} (then restart the gateway):`);
  console.log(`  plugins:\n    enabled:\n      - ${id}`);
  console.log(`Re-run with --enable to append it automatically.`);
}
