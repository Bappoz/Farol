"""Ponto de entrada: `farol` sobe o servidor local; `farol atualizar` só coleta vagas."""

from __future__ import annotations

import argparse
import sys

DEFAULT_PORT = 7788


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="farol", description="Central de carreira local")
    parser.add_argument("comando", nargs="?", default="servir",
                        choices=["servir", "atualizar", "caminho"],
                        help="servir (padrão), atualizar (coleta vagas e sai) ou caminho (mostra o banco)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reload", action="store_true", help="recarrega ao editar o código")
    args = parser.parse_args(argv)

    from . import db

    db.bootstrap()

    if args.comando == "caminho":
        print(db.db_path())
        return 0

    if args.comando == "atualizar":
        from . import collect

        report = collect.run()
        for source in report["sources"]:
            status = "ok " if source["status"] == "ok" else "ERRO"
            line = f"{status} {source['label']:<20} {source['found']:>4} encontradas  {source['new']:>4} novas"
            if source["error"]:
                line += f"  ← {source['error']}"
            print(line)
        print(f"\n{report['new']} vagas novas no total.")
        return 0

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
