"""Himalayas — https://himalayas.app/jobs/api (vagas 100% remotas)."""

from __future__ import annotations

from typing import Any

import httpx

ENDPOINT = "https://himalayas.app/jobs/api"


def fetch(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    response = client.get(ENDPOINT, params={"limit": 50})
    response.raise_for_status()
    payload = response.json()
    jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(jobs, list):
        return []

    needle = (query or "").lower().strip()
    items: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = job.get("title") or ""
        description = job.get("description") or job.get("excerpt") or ""
        if needle and needle not in f"{title} {description}".lower():
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
