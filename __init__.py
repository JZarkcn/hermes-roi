"""hermes-roi: Return on Intelligence — ROI dashboard for local AI inference.

This package is a host-level unified plugin (D-011):

  * the desktop page lives in ``desktop/plugin.js`` (app-level: one copy
    for every profile window);
  * the read-only backend lives in ``dashboard/plugin_api.py`` and is
    LAZILY mounted by the gateway web server on the first desktop request
    (module ``hermes_dashboard_plugin_hermes_roi``), gated by the
    ``plugins.enabled`` allow-list of the config the mounting gateway reads;
  * the collectors and economics live in ``roi/`` (pure stdlib, SQLite
    ``mode=ro`` only, never reads message content).

This module is the directory-plugin entry point required by
``hermes_cli.plugins_loader``: a directory plugin is imported as
``hermes_plugins.<slug>`` and must expose a ``register(ctx)`` function
(verified 2026-11-04 against v0.22.5 — ``plugins_loader.py`` raises
``No __init__.py in <dir>`` otherwise). The v1 plugin surface is the
lazy-mounted dashboard backend above, so ``register`` is an intentional
no-op that keeps the load clean.
"""
from __future__ import annotations


def register(ctx) -> None:
    """No-op on purpose: v1 registers no CLI/slash commands or tools.

    The plugin's live surface is the lazy-mounted dashboard backend (see
    module docstring). This function exists so the directory-plugin loader
    imports the package cleanly instead of failing with
    "no register() function" (plugins_loader.py:617).
    """
    return None
