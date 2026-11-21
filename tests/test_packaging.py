"""Packaging guard: the plugin root must load as a directory plugin.

The gateway's directory-plugin loader (hermes_cli.plugins_loader,
v0.22.5) imports a plugin dir as ``hermes_plugins.<slug>`` and REQUIRES a
top-level ``__init__.py`` exposing ``register(ctx)`` — verified 2026-11-04
from source (``No __init__.py in <dir>`` at plugins_loader.py:816,
"no register() function" at :617). This test pins that contract at the
repo level so a future restructure cannot silently break gateway
discovery.
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_root_module(name: str):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot create module spec for {ROOT / '__init__.py'}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackagingTest(unittest.TestCase):
    def test_top_level_init_present(self):
        self.assertTrue(
            (ROOT / "__init__.py").is_file(),
            "plugin root must have a top-level __init__.py "
            "(directory-plugin contract, plugins_loader.py:816)")

    def test_init_imports_and_exposes_register(self):
        module = _load_root_module("hermes_roi_packaging_probe")
        register = getattr(module, "register", None)
        self.assertTrue(
            callable(register),
            "plugin __init__.py must expose a callable register(ctx)")

    def test_register_is_clean_noop(self):
        class _StubCtx:
            def __getattr__(self, name):
                raise AssertionError(
                    f"v1 register must be a no-op — it called ctx.{name}")

        module = _load_root_module("hermes_roi_packaging_probe2")
        module.register(_StubCtx())  # must not raise, must not touch ctx


if __name__ == "__main__":
    unittest.main()
