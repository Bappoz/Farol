"""Ponto de entrada do executável único.

O PyInstaller roda o arquivo indicado como script de topo, sem pacote pai — e
`farol/__main__.py` usa importação relativa. Este arquivo existe só para entrar
pelo caminho absoluto, com o pacote devidamente importado.
"""

from __future__ import annotations

import multiprocessing
import sys

from farol.__main__ import main

if __name__ == "__main__":
    # necessário quando o executável se re-invoca (uvicorn com workers, Windows)
    multiprocessing.freeze_support()
    sys.exit(main())
