"""Vagas BR — os murais de vaga que a comunidade brasileira mantém no GitHub.

`backend-br/vagas`, `frontendbr/vagas` e companhia publicam cada vaga como uma
issue. É a fonte de vaga em português mais consistente que existe com API
pública: sem chave, sem scraping, e o anúncio já vem estruturado — o título
carrega o modelo de trabalho entre colchetes, as labels trazem as tecnologias e
o corpo começa com `## Nossa empresa`.

Diferente dos portais internacionais, aqui não mandamos termo de busca: cada
repositório já é a seleção (vagas de back-end, de front-end, de dados). Filtrar
anúncio em português por termo escrito para portal em inglês — `junior backend`,
`entry level data` — devolveria lista vazia. A rodada traz tudo e o fit score
ordena, que é o mesmo tratamento dado a um feed RSS cadastrado pelo usuário.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

API = "https://api.github.com/repos/{repo}/issues"
PER_PAGE = 30

# Um repositório por área. A lista é curta de propósito: cada um custa uma
# requisição, e a API do GitHub sem token permite 60 por hora.
REPOS = [
    ("backend-br/vagas", "Back-end"),
    ("frontendbr/vagas", "Front-end"),
    ("react-brasil/vagas", "React"),
    ("androiddevbr/vagas", "Android"),
    ("phpdevbr/vagas", "PHP"),
    ("datascience-br/vagas", "Dados"),
]

# marcadores entre colchetes no começo do título: [Remoto], [100% Remoto], [PJ]…
_BRACKET = re.compile(r"^\s*(?:\[[^\]]*\]\s*)+")
_TAGS_IN_TITLE = re.compile(r"\[([^\]]+)\]")
_COMPANY_SECTION = re.compile(r"##\s*Nossa empresa\s*\n+([^\n#]+)", re.I)
# "Analista de dados na Acme" / "Dev Python @ Acme (São Paulo)"
_COMPANY_SUFFIX = re.compile(
    r"\s+(?:na|no|@)\s+([^\[\]()]{2,60}?)\s*(?:\([^)]*\))?\s*$", re.I
)

PRESENCIAL = ("presencial", "on-site", "onsite")
HIBRIDO = ("hibrido", "híbrido", "hybrid")


def _sem_acento(text: str) -> str:
    return (text.lower()
            .replace("í", "i").replace("é", "e").replace("ó", "o")
            .replace("á", "a").replace("ã", "a").replace("ç", "c"))


def _company(title: str, body: str) -> str:
    """Empresa: primeiro a seção `## Nossa empresa`, depois o sufixo do título."""
    found = _COMPANY_SECTION.search(body or "")
    if found and found.group(1).strip():
        return found.group(1).strip()
    found = _COMPANY_SUFFIX.search(title)
    return found.group(1).strip() if found else ""


def _role(title: str) -> str:
    """Cargo sem os colchetes e sem o sufixo de empresa."""
    limpo = _BRACKET.sub("", title).strip()
    return _COMPANY_SUFFIX.sub("", limpo).strip() or title.strip()


def parse_issue(issue: dict[str, Any], repo: str, area: str) -> dict[str, Any] | None:
    """Converte uma issue no formato comum dos coletores. None se não for vaga."""
    if not isinstance(issue, dict) or "pull_request" in issue:
        return None  # a API devolve pull requests na mesma rota
    title = (issue.get("title") or "").strip()
    url = issue.get("html_url") or ""
    if not title or not url:
        return None

    body = issue.get("body") or ""
    labels = [str(label.get("name") or "") for label in (issue.get("labels") or [])
              if isinstance(label, dict)]
    marcadores = _sem_acento(" ".join(_TAGS_IN_TITLE.findall(title) + labels))

    presencial = any(m in marcadores for m in PRESENCIAL)
    hibrido = any(_sem_acento(m) in marcadores for m in HIBRIDO)
    # o modelo de trabalho vai para a localização porque é lá que scoring.work_mode
    # e scoring.region procuram — e estes murais são todos de vaga no Brasil
    modelo = "Presencial" if presencial else "Híbrido" if hibrido else "Remoto"

    return {
        "source_id": url.rsplit("/", 1)[-1] + "@" + repo,
        "title": _role(title),
        "company": _company(title, body),
        "url": url,
        "apply_url": url,
        "location": f"Brasil · {modelo}",
        "remote": not presencial,
        "salary": "",
        "tags": [*labels, area],
        "description": body,
        "published_at": issue.get("created_at"),
    }


def fetch(client: httpx.Client, query: str) -> list[dict[str, Any]]:
    """Percorre os murais. `query` é ignorado — veja o porquê no topo do módulo."""
    items: list[dict[str, Any]] = []
    erros: list[str] = []
    for repo, area in REPOS:
        try:
            response = client.get(
                API.format(repo=repo),
                params={"state": "open", "per_page": PER_PAGE, "sort": "created"},
                headers={"Accept": "application/vnd.github+json"},
            )
            if response.status_code == 403:
                # 60 requisições por hora sem token; a mensagem precisa dizer isso
                raise RuntimeError(
                    "limite de requisições da API do GitHub atingido — tente de novo em uma hora"
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 — um mural fora do ar não derruba os outros
            erros.append(f"{repo}: {exc}")
            continue
        if not isinstance(payload, list):
            continue
        for issue in payload:
            parsed = parse_issue(issue, repo, area)
            if parsed:
                items.append(parsed)
    if not items and erros:
        raise RuntimeError("; ".join(erros))
    return items
