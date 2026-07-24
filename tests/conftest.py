"""Shared pytest fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def _clear_smart_okf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from a developer's exported `SMART_OKF_*` environment.

    Config resolution reads these (`SMART_OKF_CONFIG` even wins over a per-root
    `.smart-okf/config.yaml` in `load_config`, and `SMART_OKF_LLM_*` feed pydantic-settings),
    so a shell with any of them exported would make config/load tests resolve the developer's
    values instead of what the test set up. Tests that want a specific var set it themselves
    via `monkeypatch.setenv` after this fixture has cleared the namespace.
    """
    for key in [k for k in os.environ if k.startswith("SMART_OKF_")]:
        monkeypatch.delenv(key, raising=False)
