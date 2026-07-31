"""We Work Remotely — feed RSS da categoria de programação."""

from __future__ import annotations

from typing import Any

import httpx

from . import rss

FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
]


def fetch(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    needle = (query or "").lower().strip()
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for feed in FEEDS:
        try:
            entries = rss.fetch(client, feed)
        except Exception as exc:  # um feed fora do ar não derruba os outros
            errors.append(f"{feed.rsplit('/', 1)[-1]}: {exc}")
            continue
        for entry in entries:
            title = entry.get("title") or ""
            # o WWR usa "Empresa: Cargo" no título do item
            if ":" in title and not entry.get("company"):
                company, _, role = title.partition(":")
                entry["company"] = company.strip()
                entry["title"] = role.strip() or title
            if needle and needle not in f"{entry.get('title', '')} {entry.get('description', '')}".lower():
                continue
            items.append(entry)
    if not items and errors:
        raise RuntimeError("; ".join(errors))
    return items
