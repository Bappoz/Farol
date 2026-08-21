"""farol update — comparação com o remoto e pull em modo editável."""

import subprocess
from pathlib import Path

import pytest

from farol import selfupdate


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _repo_com_um_commit(path: Path, versao: str) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "--quiet", "--initial-branch=main")
    _git(path, "config", "user.email", "farol@teste.local")
    _git(path, "config", "user.name", "Farol Teste")
    (path / "farol").mkdir()
    (path / "farol" / "__init__.py").write_text(f'__version__ = "{versao}"\n', encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "--quiet", "-m", "inicial")
    return path


@pytest.fixture
def clone(tmp_path, monkeypatch) -> Path:
    """Um repo 'origin' e um clone dele — o clone é onde farol está 'instalado'."""
    origin = _repo_com_um_commit(tmp_path / "origin.git", "1.0.0")
    _git(origin, "config", "receive.denyCurrentBranch", "updateInstead")

    local = tmp_path / "local"
    subprocess.run(
        ["git", "clone", "--quiet", str(origin), str(local)], check=True, capture_output=True, text=True
    )
    monkeypatch.setattr(selfupdate, "APP_DIR", local)
    return local


def test_sem_git_nao_tenta_atualizar(tmp_path, monkeypatch):
    monkeypatch.setattr(selfupdate, "APP_DIR", tmp_path)

    resultado = selfupdate.run()

    assert resultado["status"] == "no_git"


def test_arvore_suja_nao_atualiza(clone):
    (clone / "farol" / "__init__.py").write_text('__version__ = "1.0.0"  # editado\n', encoding="utf-8")

    resultado = selfupdate.run()

    assert resultado["status"] == "dirty"


def test_ja_atualizado_nao_mexe_em_nada(clone):
    resultado = selfupdate.run()

    assert resultado == {"status": "up_to_date", "versao": "1.0.0"}


def test_puxa_versao_nova_do_remoto(tmp_path, clone):
    origin = tmp_path / "origin.git"
    (origin / "farol" / "__init__.py").write_text('__version__ = "1.1.0"\n', encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "--quiet", "-m", "bump versao")

    resultado = selfupdate.run(reinstall=False)

    assert resultado["status"] == "updated"
    assert resultado["versao"] == "1.1.0"
    assert (clone / "farol" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "1.1.0"\n'


def test_falha_de_rede_vira_status_error(clone, monkeypatch):
    def fetch_falho(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="não deu para conectar")

    original_git = selfupdate._git

    def git_com_fetch_falho(*args, **kwargs):
        if args and args[0] == "fetch":
            return fetch_falho()
        return original_git(*args, **kwargs)

    monkeypatch.setattr(selfupdate, "_git", git_com_fetch_falho)

    resultado = selfupdate.run()

    assert resultado["status"] == "error"
    assert "conectar" in resultado["detail"]
