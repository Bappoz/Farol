"""Leituras: agregador de artigos técnicos (issue #9).

O estudo de custo-benefício que o issue pedia está em
`docs/decisoes/0002-agregador-de-leituras.md`. O resumo do que foi decidido, e que
explica a forma deste módulo:

**Só RSS/Atom, nunca scraping.** Feed é um canal que o autor publicou de propósito
para ser lido por programa. Raspar o HTML de um blog seria a mesma fragilidade dos
portais de vaga, por um conteúdo que vale menos que uma vaga.

**Título, link, data e o resumo que o próprio feed traz — mais nada.** O texto do
artigo não é copiado para o banco. O resumo é cortado em `SUMMARY_MAX` caracteres,
e todo item leva o link para o site de quem escreveu. O Farol é um índice do que
vale ler, não uma cópia da internet.

**Opt-in.** Os dez feeds embutidos nascem desligados (`db.BUILTIN_FEEDS`) e a
atualização é sempre um pedido explícito seu — abrir o app não busca artigo. Quem
nunca entrar em Leituras não gera uma requisição sequer.

**A ligação com o perfil é a taxonomia que já existe.** As skills do artigo saem
de `farol.skills.extract` sobre título e resumo, as mesmas canônicas do fit score
e do roadmap. Sem taxonomia nova, sem classificador.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

from . import db, skills, sources
from .sources import rss

# Quanto do resumo do feed é guardado. O suficiente para decidir se vale abrir,
# curto o bastante para não ser republicação do texto de ninguém.
SUMMARY_MAX = 400

# Quantos feeds falam com a rede ao mesmo tempo. Cada feed é um servidor
# diferente e um pedido só — não há rajada a conter, ao contrário da coleta de
# vagas, onde o mesmo portal é consultado uma vez por termo de busca.
MAX_PARALLEL_FEEDS = int(os.environ.get("FAROL_PARALLEL_FEEDS", "4"))

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "finished_at": None, "report": None, "error": ""}


# ------------------------------------------------------------------ feeds


def feeds(only_enabled: bool = False) -> list[dict[str, Any]]:
    clause = " WHERE enabled = 1" if only_enabled else ""
    return [dict(r) for r in db.query(f"SELECT * FROM feeds{clause} ORDER BY label COLLATE NOCASE")]


def add_feed(label: str, url: str) -> str:
    """Cadastra um feed seu. O id vem da URL, então o mesmo feed nunca entra duas vezes."""
    url = url.strip()
    if not url:
        raise ValueError("informe a URL do feed")
    fid = "feed-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    db.execute(
        "INSERT OR REPLACE INTO feeds (id, label, url, enabled) VALUES (?, ?, ?, 1)",
        (fid, (label.strip() or url)[:80], url),
    )
    return fid


def toggle_feed(feed_id: str) -> None:
    db.execute("UPDATE feeds SET enabled = 1 - enabled WHERE id = ?", (feed_id,))


def remove_feed(feed_id: str) -> None:
    """Remove o feed **e** os artigos que vieram dele: índice órfão não serve a ninguém."""
    conn = db.connect()
    with conn:
        conn.execute("DELETE FROM articles WHERE feed = ?", (feed_id,))
        conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))


# ------------------------------------------------------------------ ingestão


def url_key(url: str) -> str:
    """Chave de deduplicação entre feeds: o mesmo artigo sai em agregador e no blog.

    Tira esquema, `www.`, barra final, âncora e os parâmetros de campanha, que são
    o motivo mais comum de a mesma URL chegar escrita de dois jeitos.
    """
    if not url:
        return ""
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if not host:
        return ""
    caminho = (parsed.path or "/").rstrip("/") or "/"
    query = "&".join(
        parte for parte in (parsed.query or "").split("&")
        if parte and not parte.lower().startswith(("utm_", "ref=", "source="))
    )
    return urlunparse(("", host, caminho, "", query, ""))


def _entry_to_article(feed_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    titulo = (entry.get("title") or "").strip()
    if not titulo:
        return None
    url = (entry.get("url") or "").strip()
    resumo = sources.to_text(entry.get("description"))
    if len(resumo) > SUMMARY_MAX:
        resumo = resumo[:SUMMARY_MAX].rsplit(" ", 1)[0] + "…"
    tags = " ".join(str(t) for t in (entry.get("tags") or []))
    return {
        "feed": feed_id,
        "guid": str(entry.get("source_id") or url or titulo)[:300],
        "url_key": url_key(url),
        "title": titulo[:300],
        "url": url,
        "summary": resumo,
        "published_at": sources.iso(entry.get("published_at")),
        "skills": db.dumps(skills.extract(f"{titulo} {tags} {resumo}")),
    }


_INSERT_COLUMNS = ("feed", "guid", "url_key", "title", "url", "summary", "published_at", "skills")


def _save(artigos: list[dict[str, Any]]) -> int:
    """Grava o que é inédito. Devolve quantos entraram.

    `INSERT OR IGNORE` cobre as duas deduplicações de uma vez: o par (feed, guid),
    que é o mesmo item reaparecendo no próprio feed, e a URL normalizada, que é o
    mesmo artigo chegando por dois feeds diferentes.
    """
    if not artigos:
        return 0
    marcas = ",".join("?" for _ in _INSERT_COLUMNS)
    conn = db.connect()
    novos = 0
    with conn:
        for artigo in artigos:
            cursor = conn.execute(
                f"INSERT OR IGNORE INTO articles ({','.join(_INSERT_COLUMNS)}) VALUES ({marcas})",
                [artigo[coluna] for coluna in _INSERT_COLUMNS],
            )
            novos += cursor.rowcount or 0
    return novos


def _fetch_feed(feed: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    try:
        with sources.client() as http:
            cru = rss.fetch(http, feed["url"])
    except Exception as exc:  # noqa: BLE001 — o erro vira diagnóstico na tela, como nas fontes de vaga
        return [], f"{type(exc).__name__}: {exc}"[:300]
    artigos = [a for a in (_entry_to_article(feed["id"], e) for e in cru) if a]
    return artigos, ""


def refresh(feed_ids: list[str] | None = None) -> dict[str, Any]:
    """Atualiza os feeds ativos. Devolve um relatório por feed.

    Feed que falha não derruba os outros nem apaga o que ele já trouxe: o erro
    fica gravado em `feeds.last_error` e a lista continua mostrando os artigos
    antigos daquele feed.
    """
    ativos = [f for f in feeds(only_enabled=True) if not feed_ids or f["id"] in feed_ids]
    relatorio: list[dict[str, Any]] = []
    total = 0
    if not ativos:
        return {"feeds": relatorio, "new": 0, "removed": 0}

    colhido: dict[str, tuple[list[dict[str, Any]], str]] = {}
    with ThreadPoolExecutor(max_workers=min(len(ativos), MAX_PARALLEL_FEEDS)) as pool:
        futuros = {pool.submit(_fetch_feed, f): f["id"] for f in ativos}
        for futuro in as_completed(futuros):
            colhido[futuros[futuro]] = futuro.result()

    for feed in ativos:
        artigos, erro = colhido.get(feed["id"], ([], "feed não executado"))
        novos = _save(artigos)
        total += novos
        status = "erro" if erro and not artigos else "ok"
        db.execute(
            """UPDATE feeds SET last_run_at = datetime('now'), last_status = ?,
                                last_count = ?, last_error = ? WHERE id = ?""",
            (status, len(artigos), erro, feed["id"]),
        )
        relatorio.append(
            {"id": feed["id"], "label": feed["label"], "found": len(artigos),
             "new": novos, "status": status, "error": erro}
        )
    return {"feeds": relatorio, "new": total, "removed": prune()}


def prune() -> int:
    """Descarta artigo velho. A janela é ajustável em `reading_keep_days`.

    O índice não precisa virar arquivo histórico: o que ainda está no ar volta na
    próxima atualização do feed, e o que saiu do ar não interessa mais.
    """
    try:
        dias = max(1, int(db.get_settings().get("reading_keep_days") or 60))
    except ValueError:
        dias = 60
    corte = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=dias)).isoformat(
        sep=" ", timespec="seconds"
    )
    conn = db.connect()
    with conn:
        cursor = conn.execute(
            "DELETE FROM articles WHERE COALESCE(published_at, first_seen_at) < ?", (corte,)
        )
    return cursor.rowcount or 0


# ------------------------------------------------- atualização em segundo plano


def status() -> dict[str, Any]:
    snapshot = dict(_state)
    row = db.one("SELECT MAX(last_run_at) AS at FROM feeds WHERE last_status IS NOT NULL")
    snapshot["last_run_at"] = row["at"] if row else None
    return snapshot


def _worker(feed_ids: list[str] | None) -> None:
    try:
        _state["report"] = refresh(feed_ids)
        _state["error"] = ""
    except Exception as exc:  # noqa: BLE001 — vira aviso na tela, não derruba o app
        _state["report"] = None
        _state["error"] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        _state["running"] = False
        _state["finished_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(
            timespec="seconds"
        )


def start(feed_ids: list[str] | None = None) -> dict[str, Any]:
    """Dispara a atualização numa thread. Sempre a pedido seu — nunca sozinha."""
    with _lock:
        if _state["running"]:
            return {"verdict": "em-curso", **status()}
        _state.update(running=True, finished_at=None, report=None, error="")
    threading.Thread(
        target=_worker, args=(feed_ids,), daemon=True, name="farol-leituras"
    ).start()
    return {"verdict": "iniciada", **status()}


# ------------------------------------------------------------------ consulta


def stale_days() -> int:
    try:
        return max(1, int(db.get_settings().get("reading_stale_days") or 365))
    except ValueError:
        return 365


def _decorate(row: Any, owned: set[str], limite: str) -> dict[str, Any]:
    artigo = dict(row)
    artigo["skills"] = db.loads(artigo.get("skills"), [])
    artigo["matched"] = [s for s in artigo["skills"] if s in owned]
    artigo["read"] = bool(artigo.get("read_at"))
    quando = artigo.get("published_at") or artigo.get("first_seen_at") or ""
    # conteúdo possivelmente desatualizado: o issue pedia a indicação, e em texto
    # técnico a data é o único sinal barato que existe
    artigo["stale"] = bool(quando) and quando < limite
    return artigo


# o rótulo do feed vem do JOIN: a tela mostra "GitHub Blog", não `feed-a8a5e430cf`
ARTICLE_COLUMNS = """a.id, a.feed, a.title, a.url, a.summary, a.published_at, a.first_seen_at,
                     a.skills, a.read_at, COALESCE(f.label, a.feed) AS feed_label"""


def listing(*, unread_only: bool = False, feed: str = "", skill: str = "",
            mine_only: bool = False, term: str = "", limit: int = 80) -> list[dict[str, Any]]:
    """Artigos do mais recente para o mais antigo, com os filtros da tela aplicados."""
    profile = db.get_profile()
    owned = set(profile.get("skills") or [])

    where: list[str] = []
    args: list[Any] = []
    if unread_only:
        where.append("a.read_at IS NULL")
    if feed:
        where.append("a.feed = ?")
        args.append(feed)
    if skill:
        # a coluna guarda JSON de canônicas: procurar a string entre aspas evita
        # que "java" case dentro de "javascript"
        where.append("a.skills LIKE ?")
        args.append(f'%"{skill}"%')
    if mine_only and owned:
        where.append("(" + " OR ".join("a.skills LIKE ?" for _ in owned) + ")")
        args += [f'%"{s}"%' for s in sorted(owned)]
    if term:
        where.append("(LOWER(a.title) LIKE ? OR LOWER(a.summary) LIKE ?)")
        agulha = f"%{term.lower()}%"
        args += [agulha, agulha]

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    rows = db.query(
        f"""SELECT {ARTICLE_COLUMNS} FROM articles a
            LEFT JOIN feeds f ON f.id = a.feed{clause}
            ORDER BY COALESCE(a.published_at, a.first_seen_at) DESC LIMIT ?""",
        [*args, limit],
    )
    limite = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=stale_days())).isoformat()
    return [_decorate(row, owned, limite) for row in rows]


def counts() -> dict[str, int]:
    total = db.one("SELECT COUNT(*) AS n FROM articles")["n"]
    nao_lidos = db.one("SELECT COUNT(*) AS n FROM articles WHERE read_at IS NULL")["n"]
    return {"total": total, "unread": nao_lidos}


def top_skills(limit: int = 12) -> list[tuple[str, int]]:
    """Skills mais citadas no acervo — os atalhos de filtro da tela."""
    contador: Counter[str] = Counter()
    for row in db.query("SELECT skills FROM articles"):
        contador.update(db.loads(row["skills"], []))
    return contador.most_common(limit)


def mark_read(article_id: int, read: bool = True) -> None:
    db.execute(
        "UPDATE articles SET read_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") if read else None,
         article_id),
    )


def mark_all_read() -> int:
    conn = db.connect()
    with conn:
        cursor = conn.execute(
            "UPDATE articles SET read_at = datetime('now') WHERE read_at IS NULL"
        )
    return cursor.rowcount or 0
