"""Autoatualização: o Farol não tem instalador empacotado — quem instala clona
o repositório e roda install.sh. Atualizar é a mesma ideia: buscar o que mudou
no remoto e, se houver algo novo, puxar e reinstalar no mesmo ambiente.

Só funciona quando `farol` roda a partir de um clone git limpo. Executável
avulso (PyInstaller) ou instalação via `pip install` sem `.git` não têm como
se auto-atualizar — o comando avisa e aponta para a página de releases.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_URL = "https://github.com/Bappoz/farol"
APP_DIR = Path(__file__).resolve().parent.parent


def _git(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(APP_DIR), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _default_branch() -> str:
    """Branch que origin/HEAD aponta; cai para 'main' se o clone não sabe."""
    result = _git("symbolic-ref", "refs/remotes/origin/HEAD")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().rsplit("/", 1)[-1]
    return "main"


def _version_from_source() -> str:
    text = (APP_DIR / "farol" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "?"


def _reinstall() -> subprocess.CompletedProcess[str]:
    """Reinstala em modo editável — pega dependência nova que o pull trouxe."""
    uv = shutil.which("uv")
    if uv:
        return subprocess.run(
            [uv, "pip", "install", "--quiet", "--python", sys.executable, "-e", str(APP_DIR)],
            capture_output=True, text=True, timeout=180,
        )
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "-e", str(APP_DIR)],
        capture_output=True, text=True, timeout=180,
    )


def run(*, reinstall: bool = True) -> dict[str, Any]:
    """Verifica e aplica atualização. Nunca levanta — falha vira `status`."""
    if not (APP_DIR / ".git").exists():
        return {"status": "no_git", "detail": str(APP_DIR)}

    status = _git("status", "--porcelain")
    if status.returncode != 0:
        return {"status": "error", "detail": status.stderr.strip() or "git status falhou"}
    if status.stdout.strip():
        return {"status": "dirty"}

    fetch = _git("fetch", "--quiet", "origin")
    if fetch.returncode != 0:
        return {"status": "error", "detail": fetch.stderr.strip() or "git fetch falhou"}

    branch = _default_branch()
    local = _git("rev-parse", "HEAD")
    remote = _git("rev-parse", f"origin/{branch}")
    if local.returncode != 0 or remote.returncode != 0:
        return {"status": "error", "detail": "não deu para comparar HEAD com origin"}

    if local.stdout.strip() == remote.stdout.strip():
        return {"status": "up_to_date", "versao": _version_from_source()}

    pull = _git("pull", "--ff-only", "--quiet", "origin", branch, timeout=60)
    if pull.returncode != 0:
        return {"status": "error", "detail": pull.stderr.strip() or "git pull --ff-only falhou"}

    result: dict[str, Any] = {"status": "updated", "versao": _version_from_source()}
    if reinstall:
        install = _reinstall()
        if install.returncode != 0:
            result["install_detail"] = install.stderr.strip()
    return result
