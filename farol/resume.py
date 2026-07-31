"""Montagem de currículo e carta de apresentação.

Regra da casa: o app nunca inventa experiência. Ele reordena, destaca e formata o
que está no seu perfil, e marca com [preencher] o que falta.
"""

from __future__ import annotations

import re
from typing import Any

from . import db, skills

PLACEHOLDER = "[preencher]"

LANGS = {"pt": "Português", "en": "English"}

# Títulos das seções do currículo impresso.
SECTIONS = {
    "pt": {
        "summary": "Resumo", "skills": "Competências", "experience": "Experiência",
        "projects": "Projetos", "education": "Formação", "languages": "Idiomas",
    },
    "en": {
        "summary": "Summary", "skills": "Skills", "experience": "Experience",
        "projects": "Projects", "education": "Education", "languages": "Languages",
    },
}


def sections(lang: str) -> dict[str, str]:
    return SECTIONS.get(lang, SECTIONS["pt"])


def _job_skills(job: dict[str, Any] | None) -> list[str]:
    if not job:
        return []
    tags = db.loads(job.get("tags"), []) if isinstance(job.get("tags"), str) else (job.get("tags") or [])
    text = f"{job.get('title', '')} {' '.join(map(str, tags))} {job.get('description', '')}"
    return skills.extract(text)


def build(profile: dict[str, Any], job: dict[str, Any] | None = None) -> dict[str, Any]:
    """Gera a estrutura do currículo, priorizando o que a vaga pede."""
    wanted = _job_skills(job)
    wanted_set = set(wanted)

    owned = list(profile.get("skills") or [])
    ordered_skills = [s for s in owned if s in wanted_set] + [s for s in owned if s not in wanted_set]

    def relevance(entry: dict[str, Any]) -> int:
        text = " ".join(
            str(entry.get(field, "")) for field in ("name", "role", "org", "stack", "course", "school")
        )
        text += " " + " ".join(entry.get("bullets") or [])
        return len(set(skills.extract(text)) & wanted_set)

    projects = sorted(profile.get("projects") or [], key=relevance, reverse=True)
    experience = list(profile.get("experience") or [])

    summary = (profile.get("summary") or "").strip()
    if not summary:
        top = ", ".join(ordered_skills[:5]) or PLACEHOLDER
        role = (job or {}).get("title") or profile.get("headline") or PLACEHOLDER
        summary = (
            f"Profissional em início de carreira com foco em {role.lower()}. "
            f"Trabalho com {top}. "
            f"{PLACEHOLDER}: escreva aqui duas linhas sobre o que você entregou e o que procura."
        )

    return {
        "name": profile.get("name") or PLACEHOLDER,
        "headline": (job or {}).get("title") or profile.get("headline") or PLACEHOLDER,
        "email": profile.get("email") or PLACEHOLDER,
        "phone": profile.get("phone") or "",
        "city": profile.get("city") or "",
        "links": profile.get("links") or [],
        "summary": summary,
        "skills": ordered_skills,
        "highlight_skills": [s for s in ordered_skills if s in wanted_set],
        "experience": experience,
        "projects": projects,
        "education": profile.get("education") or [],
        "languages": profile.get("languages") or [],
        "target": {
            "title": (job or {}).get("title", ""),
            "company": (job or {}).get("company", ""),
            "url": (job or {}).get("url", ""),
        },
        "missing_skills": [s for s in wanted if s not in set(owned)],
    }


