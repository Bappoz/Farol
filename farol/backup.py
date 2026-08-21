"""Backup completo: exportar, ler de volta e restaurar.

Um backup que não restaura não é backup — o app exportava JSON desde a primeira
versão e nunca soube importá-lo. Aqui o arquivo vira um ZIP com o JSON e os PDFs
de currículo que o usuário enviou, porque o JSON sozinho referencia arquivos que
não estão dentro dele.

O que **não** entra: as vagas coletadas. Elas se refazem sozinhas na próxima
coleta e ocupariam a maior parte do arquivo. O que se perde numa máquina nova é
o histórico de anúncio, não o trabalho da pessoa.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from typing import Any

from . import __version__, db, pdfs

MANIFEST = "backup.json"
FILES_PREFIX = "curriculos/"

# Tabelas restauradas na íntegra, na ordem em que precisam ser gravadas: quem
# tem chave estrangeira vem depois de quem é referenciado.
TABLES = ("applications", "events", "resumes", "learning", "searches")

# Chaves de ajuste que não viajam: a do modelo é do ambiente, e a da API é
# credencial — backup que carrega segredo vira segredo espalhado por aí.
SETTINGS_EXCLUDED = {"anthropic_api_key"}


def _rows(table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in db.query(f"SELECT * FROM {table}")]


def payload() -> dict[str, Any]:
    """Conteúdo do backup, pronto para virar JSON."""
    settings = {k: v for k, v in db.get_settings().items() if k not in SETTINGS_EXCLUDED}
    dados: dict[str, Any] = {
        "farol": {
            "version": __version__,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "format": 1,
        },
        "profile": db.get_profile(),
        "settings": settings,
    }
    for table in TABLES:
        dados[table] = _rows(table)
    return json.loads(json.dumps(dados, default=str, ensure_ascii=False))


def archive() -> bytes:
    """ZIP com o manifesto e os PDFs de currículo enviados pelo usuário."""
    buffer = io.BytesIO()
    dados = payload()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, json.dumps(dados, ensure_ascii=False, indent=1))
        for resume in dados.get("resumes", []):
            relativo = resume.get("file") or ""
            caminho = pdfs.path_for(relativo)
            if caminho is not None:
                zf.write(caminho, relativo)
    return buffer.getvalue()


def read(content: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Lê backup em ZIP ou em JSON puro. Devolve (manifesto, arquivos)."""
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            nomes = zf.namelist()
            if MANIFEST not in nomes:
                raise ValueError("o ZIP não contém backup.json")
            dados = json.loads(zf.read(MANIFEST).decode("utf-8"))
            arquivos = {
                nome: zf.read(nome) for nome in nomes
                if nome.startswith(FILES_PREFIX) and not nome.endswith("/")
            }
        return dados, arquivos
    return json.loads(content.decode("utf-8")), {}


def describe(dados: dict[str, Any]) -> dict[str, Any]:
    """Resumo do que há dentro do backup, para conferir antes de restaurar."""
    return {
        "version": (dados.get("farol") or {}).get("version", "desconhecida"),
        "exported_at": (dados.get("farol") or {}).get("exported_at", ""),
        "profile": (dados.get("profile") or {}).get("name", ""),
        **{table: len(dados.get(table) or []) for table in TABLES},
    }


def _insert(conn, table: str, linhas: list[dict[str, Any]]) -> int:
    """Grava as linhas mantendo só as colunas que esta versão do schema conhece."""
    colunas = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    gravadas = 0
    for linha in linhas:
        campos = [campo for campo in linha if campo in colunas]
        if not campos:
            continue
        marcadores = ",".join("?" for _ in campos)
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({','.join(campos)}) VALUES ({marcadores})",
            [linha[campo] for campo in campos],
        )
        gravadas += 1
    return gravadas


def restore(dados: dict[str, Any], arquivos: dict[str, bytes] | None = None) -> dict[str, Any]:
    """Substitui perfil, candidaturas, currículos, plano e ajustes pelo backup.

    É destrutivo por definição — restaurar é trocar o que está aqui pelo que
    está no arquivo — e por isso a rota que chama esta função exige confirmação.
    As vagas coletadas ficam intocadas: elas não estão no backup e se refazem na
    próxima coleta.
    """
    if not isinstance(dados, dict) or "profile" not in dados:
        raise ValueError("arquivo não parece um backup do Farol")

    arquivos = arquivos or {}
    resumo: dict[str, Any] = {"tabelas": {}, "arquivos": 0, "pdfs_ausentes": []}
    conn = db.connect()
    with conn:
        # a ordem inversa respeita as chaves estrangeiras na hora de limpar
        for table in reversed(TABLES):
            conn.execute(f"DELETE FROM {table}")
        for table in TABLES:
            resumo["tabelas"][table] = _insert(conn, table, dados.get(table) or [])

        perfil = dados.get("profile") or {}
        campos = [campo for campo in perfil if campo not in ("id", "updated_at")]
        colunas = {row["name"] for row in conn.execute("PRAGMA table_info(profile)")}
        campos = [campo for campo in campos if campo in colunas]
        if campos:
            atribuicoes = ", ".join(f"{campo} = ?" for campo in campos)
            conn.execute(
                f"UPDATE profile SET {atribuicoes} WHERE id = 1",
                [json.dumps(perfil[c], ensure_ascii=False)
                 if isinstance(perfil[c], (list, dict)) else perfil[c] for c in campos],
            )

        for chave, valor in (dados.get("settings") or {}).items():
            if chave in SETTINGS_EXCLUDED:
                continue
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (chave, str(valor)),
            )

    destino = db.home()
    for nome, conteudo in arquivos.items():
        alvo = (destino / nome).resolve()
        if not str(alvo).startswith(str(destino.resolve())):
            continue  # nome de arquivo tentando escapar do diretório de dados
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(conteudo)
        resumo["arquivos"] += 1

    resumo["pdfs_ausentes"] = [
        resume.get("name", "?") for resume in (dados.get("resumes") or [])
        if resume.get("file") and pdfs.path_for(resume["file"]) is None
    ]
    return resumo
