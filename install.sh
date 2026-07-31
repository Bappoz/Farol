#!/usr/bin/env bash
# Instala o Farol como aplicativo do usuário: ambiente Python + atalho no menu.
# Seguro rodar de novo — atualiza o que já existe.

set -euo pipefail

APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
VENV="$APP_DIR/.venv"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
BIN_DIR="$HOME/.local/bin"

say() { printf '\033[1m%s\033[0m\n' "$*"; }

command -v python3 >/dev/null || { echo "python3 não encontrado."; exit 1; }

cd "$APP_DIR"

say "1/4 · ambiente Python"
if command -v uv >/dev/null 2>&1; then
  uv venv "$VENV" >/dev/null
  uv pip install --quiet --python "$VENV/bin/python" -r "$APP_DIR/requirements.txt"
else
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -r "$APP_DIR/requirements.txt"
fi

say "2/4 · banco de dados"
"$VENV/bin/python" -c "from farol import db; db.bootstrap(); print('   ', db.db_path())"

say "3/4 · ícone e atalho do menu"
mkdir -p "$APPS_DIR" "$ICON_DIR" "$BIN_DIR"
cp "$APP_DIR/farol/static/icon.svg" "$ICON_DIR/farol.svg"

cat >"$APPS_DIR/farol.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Farol
GenericName=Central de carreira
Comment=Vagas remotas, pipeline de candidaturas, currículos e roadmap de estudos
Exec=$APP_DIR/bin/farol-app
Icon=farol
Terminal=false
Categories=Office;Development;
Keywords=vagas;emprego;curriculo;carreira;jobs;farol;
StartupNotify=true
StartupWMClass=Farol
EOF

chmod +x "$APP_DIR/bin/farol-app"
ln -sf "$APP_DIR/bin/farol-app" "$BIN_DIR/farol"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" || true

say "4/4 · pronto"
cat <<EOF

  Abra pelo menu do Omarchy (SUPER + espaço) procurando por "Farol",
  ou pelo terminal com o comando: farol

  Coleta sem abrir a janela:  $VENV/bin/python -m farol atualizar
  Banco de dados:             \$XDG_DATA_HOME/farol/farol.db  (~/.local/share/farol)
  Desinstalar o atalho:       $APP_DIR/uninstall.sh

EOF
