"""Abertura do aplicativo: sobe o servidor local e abre a janela.

É o que o atalho do menu executa em qualquer sistema. Antes isso era um script
de shell, o que restringia o Farol ao Linux; aqui a mesma lógica roda em Linux,
macOS e Windows, com o navegador em modo aplicativo quando existe um instalado.

Sequência:

1. Se já houver um servidor de pé na porta, reaproveita — abrir o app duas vezes
   não sobe dois processos.
2. Senão, inicia `farol servir` em segundo plano e espera `/saude` responder.
3. Dispara uma coleta (o servidor recusa sozinho se a última foi há pouco).
4. Abre a janela.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import db

STARTUP_TIMEOUT_SECONDS = 25.0
POLL_INTERVAL_SECONDS = 0.25

# navegadores baseados em Chromium abrem uma janela sem barra de endereço com
# --app=URL, que é o que faz o Farol parecer um aplicativo e não uma aba
APP_MODE_BROWSERS = (
    "omarchy-launch-webapp",  # Omarchy: já resolve classe de janela e ícone
    "chromium", "chromium-browser", "google-chrome-stable", "google-chrome",
    "brave-browser", "brave", "microsoft-edge-stable", "microsoft-edge", "vivaldi",
    "thorium-browser",
)

WINDOWS_APP_BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
)

MACOS_APP_BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def log_path() -> Path:
    return db.home() / "server.log"


def is_running(port: int, timeout: float = 1.0) -> bool:
    """Já existe um Farol atendendo nesta porta?"""
    try:
        with urllib.request.urlopen(f"{base_url(port)}/saude", timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")).get("app") == "farol"
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return False


def _detached_flags() -> dict:
    """Como soltar o servidor do terminal que o chamou, em cada sistema."""
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: sem console piscando
        return {"creationflags": 0x00000008 | 0x00000200}
    return {"start_new_session": True}


def start_server(port: int, host: str = "127.0.0.1") -> subprocess.Popen | None:
    """Sobe `farol servir` em segundo plano, com log no diretório de dados."""
    log = log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n--- {stamp} iniciando farol na porta {port}\n")
    handle = log.open("a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-m", "farol", "servir", "--port", str(port), "--host", host],
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        cwd=str(Path(__file__).resolve().parent.parent),
        **_detached_flags(),
    )


def wait_until_up(port: int, timeout: float = STARTUP_TIMEOUT_SECONDS) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running(port):
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return False


def trigger_collect(port: int) -> None:
    """Pede uma coleta. O servidor recusa sozinho dentro da janela de descanso."""
    request = urllib.request.Request(f"{base_url(port)}/coleta", method="POST", data=b"")
    # coleta é bônus na abertura, nunca motivo para não abrir a janela
    with contextlib.suppress(urllib.error.URLError, OSError):
        urllib.request.urlopen(request, timeout=5).close()


def _app_mode_command(url: str) -> list[str] | None:
    """Comando que abre a URL como janela de aplicativo, se houver navegador."""
    if os.name == "nt":
        for candidate in WINDOWS_APP_BROWSERS:
            if Path(candidate).is_file():
                return [candidate, f"--app={url}"]
        return None
    if sys.platform == "darwin":
        for candidate in MACOS_APP_BROWSERS:
            if Path(candidate).is_file():
                return [candidate, f"--app={url}"]
        return None
    for name in APP_MODE_BROWSERS:
        found = shutil.which(name)
        if not found:
            continue
        if name == "omarchy-launch-webapp":
            return [found, url]
        return [found, f"--app={url}", "--class=Farol", "--name=Farol"]
    return None


def open_window(port: int) -> str:
    """Abre a janela do app. Devolve como foi aberta, para a mensagem final."""
    url = base_url(port)
    command = _app_mode_command(url)
    if command:
        try:
            subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **_detached_flags(),
            )
            return "janela"
        except OSError:
            pass  # navegador sumiu entre o which e o exec: cai para o padrão

    import webbrowser

    return "navegador" if webbrowser.open(url) else "nenhum"


def launch(port: int, host: str = "127.0.0.1", open_browser: bool = True) -> int:
    """Fluxo completo da abertura. Devolve o código de saída do processo."""
    fresh = not is_running(port)
    if fresh:
        start_server(port, host)
        if not wait_until_up(port):
            print(
                f"O servidor não respondeu em {STARTUP_TIMEOUT_SECONDS:.0f}s.\n"
                f"Veja o log em {log_path()}",
                file=sys.stderr,
            )
            return 1

    trigger_collect(port)

    if not open_browser:
        print(f"Farol rodando em {base_url(port)}")
        return 0

    how = open_window(port)
    if how == "nenhum":
        print(f"Nenhum navegador encontrado. O Farol está rodando em {base_url(port)}")
    return 0
