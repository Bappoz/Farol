import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Cada teste roda com um banco novo em diretório temporário."""
    monkeypatch.setenv("FAROL_HOME", str(tmp_path / "farol"))
    monkeypatch.setenv("FAROL_REQUEST_DELAY", "0")
    from farol import collect, db

    db.bootstrap()
    collect.REQUEST_DELAY_SECONDS = 0.0
    collect._state.update(
        running=False, started_at=None, finished_at=None, report=None, error="", skipped=""
    )
    yield tmp_path
    wait_for_collect()


def wait_for_collect(timeout: float = 10.0) -> dict:
    """Espera a coleta em segundo plano terminar (os testes não podem vazar thread)."""
    import time

    from farol import collect

    deadline = time.monotonic() + timeout
    while collect._state["running"] and time.monotonic() < deadline:
        time.sleep(0.02)
    return collect.status()


@pytest.fixture
def fixtures() -> Path:
    return Path(__file__).resolve().parent / "fixtures"
