"""Roadmap: o que estudar, construir e certificar — derivado das vagas que VOCÊ buscou.

A lógica é simples e proposital: a demanda vem da sua própria base de vagas
coletadas, não de uma lista genérica de "top 10 skills de 2026".
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from . import db

DATA_DIR = Path(__file__).resolve().parent / "data"


def _load(name: str) -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def catalog_projects() -> list[dict[str, Any]]:
    return _load("projects.json")


def catalog_certifications() -> list[dict[str, Any]]:
    return _load("certifications.json")


def demand(limit: int = 400) -> Counter:
    """Frequência de skills nas vagas coletadas, priorizando as de maior fit.

    Lê a coluna `jobs.skills`, gravada na ingestão. Reextrair aqui — passar cem
    expressões regulares por quatrocentas descrições — custava mais de um segundo
    por abertura do Roadmap, e o resultado era exatamente o mesmo.
    """
    counter: Counter = Counter()
    for row in db.query(
        """SELECT skills FROM jobs WHERE state <> 'expirada'
           ORDER BY score DESC, last_seen_at DESC LIMIT ?""",
        (limit,),
    ):
        counter.update(set(db.loads(row["skills"], [])))
    return counter


def sample_size(limit: int = 400) -> int:
    """Quantas vagas entraram no cálculo de demanda — o denominador de `share`."""
    row = db.one("SELECT MIN(COUNT(*), ?) AS n FROM jobs WHERE state <> 'expirada'", (limit,))
    return max(1, row["n"] if row else 1)


def gaps(profile: dict[str, Any], top: int = 18, counter: Counter | None = None) -> list[dict[str, Any]]:
    """Skills mais pedidas que você ainda não tem, com o quanto aparecem."""
    counter = demand() if counter is None else counter
    total = sample_size()
    owned = set(profile.get("skills") or [])
    result = []
    for skill, count in counter.most_common():
        if skill in owned:
            continue
        result.append(
            {
                "skill": skill,
                "count": count,
                "share": round(100 * count / total),
            }
        )
        if len(result) >= top:
            break
    return result


def strengths(profile: dict[str, Any], top: int = 12, counter: Counter | None = None) -> list[dict[str, Any]]:
    """Suas skills que mais aparecem nas vagas — o que destacar no currículo."""
    counter = demand() if counter is None else counter
    owned = profile.get("skills") or []
    ranked = [
        {"skill": s, "count": counter.get(s, 0)}
        for s in owned
    ]
    ranked.sort(key=lambda item: item["count"], reverse=True)
    return ranked[:top]


def _tracked() -> dict[str, dict[str, Any]]:
    rows = db.query("SELECT * FROM learning")
    return {f"{r['kind']}:{r['ref']}": dict(r) for r in rows}


def recommend(profile: dict[str, Any], counter: Counter | None = None) -> dict[str, list[dict[str, Any]]]:
    """Projetos e certificações ordenados pelo quanto cobrem seus gaps."""
    area = profile.get("area") or "backend"
    gap_names = {g["skill"]: g["count"] for g in gaps(profile, top=40, counter=counter)}
    tracked = _tracked()

    def rank(item: dict[str, Any], kind: str) -> dict[str, Any]:
        item = dict(item)
        covered = [s for s in item.get("skills", []) if s in gap_names]
        item["covers"] = covered
        item["relevance"] = sum(gap_names.get(s, 0) for s in covered) + (
            25 if area in item.get("areas", []) else 0
        )
        item["in_area"] = area in item.get("areas", [])
        item["tracked"] = tracked.get(f"{kind}:{item['id']}")
        return item

    projects = [rank(p, "projeto") for p in catalog_projects()]
    certs = [rank(c, "certificacao") for c in catalog_certifications()]
    projects.sort(key=lambda i: (i["in_area"], i["relevance"]), reverse=True)
    certs.sort(key=lambda i: (i["in_area"], i["relevance"]), reverse=True)
    return {"projects": projects, "certifications": certs}


def track(kind: str, ref: str, title: str, url: str, status: str) -> None:
    db.execute(
        """INSERT INTO learning (kind, ref, title, url, status)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (kind, ref) DO UPDATE
             SET status = excluded.status, updated_at = datetime('now')""",
        (kind, ref, title, url, status),
    )


def untrack(kind: str, ref: str) -> None:
    db.execute("DELETE FROM learning WHERE kind = ? AND ref = ?", (kind, ref))


def board() -> dict[str, list[dict[str, Any]]]:
    """Itens marcados, agrupados por status — a lista de estudo em andamento."""
    grouped: dict[str, list[dict[str, Any]]] = {"planejado": [], "fazendo": [], "concluido": []}
    for row in db.query("SELECT * FROM learning ORDER BY updated_at DESC"):
        grouped.setdefault(row["status"], []).append(dict(row))
    return grouped
