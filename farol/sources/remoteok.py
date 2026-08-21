"""RemoteOK — https://remoteok.com/api (o primeiro item do array é aviso legal)."""

from __future__ import annotations

from typing import Any

import httpx

from .query import first_term, matches

ENDPOINT = "https://remoteok.com/api"


def fetch(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    # a API aceita uma tag só: mandar "junior backend python" devolve lista vazia.
    # Enviamos a primeira palavra e conferimos as demais no texto que voltou.
    tag = first_term(query)
    params = {"tags": tag} if tag else None
    response = client.get(ENDPOINT, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []

    items: list[dict[str, Any]] = []
    for job in payload:
        if not isinstance(job, dict) or "legal" in job or not job.get("position"):
            continue
        if not matches(query, job.get("position"), job.get("description"),
                       job.get("company"), " ".join(job.get("tags") or [])):
            continue
        salary = ""
        low, high = job.get("salary_min"), job.get("salary_max")
        if low and high:
            salary = f"US$ {int(low):,}–{int(high):,}/ano".replace(",", ".")
        items.append(
            {
                "source_id": str(job.get("id") or job.get("slug") or ""),
                "title": job.get("position"),
                "company": job.get("company"),
                "url": job.get("url") or f"https://remoteok.com/remote-jobs/{job.get('slug', '')}",
                "apply_url": job.get("apply_url") or job.get("url"),
                "location": job.get("location") or "Remoto",
                "remote": True,
                "salary": salary,
                "tags": job.get("tags"),
                "description": job.get("description"),
                "published_at": job.get("date") or job.get("epoch"),
            }
        )
    return items
