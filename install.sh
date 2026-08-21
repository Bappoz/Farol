#!/usr/bin/env bash
# Instalador do Farol para Linux e macOS.
#
# Cria um ambiente Python isolado, instala o aplicativo, prepara o banco e
# registra o atalho no menu do sistema. Rodar de novo atualiza o que já existe:
# nenhuma etapa apaga dados.
#
#   ./install.sh                 instala a partir deste diretório
#   ./install.sh --sem-atalho    só o ambiente e o comando de terminal
#   ./install.sh --prefixo DIR   escolhe onde fica o executável (padrão ~/.local/bin)

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$APP_DIR/.venv"
BIN_DIR="${FAROL_BIN_DIR:-$HOME/.local/bin}"
WITH_SHORTCUT=1

while [ $# -gt 0 ]; do
  case "$1" in
    --sem-atalho) WITH_SHORTCUT=0 ;;
    --prefixo) BIN_DIR="$2"; shift ;;
    -h|--help) sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------- 1. Python

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  cat >&2 <<'MSG'
Python 3.10 ou mais novo não foi encontrado.

  Debian/Ubuntu   sudo apt install python3 python3-venv
  Fedora          sudo dnf install python3
  Arch            sudo pacman -S python
  macOS           brew install python@3.12
MSG
  exit 1
fi

step "1/5 · ambiente Python ($("$PYTHON" -V 2>&1))"
if command -v uv >/dev/null 2>&1; then
  uv venv --python "$PYTHON" "$VENV" >/dev/null
  uv pip install --quiet --python "$VENV/bin/python" -e "$APP_DIR"
else
  "$PYTHON" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -e "$APP_DIR"
fi

# ---------------------------------------------------------------- 2. banco

step "2/5 · banco de dados"
"$VENV/bin/python" -m farol caminho | sed 's/^/   /'

# ---------------------------------------------------------------- 3. comando

step "3/5 · comando de terminal"
mkdir -p "$BIN_DIR"
ln -sf "$VENV/bin/farol" "$BIN_DIR/farol"
echo "   $BIN_DIR/farol"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "   Atenção: $BIN_DIR não está no PATH. Acrescente ao seu shell:"
     warn "     export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

# ---------------------------------------------------------------- 4. atalho

if [ "$WITH_SHORTCUT" = "1" ] && [ "$(uname -s)" = "Darwin" ]; then
  step "4/5 · aplicativo do macOS"
  APP_BUNDLE="$HOME/Applications/Farol.app"
  mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

  cat >"$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Farol</string>
  <key>CFBundleDisplayName</key><string>Farol</string>
  <key>CFBundleIdentifier</key><string>dev.bappoz.farol</string>
  <key>CFBundleVersion</key><string>$("$VENV/bin/python" -c 'import farol; print(farol.__version__)')</string>
  <key>CFBundleExecutable</key><string>farol</string>
  <key>CFBundleIconFile</key><string>farol</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
</dict>
</plist>
PLIST

  cat >"$APP_BUNDLE/Contents/MacOS/farol" <<LAUNCH
#!/bin/sh
exec "$VENV/bin/farol" abrir
LAUNCH
  chmod +x "$APP_BUNDLE/Contents/MacOS/farol"

  # iconutil faz parte das ferramentas do sistema em todo macOS
  if command -v iconutil >/dev/null 2>&1; then
    ICONSET="$(mktemp -d)/farol.iconset"
    mkdir -p "$ICONSET"
    for size in 16 32 128 256 512; do
      cp "$APP_DIR/assets/farol-$size.png" "$ICONSET/icon_${size}x${size}.png" 2>/dev/null || true
    done
    cp "$APP_DIR/assets/farol-32.png" "$ICONSET/icon_16x16@2x.png" 2>/dev/null || true
    cp "$APP_DIR/assets/farol-64.png" "$ICONSET/icon_32x32@2x.png" 2>/dev/null || true
    cp "$APP_DIR/assets/farol-256.png" "$ICONSET/icon_128x128@2x.png" 2>/dev/null || true
    cp "$APP_DIR/assets/farol-512.png" "$ICONSET/icon_256x256@2x.png" 2>/dev/null || true
    iconutil -c icns "$ICONSET" -o "$APP_BUNDLE/Contents/Resources/farol.icns" 2>/dev/null || true
  fi
  echo "   $APP_BUNDLE"

elif [ "$WITH_SHORTCUT" = "1" ]; then
  step "4/5 · atalho no menu"
  APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  ICON_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
  mkdir -p "$APPS_DIR" "$ICON_ROOT/scalable/apps"
  cp "$APP_DIR/farol/static/icon.svg" "$ICON_ROOT/scalable/apps/farol.svg"
  for size in 16 32 48 64 128 256; do
    mkdir -p "$ICON_ROOT/${size}x${size}/apps"
    cp "$APP_DIR/assets/farol-$size.png" "$ICON_ROOT/${size}x${size}/apps/farol.png" 2>/dev/null || true
  done

  cat >"$APPS_DIR/farol.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Farol
GenericName=Central de carreira
Comment=Vagas remotas, pipeline de candidaturas, currículos e roadmap de estudos
Exec=$VENV/bin/farol abrir
Icon=farol
Terminal=false
Categories=Office;Development;
Keywords=vagas;emprego;curriculo;carreira;jobs;farol;
StartupNotify=true
StartupWMClass=Farol
DESKTOP

  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" 2>/dev/null || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -qtf "$ICON_ROOT" 2>/dev/null || true
  echo "   $APPS_DIR/farol.desktop"
else
  step "4/5 · atalho ignorado (--sem-atalho)"
fi

# ---------------------------------------------------------------- 5. fim

step "5/5 · instalado"
cat <<MSG

  Abrir            farol
  Só o servidor    farol servir
  Só a coleta      farol atualizar
  Onde ficam       farol caminho
  Desinstalar      $APP_DIR/uninstall.sh

MSG
