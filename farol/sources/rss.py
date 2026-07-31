"""Leitor genérico de RSS/Atom — serve aos feeds embutidos e às fontes que você adicionar."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree

import httpx

NS = {"atom": "http://www.w3.org/2005/Atom", "content": "http://purl.org/rss/1.0/modules/content/"}


def _text(node: ElementTree.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _first(item: ElementTree.Element, *paths: str) -> ElementTree.Element | None:
    for path in paths:
        found = item.find(path, NS)
        if found is not None:
            return found
    return None


def fetch(client: httpx.Client, url: str) -> list[dict[str, Any]]:
    if not url:
        return []
    response = client.get(url)
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)

    entries = root.findall(".//item") or root.findall(".//atom:entry", NS)
    items: list[dict[str, Any]] = []
    for entry in entries:
        title = _text(_first(entry, "title", "atom:title"))
        link_node = _first(entry, "link", "atom:link")
        link = _text(link_node)
        if not link and link_node is not None:
            link = link_node.attrib.get("href", "")
        guid = _text(_first(entry, "guid", "atom:id")) or link
        description = _text(
            _first(entry, "content:encoded", "description", "atom:content", "atom:summary")
        )
        published = _text(_first(entry, "pubDate", "atom:updated", "atom:published"))
        region = _text(entry.find("region")) or _text(entry.find("location"))
        company = _text(entry.find("company"))
        categories = [_text(c) for c in entry.findall("category")]
        if not title:
            continue
        items.append(
            {
                "source_id": guid or title,
                "title": title,
                "company": company,
                "url": link,
                "apply_url": link,
                "location": region or "Remoto",
                "remote": True,
                "salary": "",
                "tags": categories,
                "description": description,
                "published_at": published,
            }
        )
    return items