def checklist(resume: dict[str, Any]) -> list[dict[str, Any]]:
    """Verificações objetivas antes de enviar. Nada de conselho vago."""
    items: list[dict[str, Any]] = []

    def add(ok: bool, label: str, hint: str = "") -> None:
        items.append({"ok": ok, "label": label, "hint": hint})

    add(bool(resume.get("email")) and PLACEHOLDER not in resume["email"], "E-mail preenchido")
    add(bool(resume.get("phone")), "Telefone ou WhatsApp", "Recrutador ainda liga.")
    add(
        any("linkedin" in (l.get("url") or "").lower() for l in resume.get("links", [])),
        "LinkedIn no cabeçalho",
    )
    add(
        any("github" in (l.get("url") or "").lower() for l in resume.get("links", [])),
        "GitHub no cabeçalho",
        "Em vaga técnica, o link do código pesa mais que o resumo.",
    )

    bullets = [b for exp in resume.get("experience", []) for b in (exp.get("bullets") or [])]
    bullets += [b for pr in resume.get("projects", []) for b in (pr.get("bullets") or [])]
    add(len(bullets) >= 4, "Pelo menos 4 marcadores de entrega", "Currículo sem verbo de ação some.")

    with_number = [b for b in bullets if re.search(r"\d", b)]
    add(
        len(with_number) >= max(1, len(bullets) // 3),
        "Um terço dos marcadores tem número",
        "Troque 'melhorei a performance' por 'reduzi o tempo de resposta de 800ms para 200ms'.",
    )

    add(len(resume.get("skills", [])) >= 6, "Ao menos 6 competências listadas")
    add(len(resume.get("projects", [])) >= 2, "Dois projetos com link", "Primeiro emprego se ganha com projeto.")
    add(bool(resume.get("summary")) and PLACEHOLDER not in resume["summary"], "Resumo escrito por você")

    if resume.get("target", {}).get("title"):
        missing = resume.get("missing_skills") or []
        add(
            len(missing) <= 3,
            "Poucos requisitos fora do seu perfil",
            ("A vaga pede: " + ", ".join(missing[:6])) if missing else "",
        )
    return items


LETTER_TEMPLATE = """{saudacao}

Estou me candidatando à vaga de {cargo}{empresa}. {motivo}

No que a vaga pede, minha experiência mais próxima é: {experiencia}. {evidencia}

{fechamento}

{nome}
{contato}"""


LETTER_TEMPLATE_EN = """{saudacao}

{intro} {motivo}

{ponte} {experiencia}. {evidencia}

{fechamento}

{nome}
{contato}"""


def cover_letter(profile: dict[str, Any], job: dict[str, Any] | None, lang: str = "pt") -> str:
    """Rascunho honesto: estrutura pronta, com [preencher] onde só você sabe a resposta.

    O marcador continua em português nos dois idiomas — é lembrete para você, e
    justamente por destoar do texto fica difícil de esquecer lá dentro.
    """
    resume = build(profile, job)
    cargo = (job or {}).get("title") or PLACEHOLDER
    empresa = (job or {}).get("company") or ""
    matched = [skills.display(s, lang) for s in resume["highlight_skills"][:4]]
    first_project = (resume.get("projects") or [None])[0]

    contato = " · ".join(
        [v for v in [profile.get("email"), profile.get("phone")] if v]
        + [l.get("url", "") for l in (profile.get("links") or [])[:2]]
    )

    if lang == "en":
        if matched:
            experiencia = ", ".join(matched)
            if first_project:
                evidencia = f"You can see it in {first_project['name']}"
                if first_project.get("url"):
                    evidencia += f" ({first_project['url']})"
                evidencia += "."
            else:
                evidencia = f"{PLACEHOLDER}: name the project where you used it and the outcome."
        else:
            experiencia = PLACEHOLDER
            evidencia = f"{PLACEHOLDER}: describe a project of yours close to what the role asks for."
        return LETTER_TEMPLATE_EN.format(
            saudacao="Hello,",
            intro=f"I'm applying for the {cargo} position" + (f" at {empresa}." if empresa else "."),
            motivo=f"{PLACEHOLDER}: one specific sentence about the company — the product, the "
                   "engineering, something you actually read. If you can't say anything specific, "
                   "say nothing.",
            ponte="The closest experience I have to what the role asks for is:",
            experiencia=experiencia,
            evidencia=evidencia,
            fechamento="I'd be glad to talk about how I can contribute to the team.",
            nome=profile.get("name") or PLACEHOLDER,
            contato=contato,
        )

    if matched:
        experiencia = ", ".join(matched)
        if first_project:
            evidencia = f"Você encontra isso em {first_project['name']}"
            if first_project.get("url"):
                evidencia += f" ({first_project['url']})"
            evidencia += "."
        else:
            evidencia = f"{PLACEHOLDER}: cite o projeto onde usou isso e o resultado."
    else:
        experiencia = PLACEHOLDER
        evidencia = f"{PLACEHOLDER}: descreva um projeto seu que se aproxime do que a vaga pede."

    return LETTER_TEMPLATE.format(
        saudacao="Olá,",
        cargo=cargo,
        empresa=f" na {empresa}" if empresa else "",
        motivo=f"{PLACEHOLDER}: uma frase específica sobre a empresa — produto, engenharia, algo que você leu. "
               "Se não souber dizer nada específico, não escreva nada genérico.",
        experiencia=experiencia,
        evidencia=evidencia,
        fechamento="Fico à disposição para conversar sobre como posso contribuir com o time.",
        nome=profile.get("name") or PLACEHOLDER,
        contato=contato,
    )


INTERVIEW_BASE = [
    "Me conta sobre você em dois minutos.",
    "Por que essa vaga e por que esta empresa?",
    "Fale de um projeto seu do início ao fim: decisão técnica difícil e o que faria diferente.",
    "Conte uma vez em que você errou e como percebeu.",
    "Como você aprende algo que não sabe? Dê um exemplo desta semana.",
    "Qual sua pretensão salarial e por quê?",
]


def interview_questions(job: dict[str, Any] | None) -> list[str]:
    """Perguntas prováveis: as clássicas + uma por tecnologia citada na vaga."""
    questions = list(INTERVIEW_BASE)
    for skill in _job_skills(job)[:8]:
        questions.append(
            f"Onde você usou {skills.display(skill)}? Explique uma decisão que tomou com isso."
        )
    if job:
        questions.append("Que perguntas você tem sobre o time, o processo e o que se espera nos 90 dias?")
    return questions
