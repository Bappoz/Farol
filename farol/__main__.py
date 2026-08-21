"""Linha de comando do Farol.

    farol             abre o aplicativo (sobe o servidor e abre a janela)
    farol servir      só o servidor, no primeiro plano
    farol atualizar   só a coleta de vagas, e sai
    farol caminho     mostra onde ficam banco e arquivos
    farol versao      mostra a versão instalada
"""

from __future__ import annotations

import argparse
import sys

from . import __version__

DEFAULT_PORT = 7788
COMMANDS = ("abrir", "servir", "atualizar", "caminho", "versao")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="farol",
        description="Central de carreira local: vagas remotas, candidaturas, currículos e roadmap.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "exemplos:\n"
            "  farol                    abre a janela do aplicativo\n"
            "  farol atualizar          coleta vagas sem abrir nada (bom para cron)\n"
            "  farol servir --port 8000 servidor em outra porta\n"
        ),
    )
    parser.add_argument(
        "comando", nargs="?", default="abrir", choices=COMMANDS,
        help="abrir (padrão), servir, atualizar, caminho ou versao",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"porta local (padrão {DEFAULT_PORT})")
    parser.add_argument("--host", default="127.0.0.1", help="interface do servidor (padrão 127.0.0.1)")
    parser.add_argument("--reload", action="store_true", help="recarrega ao editar o código")
    parser.add_argument(
        "--sem-navegador", dest="sem_navegador", action="store_true",
        help="em 'abrir', sobe o servidor mas não abre a janela",
    )
    parser.add_argument("--version", action="version", version=f"farol {__version__}")
    return parser


def _collect() -> int:
    from . import collect

    report = collect.run()
    for source in report["sources"]:
        status = "ok " if source["status"] == "ok" else "ERRO"
        line = (
            f"{status} {source['label']:<20} {source['found']:>4} encontradas "
            f"{source['new']:>4} novas"
        )
        if source["error"]:
            line += f"  ← {source['error']}"
        print(line)
    print(f"\n{report['new']} vagas novas no total.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.comando == "versao":
        print(f"farol {__version__}")
        return 0

    from . import db

    db.bootstrap()

    if args.comando == "caminho":
        print(f"dados      {db.home()}")
        print(f"banco      {db.db_path()}")
        print(f"currículos {db.home() / 'curriculos'}")
        return 0

    if args.comando == "atualizar":
        return _collect()

    if args.comando == "abrir":
        from . import launcher

        return launcher.launch(args.port, args.host, open_browser=not args.sem_navegador)

    import uvicorn

    uvicorn.run(
        "farol.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
