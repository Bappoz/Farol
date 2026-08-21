"""Linha de comando do Farol.

    farol             abre o aplicativo (sobe o servidor e abre a janela)
    farol servir      só o servidor, no primeiro plano
    farol atualizar   só a coleta de vagas, e sai
    farol caminho     mostra onde ficam banco e arquivos
    farol versao      mostra a versão instalada
    farol update      verifica se há uma versão nova do app e atualiza
"""

from __future__ import annotations

import argparse
import sys

from . import __version__

DEFAULT_PORT = 7788
COMMANDS = ("abrir", "servir", "atualizar", "caminho", "versao", "update")


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
            "  farol update             verifica e instala uma versão nova do app\n"
        ),
    )
    parser.add_argument(
        "comando", nargs="?", default="abrir", choices=COMMANDS,
        help="abrir (padrão), servir, atualizar, caminho, versao ou update",
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
    resumo = f"\n{report['new']} vagas novas no total."
    if report.get("expired"):
        resumo += f" {report['expired']} saíram do ar e foram marcadas como expiradas."
    print(resumo)
    return 0


def _selfupdate() -> int:
    from . import selfupdate

    result = selfupdate.run()
    status = result["status"]

    if status == "no_git":
        print("Este farol não veio de um clone git — sem atualização automática por aqui.")
        print(f"Baixe a versão mais nova em {selfupdate.REPO_URL}/releases e reinstale.")
        return 1
    if status == "dirty":
        print(f"Há mudanças não commitadas em {selfupdate.APP_DIR} — resolva (git status) antes de atualizar.")
        return 1
    if status == "error":
        print(f"Não deu para atualizar: {result['detail']}")
        return 1
    if status == "up_to_date":
        print(f"Farol já está atualizado (versão {result['versao']}).")
        return 0

    print(f"Farol atualizado para a versão {result['versao']}.")
    if result.get("install_detail"):
        print("Atenção: as dependências podem não ter sido reinstaladas por completo:")
        print(result["install_detail"])
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.comando == "versao":
        print(f"farol {__version__}")
        return 0

    if args.comando == "update":
        return _selfupdate()

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
