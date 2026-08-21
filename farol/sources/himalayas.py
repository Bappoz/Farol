"""Himalayas — https://himalayas.app/jobs/api (vagas 100% remotas).

A API devolve no máximo 20 vagas por chamada e ignora `limit` acima disso, então
paginamos por `offset` até `PAGES` páginas. O User-Agent honesto do pacote é
condição para a resposta chegar: a proteção antibot do portal devolve 403 para
User-Agent de navegador que não executa JavaScript.
"""

from __future__ import annotations

from typing import Any

import httpx

from .query import matches

ENDPOINT = "https://himalayas.app/jobs/api"
PAGE_SIZE = 20
PAGES = 3


def _page(client: httpx.Client, offset: int) -> list[dict[str, Any]]:
    response = client.get(ENDPOINT, params={"limit": PAGE_SIZE, "offset": offset})
    response.raise_for_status()
    payload = response.json()
    jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    return jobs if isinstance(jobs, list) else []


def fetch(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for page in range(PAGES):
        batch = _page(client, page * PAGE_SIZE)
        jobs.extend(batch)
        if len(batch) < PAGE_SIZE:
            break

    items: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = job.get("title") or ""
        description = job.get("description") or job.get("excerpt") or ""
        if not matches(query, title, description, job.get("companyName")):
            continue
        salary = ""
        low, high = job.get("minSalary"), job.get("maxSalary")
        if low and high:
            salary = f"US$ {int(low):,}–{int(high):,}/ano".replace(",", ".")
        locations = job.get("locationRestrictions") or []
        items.append(
            {
                "source_id": str(job.get("guid") or job.get("applicationLink") or title),
                "title": title,
                "company": job.get("companyName"),
                "url": job.get("applicationLink") or job.get("guid"),
                "apply_url": job.get("applicationLink"),
                "location": ", ".join(str(loc) for loc in locations) or "Worldwide",
                "remote": True,
                "salary": salary,
                "tags": (job.get("categories") or []) + (job.get("seniority") or []),
                "description": description,
                "published_at": job.get("pubDate"),
            }
        )
    return items
