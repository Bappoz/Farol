"""Montagem de currículo e carta de apresentação.

Regra da casa: o app nunca inventa experiência. Ele reordena, destaca e formata o
que está no seu perfil, e marca com [preencher] o que falta.
"""

from __future__ import annotations

import copy
from typing import Any

from . import db, skills

PLACEHOLDER = "[preencher]"

LANGS = {"pt": "Português", "en": "English"}

# Modelos de apresentação do currículo. Mudam a aparência e a ordem das seções —
# o conteúdo é o mesmo, então trocar de modelo nunca perde texto seu.
#
# `sober` é o recomendado de propósito: uma coluna, sem cor de fundo, sem ícone e
# sem coluna lateral é o que um filtro de ATS lê sem erro, e ATS é o primeiro
# leitor de quase toda candidatura. Harvard e FAANG são os dois padrões que mais
# circulam em processo seletivo de tecnologia e também são de uma coluna. O
# Designer é o único de duas colunas: existe para quando uma pessoa abre o PDF
# direto (indicação, feira, portfólio), e o verificador ATS avisa do risco.
DEFAULT_ORDER = ("summary", "skills", "experience", "projects", "education", "languages")

TEMPLATES: dict[str, dict[str, Any]] = {
    "sober": {
        "label": "Sóbrio",
        "hint": "Uma coluna, sem enfeite. É o que passa limpo por filtro de ATS.",
        "recommended": True,
    },
    "harvard": {
        "label": "Harvard",
        "hint": "O padrão acadêmico americano: serifado, nome centralizado e formação antes da experiência.",
        "recommended": False,
        "order": ("summary", "education", "experience", "projects", "skills", "languages"),
    },
    "faang": {
        "label": "FAANG",
        "hint": "O formato denso das big techs: experiência e projetos primeiro, competências no fim, tudo em uma página.",
        "recommended": False,
        "order": ("summary", "experience", "projects", "education", "skills", "languages"),
    },
    "compacto": {
        "label": "Compacto",
        "hint": "Mesma estrutura em espaçamento menor — ajuda a caber em uma página.",
        "recommended": False,
    },
    "destaque": {
        "label": "Com destaque",
        "hint": "Nome e títulos de seção em cor de acento. Bom quando uma pessoa lê antes do robô.",
        "recommended": False,
    },
    "moderno": {
        "label": "Moderno",
        "hint": "Sem serifa, nome grande e barra no título da seção. Mais cara de produto.",
        "recommended": False,
    },
    "designer": {
        "label": "Designer",
        "hint": "Duas colunas com barra lateral colorida. Bonito na mão de uma pessoa; parser de ATS embaralha a ordem.",
        "recommended": False,
        "layout": "duas-colunas",
        "side": ("skills", "education", "languages"),
        "order": ("summary", "experience", "projects"),
    },
}

DEFAULT_TEMPLATE = "sober"


def template_or_default(value: str | None) -> str:
    return value if value in TEMPLATES else DEFAULT_TEMPLATE


def layout(template: str | None) -> dict[str, Any]:
    """Como o modelo distribui as seções na folha: colunas, ordem e barra lateral."""
    meta = TEMPLATES[template_or_default(template)]
    return {
        "columns": meta.get("layout", "uma-coluna"),
        "order": tuple(meta.get("order", DEFAULT_ORDER)),
        "side": tuple(meta.get("side", ())),
    }


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


def _relevance(entry: dict[str, Any], wanted: set[str]) -> int:
    """Quantas skills pedidas pela vaga o item (projeto, experiência) cita."""
    text = " ".join(
        str(entry.get(field, "")) for field in ("name", "role", "org", "stack", "course", "school")
    )
    text += " " + " ".join(entry.get("bullets") or [])
    return len(set(skills.extract(text)) & wanted)


def build(profile: dict[str, Any], job: dict[str, Any] | None = None) -> dict[str, Any]:
    """Gera a estrutura do currículo, priorizando o que a vaga pede."""
    wanted = _job_skills(job)
    wanted_set = set(wanted)

    owned = list(profile.get("skills") or [])
    ordered_skills = [s for s in owned if s in wanted_set] + [s for s in owned if s not in wanted_set]

    projects = sorted(profile.get("projects") or [], key=lambda p: _relevance(p, wanted_set), reverse=True)
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


# Sobras de uma revisão anterior que não fazem sentido na cópia: a sugestão de
# marcadores e o parecer da IA foram escritos para outra vaga.
_DERIVED_ONLY = ("ai_bullets", "ats_ai")


def retarget(data: dict[str, Any], job: dict[str, Any] | None,
             owned: list[str] | None = None) -> dict[str, Any]:
    """Cópia de um currículo já lapidado, apontada para outra vaga (ou para nenhuma).

    O texto é preservado inteiro — é para isso que se parte de um currículo
    pronto e não do Perfil. Muda só o que depende da vaga: a ordem das
    competências e dos projetos, o que a vaga pede e você não tem, e o alvo.
    O cargo pretendido fica como estava; o verificador ATS avisa se ele não
    conversa com o título do anúncio, e a decisão de trocar é sua.
    """
    novo = copy.deepcopy(data)
    for key in _DERIVED_ONLY:
        novo.pop(key, None)

    wanted = _job_skills(job)
    wanted_set = set(wanted)
    chosen = list(novo.get("skills") or [])
    novo["skills"] = [s for s in chosen if s in wanted_set] + [s for s in chosen if s not in wanted_set]
    novo["highlight_skills"] = [s for s in novo["skills"] if s in wanted_set]
    # "não tem" se mede contra o Perfil: desmarcar uma skill neste currículo não a apaga de você
    have = set(owned if owned is not None else chosen) | set(chosen)
    novo["missing_skills"] = [s for s in wanted if s not in have]
    novo["projects"] = sorted(
        novo.get("projects") or [], key=lambda p: _relevance(p, wanted_set), reverse=True
    )
    novo["target"] = {
        "title": (job or {}).get("title", ""),
        "company": (job or {}).get("company", ""),
        "url": (job or {}).get("url", ""),
    }
    return novo


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
        + [link.get("url", "") for link in (profile.get("links") or [])[:2]]
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
