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


def test_instalador_roda_sem_terminal():
    """`farol update` chama o install.sh com a saída capturada — sem tty.

    Regressão real: `uv venv` sobre um `.venv` existente pergunta se pode
    substituí-lo. Sem terminal ele não pergunta, sai com erro, o `set -e` aborta
    o instalador em 1/5 e o atalho do sistema — com os ícones — nunca é
    atualizado. Era exatamente o que `_refresh_system_shortcut` existia para
    fazer, e não fazia em nenhuma máquina que já tivesse o ambiente criado.
    """
    script = Path(__file__).resolve().parents[1] / "install.sh"
    chamadas = [
        linha.strip()
        for linha in script.read_text(encoding="utf-8").splitlines()
        if linha.strip().startswith("uv venv")
    ]

    assert chamadas, "o instalador deixou de criar o ambiente com uv"
    for chamada in chamadas:
        assert "--allow-existing" in chamada or "--clear" in chamada, (
            f"`{chamada}` trava esperando resposta quando o ambiente já existe"
        )


def test_branch_de_trabalho_nao_recebe_main(tmp_path, clone):
    """Regressão: estando numa branch de trabalho, o update não pode puxar main para dentro dela."""
    origin = tmp_path / "origin.git"
    (origin / "farol" / "__init__.py").write_text('__version__ = "1.1.0"\n', encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "--quiet", "-m", "bump versao")
    _git(clone, "switch", "--quiet", "-c", "feat/trabalho")
    antes = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout

    resultado = selfupdate.run(reinstall=False)

    assert resultado == {"status": "other_branch", "branch": "feat/trabalho", "default": "main"}
    depois = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    assert antes == depois
    assert (clone / "farol" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "1.0.0"\n'


def test_head_solto_nao_atualiza(clone):
    _git(clone, "checkout", "--quiet", "--detach")

    resultado = selfupdate.run(reinstall=False)

    assert resultado["status"] == "other_branch"
    assert resultado["branch"] == "(HEAD solto)"


def test_aviso_quando_o_servidor_em_execucao_e_de_outra_versao(monkeypatch, capsys):
    from farol import __main__ as cli
    from farol import launcher

    monkeypatch.setattr(launcher, "running_version", lambda port: "1.1.0")
    cli._avisa_servidor_antigo("1.2.0")
    assert "ainda é a versão 1.1.0" in capsys.readouterr().out


def test_sem_aviso_quando_o_servidor_ja_e_o_da_versao_nova(monkeypatch, capsys):
    from farol import __main__ as cli
    from farol import launcher

    monkeypatch.setattr(launcher, "running_version", lambda port: "1.2.0")
    cli._avisa_servidor_antigo("1.2.0")
    assert capsys.readouterr().out == ""


def test_sem_aviso_quando_nenhum_servidor_responde(monkeypatch, capsys):
    from farol import __main__ as cli
    from farol import launcher

    monkeypatch.setattr(launcher, "running_version", lambda port: None)
    cli._avisa_servidor_antigo("1.2.0")
    assert capsys.readouterr().out == ""
