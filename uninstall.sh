#!/usr/bin/env bash
# Remove o atalho, o ícone e o ambiente virtual. NÃO apaga seus dados.

set -euo pipefail

APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/farol"

rm -f "$APPS_DIR/farol.desktop" "$ICON_DIR/farol.svg" "$HOME/.local/bin/farol"
rm -rf "$APP_DIR/.venv"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" || true

echo "Atalho e ambiente removidos."
echo "Seus dados continuam em $DATA_DIR (apague à mão se quiser)."
