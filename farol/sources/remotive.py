"""Remotive — https://remotive.com/api/remote-jobs (API pública, sem chave)."""

from __future__ import annotations

from typing import Any

import httpx

ENDPOINT = "https://remotive.com/api/remote-jobs"


def fetch(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": 60}
    if query:
        params["search"] = query
    response = client.get(ENDPOINT, params=params)
    response.raise_for_status()
    payload = response.json()
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        return []

    items: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        items.append(
            {
                "source_id": str(job.get("id") or job.get("url") or ""),
                "title": job.get("title"),
                "company": job.get("company_name"),
                "url": job.get("url"),
                "apply_url": job.get("url"),
                "location": job.get("candidate_required_location"),
                "remote": True,
                "salary": job.get("salary"),
                "tags": (job.get("tags") or []) + [job.get("category") or ""],
                "description": job.get("description"),
                "published_at": job.get("publication_date"),
            }
        )
    return items
