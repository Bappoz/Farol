# PyInstaller: um executável único do Farol para quem não quer instalar Python.
#
#   pip install -e ".[build]"
#   pyinstaller packaging/farol.spec
#
# O resultado sai em dist/: `farol` (Linux/macOS) ou `farol.exe` (Windows).
# É o mesmo aplicativo — o binário só embute o interpretador e as dependências.
#
# Templates, CSS e catálogos JSON precisam ser declarados: o PyInstaller enxerga
# imports, não arquivos abertos em tempo de execução.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "farol"

datas = [
    (str(PKG / "templates"), "farol/templates"),
    (str(PKG / "static"), "farol/static"),
    (str(PKG / "data"), "farol/data"),
    (str(PKG / "schema.sql"), "farol"),
]

# O uvicorn carrega o ciclo de eventos e os protocolos por nome, em tempo de
# execução, e a própria aplicação é referenciada como a string "farol.app:app".
# Nada disso aparece como import estático: sem declarar aqui, o binário sobe e
# morre no primeiro request.
hiddenimports = [
    *collect_submodules("uvicorn"),
    *collect_submodules("farol"),
    "anyio._backends._asyncio",
]

icon = None
for candidate in ("assets/farol.ico", "assets/farol.png"):
    if (ROOT / candidate).is_file():
        icon = str(ROOT / candidate)
        break

analysis = Analysis(
    # entra por packaging/entry.py, não por farol/__main__.py: o PyInstaller roda
    # o script de topo sem pacote pai, e a importação relativa falharia
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest", "pydoc_data"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="farol",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=icon,
)
