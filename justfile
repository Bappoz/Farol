# Receitas do Farol. `just --list` mostra todas.
# Sem `just` instalado, cada receita é um comando só — copie a linha.

python := ".venv/bin/python"
ruff := ".venv/bin/ruff"

# lista as receitas
default:
    @just --list

# cria o ambiente e instala em modo editável, com as ferramentas de desenvolvimento
setup:
    ./install.sh --sem-atalho
    uv pip install --python {{python}} -e ".[dev]" || {{python}} -m pip install -e ".[dev]"

# servidor com recarga automática ao editar o código
dev port="7788":
    {{python}} -m farol servir --port {{port}} --reload

# abre o aplicativo como o atalho do menu faz
run:
    {{python}} -m farol abrir

# coleta vagas sem abrir a janela
collect:
    {{python}} -m farol atualizar

# lint e testes — o portão de qualidade, na mesma ordem da CI
check: lint test

# formatador disponível, mas não imposto: veja CONTRIBUTING.md
format:
    {{ruff}} format farol tests

lint:
    {{ruff}} check --fix farol tests

test *args:
    {{python}} -m pytest {{args}}

cover:
    {{python}} -m pytest --cov=farol --cov-report=term-missing

# executável único para este sistema (dist/farol)
binary:
    {{python}} -m pip install -e ".[build]"
    {{python}} -m PyInstaller packaging/farol.spec --noconfirm

# pacote instalável por pip/pipx (dist/*.whl)
package:
    {{python}} -m pip install --quiet build
    {{python}} -m build

# imagem Docker e um contêiner de teste
docker:
    docker build -t farol:local .
    docker run --rm -d --name farol-teste -p 7788:7788 farol:local
    @echo "http://127.0.0.1:7788 — pare com: docker rm -f farol-teste"

# regenera os ícones a partir do SVG (precisa de rsvg-convert e magick)
icons:
    #!/usr/bin/env bash
    set -euo pipefail
    for s in 16 32 48 64 128 256 512; do
        rsvg-convert -w $s -h $s farol/static/icon.svg -o "assets/farol-$s.png"
    done
    magick assets/farol-{16,32,48,64,128,256}.png assets/farol.ico
    cp assets/farol-512.png assets/farol.png

# remove artefatos de build e caches
clean:
    rm -rf build dist *.egg-info .pytest_cache .ruff_cache .coverage
    find . -name __pycache__ -type d -prune -exec rm -rf {} +
