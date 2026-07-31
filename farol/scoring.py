"""Fit score determinístico e explicável.

Nada de caixa-preta: cada componente vale um número fixo e devolve a frase que
justifica a nota. O total é 0–100.

    skills      0–55   quanto do que a vaga pede você já tem
    senioridade 0–20   vaga de entrada pontua; vaga sênior derruba
    região      0–10   aceita quem está no Brasil / América Latina
    recência    0–10   vaga de hoje vale mais que vaga de três semanas
    preferência 0–5    suas palavras-chave; termos excluídos zeram a vaga
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from . import skills as sk

WORK_MODES = ["remoto", "hibrido", "presencial"]
WORK_MODE_LABELS = {"remoto": "Remoto", "hibrido": "Híbrido", "presencial": "Presencial"}

# as fontes só marcam remote:boolean — híbrido só aparece se o texto disser
HYBRID_MARKERS = ["hibrido", "hibrida", "hybrid"]

REGION_TERMS = {
    "brazil": ["brazil", "brasil", "latam", "latin america", "america latina", "south america",
               "worldwide", "anywhere", "global", "remote", "americas"],
    "latam": ["latam", "latin america", "america latina", "south america", "worldwide",
              "anywhere", "global", "remote", "americas", "brazil", "brasil"],
    "worldwide": ["worldwide", "anywhere", "global", "remote"],
}

REGION_BLOCKERS = [
    "us only", "usa only", "united states only", "us based", "u s based", "eu only",
    "europe only", "uk only", "canada only", "must be located in the united states",
    "authorized to work in the us", "eligible to work in the uk", "germany only",
]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def days_old(published_at: str | None) -> int | None:
    parsed = _parse_date(published_at)
    if not parsed:
        return None
    delta = datetime.now(timezone.utc) - parsed
    return max(0, delta.days)


def work_mode(job: dict[str, Any]) -> str:
    """remoto | hibrido | presencial — híbrido só é detectável pelo texto."""
    text = " ".join(str(job.get(field) or "") for field in ("title", "location", "description"))
    if sk.has_marker(text, HYBRID_MARKERS):
        return "hibrido"
    return "remoto" if job.get("remote") else "presencial"


_SALARY_NUMBER = re.compile(r"\d[\d.,]*")


def salary_range(raw: str | None) -> tuple[int, int] | None:
    """(mínimo, máximo) em USD/ano a partir do texto livre de salário — melhor esforço.

    Só reconhece números com ponto ou vírgula como separador de milhar, que é o formato
    usado por Remotive, RemoteOK e Himalayas. Vaga sem número reconhecível fica de fora
    do filtro de salário — não vira zero.
    """
    if not raw:
        return None
    numbers = [
        int(cleaned)
        for match in _SALARY_NUMBER.findall(raw)
        if (cleaned := match.replace(".", "").replace(",", ""))
    ]
    if not numbers:
        return None
    return min(numbers), max(numbers)


def score_job(job: dict[str, Any], profile: dict[str, Any], settings: dict[str, str]) -> dict[str, Any]:
    """Devolve {'score': int, 'components': [...], 'matched': [...], 'missing': [...], 'flags': [...]}"""
    text = " ".join(
        str(job.get(field) or "")
        for field in ("title", "description", "location", "salary")
    )
    tags = job.get("tags") or []
    if isinstance(tags, list):
        text += " " + " ".join(str(t) for t in tags)

    required = sk.extract(text)
    owned = [s for s in (profile.get("skills") or [])]
    owned_set = set(owned)
    matched = [s for s in required if s in owned_set]
    missing = [s for s in required if s not in owned_set]

    components: list[dict[str, Any]] = []
    flags: list[str] = []

    # --- skills (55)
    if required:
        base = max(4, min(len(required), 10))  # vagas com 20 termos não devem diluir tudo
        ratio = min(1.0, len(matched) / base)
        skill_points = round(55 * ratio)
        detail = f"{len(matched)} de {len(required)} tecnologias citadas você já tem"
    else:
        skill_points = 22
        detail = "descrição sem tecnologias reconhecidas — nota neutra"
    components.append({"label": "Skills", "points": skill_points, "max": 55, "detail": detail})

    # --- senioridade (20)
    title = str(job.get("title") or "")
    entry_title = sk.has_marker(title, sk.ENTRY_MARKERS)
    senior_title = sk.has_marker(title, sk.SENIOR_MARKERS)
    entry_body = sk.has_marker(text, sk.ENTRY_MARKERS)
    senior_body = sk.has_marker(text, sk.SENIOR_MARKERS)
    target = profile.get("seniority") or "junior"

    if target in ("estagio", "junior"):
        if senior_title:
            seniority_points, detail = 0, "título indica vaga sênior/liderança"
            flags.append("senioridade acima do seu alvo")
        elif entry_title:
            seniority_points, detail = 20, "título é de vaga de entrada"
        elif entry_body:
            seniority_points, detail = 14, "descrição menciona nível de entrada"
        elif senior_body:
            seniority_points, detail = 5, "descrição pede anos de experiência"
        else:
            seniority_points, detail = 10, "nível não declarado"
    else:
        if senior_title or senior_body:
            seniority_points, detail = 20, "nível compatível com o seu alvo"
        elif entry_title:
            seniority_points, detail = 8, "vaga de entrada, abaixo do seu alvo"
        else:
            seniority_points, detail = 12, "nível não declarado"
    components.append({"label": "Senioridade", "points": seniority_points, "max": 20, "detail": detail})

    # --- região (10)
    preference = settings.get("region_preference", "brazil")
    accepted = REGION_TERMS.get(preference, REGION_TERMS["brazil"])
    where = sk.normalize(f"{job.get('location') or ''} {title}")
    body = sk.normalize(text)
    if any(term in body for term in (sk.normalize(b) for b in REGION_BLOCKERS)):
        region_points, detail = 0, "vaga restrita a outro país"
        flags.append("restrição geográfica")
    elif any(sk.normalize(term) in where for term in accepted):
        region_points, detail = 10, f"aceita candidatos de fora ({job.get('location') or 'remoto'})"
    elif job.get("remote"):
        region_points, detail = 6, "remota, mas sem região explícita"
    else:
        region_points, detail = 3, "não declarada como remota"
    components.append({"label": "Região", "points": region_points, "max": 10, "detail": detail})

    # --- recência (10)
    age = days_old(job.get("published_at"))
    if age is None:
        fresh_points, detail = 5, "sem data de publicação"
    elif age <= 3:
        fresh_points, detail = 10, "publicada nos últimos 3 dias"
    elif age <= 30:
        fresh_points = round(10 - (age - 3) * (10 / 27))
        detail = f"publicada há {age} dias"
    else:
        fresh_points, detail = 0, f"publicada há {age} dias"
        flags.append("vaga antiga")
    components.append({"label": "Recência", "points": fresh_points, "max": 10, "detail": detail})

    # --- preferências (5)
    wanted = [w.strip() for w in (settings.get("keywords") or "").split(",") if w.strip()]
    excluded = [w.strip() for w in (settings.get("exclude_keywords") or "").split(",") if w.strip()]
    hit = [w for w in wanted if sk.normalize(w) and sk.normalize(w) in body]
    blocked = [w for w in excluded if sk.normalize(w) and sk.normalize(w) in sk.normalize(title)]
    if blocked:
        pref_points = 0
        detail = "título contém termo excluído: " + ", ".join(blocked)
        flags.append("termo excluído no título")
    elif hit:
        pref_points, detail = 5, "combina com: " + ", ".join(hit)
    else:
        pref_points, detail = 2, "sem palavras-chave suas"
    components.append({"label": "Preferências", "points": pref_points, "max": 5, "detail": detail})

    total = sum(c["points"] for c in components)
    if blocked:
        total = min(total, 25)  # não some da lista, mas afunda

    return {
        "score": int(max(0, min(100, total))),
        "components": components,
        "matched": matched,
        "missing": missing,
        "flags": flags,
    }


def label(score: int) -> str:
    if score >= 70:
        return "forte"
    if score >= 50:
        return "possível"
    if score >= 30:
        return "fraco"
    return "descartável"
