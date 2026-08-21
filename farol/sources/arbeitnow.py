"""Arbeitnow — https://www.arbeitnow.com/api/job-board-api (aberta, paginada)."""

from __future__ import annotations

from typing import Any

import httpx

from .query import matches

ENDPOINT = "https://www.arbeitnow.com/api/job-board-api"


def fetch(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    response = client.get(ENDPOINT)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []

    items: list[dict[str, Any]] = []
    for job in data:
        if not isinstance(job, dict):
            continue
        title = job.get("title") or ""
        # a API não filtra por termo; filtramos aqui para não poluir a base
        if not matches(query, title, job.get("description"), job.get("company_name")):
            continue
        items.append(
            {
                "source_id": str(job.get("slug") or job.get("url") or ""),
                "title": title,
                "company": job.get("company_name"),
                "url": job.get("url"),
                "apply_url": job.get("url"),
                "location": job.get("location"),
                "remote": bool(job.get("remote")),
                "salary": "",
                "tags": (job.get("tags") or []) + (job.get("job_types") or []),
                "description": job.get("description"),
                "published_at": job.get("created_at"),
            }
        )
    return items
