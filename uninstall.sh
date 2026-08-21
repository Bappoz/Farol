#!/usr/bin/env bash
# Remove atalho, comando e ambiente virtual do Farol.
#
# Seus dados NÃO são apagados: banco e currículos continuam onde estão.
# Para apagá-los também, use --com-dados (a confirmação é pedida).

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${FAROL_BIN_DIR:-$HOME/.local/bin}"
WITH_DATA=0

[ "${1:-}" = "--com-dados" ] && WITH_DATA=1

data_dir() {
  if [ -x "$APP_DIR/.venv/bin/python" ]; then
    "$APP_DIR/.venv/bin/python" -c 'from farol import db; print(db.home())' 2>/dev/null && return
  fi
  case "$(uname -s)" in
    Darwin) echo "$HOME/Library/Application Support/Farol" ;;
    *) echo "${XDG_DATA_HOME:-$HOME/.local/share}/farol" ;;
  esac
}

DATA_DIR="$(data_dir)"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"

rm -f "$APPS_DIR/farol.desktop" "$BIN_DIR/farol" "$ICON_ROOT/scalable/apps/farol.svg"
for size in 16 32 48 64 128 256; do
  rm -f "$ICON_ROOT/${size}x${size}/apps/farol.png"
done
rm -rf "$HOME/Applications/Farol.app" "$APP_DIR/.venv"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo "Atalho, comando e ambiente removidos."

if [ "$WITH_DATA" = "1" ]; then
  echo
  echo "Isto apaga PARA SEMPRE o banco e os currículos em:"
  echo "  $DATA_DIR"
  printf 'Digite APAGAR para confirmar: '
  read -r answer
  if [ "$answer" = "APAGAR" ]; then
    rm -rf "$DATA_DIR"
    echo "Dados apagados."
  else
    echo "Nada foi apagado."
  fi
else
  echo "Seus dados continuam em $DATA_DIR (use --com-dados para apagá-los)."
fi
