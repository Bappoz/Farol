"""Coletores de vagas.

Cada coletor é um módulo com uma função `fetch(client, query) -> list[dict]`.
O dicionário devolvido segue sempre o mesmo formato:

    source_id, title, company, url, apply_url, location, remote,
    salary, tags (list[str]), description (texto puro), published_at (ISO-8601)

Para adicionar um portal novo: crie `farol/sources/meuportal.py` com um `fetch`,
registre em `REGISTRY` abaixo e adicione a linha em `db.BUILTIN_SOURCES`.
"""

from __future__ import annotations

import html
import itertools
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from .. import USER_AGENT
from . import arbeitnow, himalayas, remoteok, remotive, rss, weworkremotely
from .query import first_term, matches

__all__ = [
    "REGISTRY",
    "USER_AGENT",
    "client",
    "fetch_source",
    "first_term",
    "matches",
    "normalize",
    "to_text",
]

REGISTRY: dict[str, Callable[[httpx.Client, str], list[dict[str, Any]]]] = {
    "remotive": remotive.fetch,
    "remoteok": remoteok.fetch,
    "arbeitnow": arbeitnow.fetch,
    "himalayas": himalayas.fetch,
    "weworkremotely": weworkremotely.fetch,
}


def client(timeout: float = 25.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/xml, */*"},
    )


# ------------------------------------------------------------------ helpers


_HEADING_OPEN = re.compile(r"<h[1-6][^>]*>", re.I)
_LIST_ITEM_OPEN = re.compile(r"<li[^>]*>", re.I)
_ORDERED_BLOCK = re.compile(r"<ol[^>]*>(.*?)</ol>", re.I | re.S)
_BLOCK_TAGS = re.compile(r"</(p|div|li|ul|ol|h[1-6]|tr|br)>|<br\s*/?>", re.I)
_TAGS = re.compile(r"<[^>]+>")


def _number_items(match: re.Match[str]) -> str:
    """Itens de <ol> viram '1. ', '2. '… — a ordem é parte do conteúdo."""
    counter = itertools.count(1)
    return _LIST_ITEM_OPEN.sub(lambda _: f"\n{next(counter)}. ", match.group(1))


def to_text(raw: str | None) -> str:
    """HTML → texto quase-markdown, preservando título de seção e lista.

    A estrutura do anúncio é o que o torna legível: `farol.markup` reconstrói o
    HTML a partir destes marcadores (`## ` para título, `- ` para item). Guardamos
    texto em vez de HTML porque o mesmo campo alimenta a extração de skills.
    """
    if not raw:
        return ""
    text = _HEADING_OPEN.sub("\n## ", str(raw))
    text = _ORDERED_BLOCK.sub(_number_items, text)  # antes do <li> genérico
    text = _LIST_ITEM_OPEN.sub("\n- ", text)
    text = _BLOCK_TAGS.sub("\n", text)
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    # o marcador pode ter ficado com espaço sobrando antes do texto
    text = re.sub(r"^(##|-|\d{1,2}\.) +", r"\1 ", text, flags=re.M)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def iso(value: Any) -> str | None:
    """Normaliza epoch, string ISO ou data RFC-822 para ISO-8601 UTC."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if text.isdigit():
        return iso(int(text))
    candidates = [
        lambda t: datetime.fromisoformat(t.replace("Z", "+00:00")),
        lambda t: datetime.strptime(t, "%a, %d %b %Y %H:%M:%S %z"),
        lambda t: datetime.strptime(t, "%a, %d %b %Y %H:%M:%S %Z"),
        lambda t: datetime.strptime(t, "%Y-%m-%d"),
    ]
    for parse in candidates:
        try:
            parsed = parse(text)
        except (ValueError, TypeError):
            continue
        if not parsed.tzinfo:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return None


def as_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()][:20]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()][:20]
    return []


def normalize(source: str, item: dict[str, Any]) -> dict[str, Any] | None:
    """Garante os campos obrigatórios e descarta itens quebrados."""
    title = (item.get("title") or "").strip()
    source_id = str(item.get("source_id") or "").strip()
    if not title or not source_id:
        return None
    return {
        "source": source,
        "source_id": source_id,
        "title": title[:200],
        "company": (item.get("company") or "").strip()[:120],
        "url": (item.get("url") or "").strip(),
        "apply_url": (item.get("apply_url") or "").strip(),
        "location": (item.get("location") or "").strip()[:120],
        "remote": 1 if item.get("remote", True) else 0,
        "salary": (item.get("salary") or "").strip()[:120],
        "tags": as_tags(item.get("tags")),
        "description": to_text(item.get("description"))[:20000],
        "published_at": item.get("published_at"),
    }


def fetch_source(source: dict[str, Any], query: str, http: httpx.Client) -> list[dict[str, Any]]:
    """Executa um coletor (embutido ou RSS custom) e devolve itens normalizados."""
    sid = source["id"]
    if source.get("kind") == "rss":
        raw = rss.fetch(http, source.get("url") or "")
        sid_prefix = sid
    else:
        collector = REGISTRY.get(sid)
        if collector is None:
            raise ValueError(f"fonte desconhecida: {sid}")
        raw = collector(http, query)
        sid_prefix = sid
    items = []
    for entry in raw:
        normalized = normalize(sid_prefix, entry)
        if normalized:
            items.append(normalized)
    return items
