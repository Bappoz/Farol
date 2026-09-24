"""Assistência opcional por LLM — na nuvem ou na sua máquina.

O app funciona inteiro sem IA nenhuma: essa é a configuração padrão. Em Ajustes
você escolhe o provedor, e só então os botões de "revisar com IA" passam a existir.

    (nenhum)     o que vem de fábrica. Zero requisição, zero botão.
    anthropic    a API da Anthropic, com a sua chave. O texto sai da máquina.
    local        um servidor que você subiu (Ollama, LM Studio, llama.cpp, Jan).
                 O texto não sai da sua rede — ver `farol.localai`.

A instrução de sistema é a mesma nos dois caminhos, e é ela que segura a única
regra que não se negocia: o modelo reescreve o que já está no seu perfil e não
inventa experiência. Um currículo com uma linha inventada não é um currículo
melhor; é uma entrevista perdida na primeira pergunta.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from . import db, localai

ENDPOINT = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

PROVIDERS = {
    "": {"label": "Nenhum", "hint": "O app funciona inteiro sem IA."},
    "anthropic": {"label": "API Anthropic", "hint": "O texto sai da sua máquina."},
    "local": {"label": "Modelo local", "hint": "O texto não sai da sua rede."},
}

SYSTEM = (
    "Você revisa currículos e cartas de apresentação em português do Brasil para uma pessoa "
    "em busca do primeiro emprego. Regras invioláveis:\n"
    "1. Nunca invente experiência, empresa, número, diploma ou tecnologia que não esteja nos dados "
    "recebidos. Se faltar informação, escreva [preencher] e diga o que falta.\n"
    "2. Prefira verbo de ação e resultado concreto a adjetivo. Corte 'apaixonado por tecnologia', "
    "'proativo', 'buscando desafios' e afins.\n"
    "3. Português direto, sem jargão de IA, sem elogio à empresa que qualquer um poderia escrever.\n"
    "4. Responda apenas com o texto pedido, sem introdução nem comentário."
)


def provider() -> str:
    """Provedor em uso: '', 'anthropic' ou 'local'.

    O ajuste vazio com uma chave gravada continua valendo como Anthropic: quem
    configurou a chave antes de este seletor existir não perde o assistente ao
    atualizar o app.
    """
    settings = db.get_settings()
    escolhido = (settings.get("ai_provider") or "").strip()
    if escolhido in ("anthropic", "local"):
        return escolhido
    return "anthropic" if (settings.get("anthropic_api_key") or "").strip() else ""


def available() -> bool:
    return provider() != ""


def describe() -> dict[str, Any]:
    """Como a tela de Ajustes descreve o assistente hoje."""
    settings = db.get_settings()
    atual = provider()
    if atual == "anthropic":
        modelo = settings.get("anthropic_model") or ""
        pronto = bool((settings.get("anthropic_api_key") or "").strip())
        falta = "" if pronto else "falta a chave da API."
    elif atual == "local":
        modelo = settings.get("local_ai_model") or ""
        pronto = bool(modelo.strip())
        falta = "" if pronto else "falta escolher o modelo instalado."
    else:
        modelo, pronto, falta = "", False, ""
    return {
        "provider": atual,
        "label": PROVIDERS[atual]["label"],
        "model": modelo,
        "ready": pronto,
        "pending": falta,
    }


def _anthropic(prompt: str, max_tokens: int) -> str:
    settings = db.get_settings()
    key = (settings.get("anthropic_api_key") or "").strip()
    if not key:
        raise RuntimeError("Nenhuma chave da API configurada em Ajustes.")
    payload = {
        "model": settings.get("anthropic_model") or "claude-sonnet-5",
        "max_tokens": max_tokens,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }
    with httpx.Client(timeout=90) as client:
        response = client.post(ENDPOINT, json=payload, headers=headers)
    if response.status_code >= 400:
        detail = response.text[:300]
        raise RuntimeError(f"API respondeu {response.status_code}: {detail}")
    data = response.json()
    parts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
    return "\n".join(parts).strip()


def complete(prompt: str, max_tokens: int = 1200) -> str:
    atual = provider()
    if atual == "anthropic":
        return _anthropic(prompt, max_tokens)
    if atual == "local":
        return localai.complete(prompt, SYSTEM, max_tokens=max_tokens)
    raise RuntimeError("Nenhum assistente de IA configurado em Ajustes.")


def _context(resume: dict[str, Any], job: dict[str, Any] | None) -> str:
    payload: dict[str, Any] = {"curriculo": resume}
    if job:
        payload["vaga"] = {
            "titulo": job.get("title"),
            "empresa": job.get("company"),
            "descricao": (job.get("description") or "")[:6000],
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class EchoedContext(RuntimeError):
    """O modelo devolveu o contexto em vez de escrever o texto pedido."""


def _sem_eco(texto: str) -> str:
    """Recusa a resposta quando o modelo só repetiu o JSON que recebeu.

    Modelo pequeno (abaixo de ~3B) às vezes devolve o contexto inteiro em vez de
    responder. Gravar isso seria encher o currículo com o JSON do próprio
    currículo — melhor tratar como etapa que falhou e dizer isso na tela.
    """
    limpo = texto.strip()
    if limpo.startswith(("{", "[")) and ('"curriculo"' in limpo or '"vaga"' in limpo):
        raise EchoedContext(
            "o modelo repetiu os dados em vez de escrever o texto; "
            "tente um modelo maior (ver o catálogo em Ajustes)"
        )
    return texto


def _idioma(lang: str) -> str:
    return ("Escreva a resposta em inglês (o currículo é em inglês). "
            if lang == "en" else "Escreva a resposta em português do Brasil. ")


def tailor_summary(resume: dict[str, Any], job: dict[str, Any] | None, lang: str = "pt") -> str:
    return _sem_eco(complete(
        _idioma(lang)
        + "Reescreva o campo 'summary' do currículo abaixo em no máximo 4 linhas, direcionado à vaga "
        "quando ela existir. Use apenas fatos presentes nos dados.\n\n" + _context(resume, job),
        max_tokens=500,
    ))


def tailor_bullets(resume: dict[str, Any], job: dict[str, Any] | None, lang: str = "pt") -> str:
    return _sem_eco(complete(
        _idioma(lang)
        + "Reescreva os marcadores de experiência e projetos do currículo abaixo. Um marcador por linha, "
        "começando com verbo de ação, mantendo os fatos originais e explicitando resultado quando o dado "
        "existir. Agrupe por item usando o nome do projeto ou cargo como cabeçalho.\n\n"
        + _context(resume, job),
        max_tokens=1500,
    ))


def polish_letter(letter: str, resume: dict[str, Any], job: dict[str, Any] | None,
                  lang: str = "pt") -> str:
    return _sem_eco(complete(
        _idioma(lang)
        + "Revise a carta de apresentação abaixo mantendo a estrutura e o tamanho (no máximo 200 palavras). "
        "Preserve os marcadores [preencher] que o candidato ainda precisa responder.\n\n"
        f"CARTA:\n{letter}\n\nDADOS:\n" + _context(resume, job),
        max_tokens=900,
    ))


# Etapas da geração dirigida a uma vaga, na ordem em que rodam. Cada uma é uma
# ida e volta ao modelo: três chamadas curtas erram menos que uma longa pedindo
# JSON — e, num modelo pequeno rodando local, "erra menos" é a diferença entre
# funcionar e não funcionar.
TAILOR_STEPS = ("resumo", "marcadores", "carta")


def tailor_for_job(resume: dict[str, Any], letter: str, job: dict[str, Any] | None,
                   lang: str = "pt") -> tuple[dict[str, Any], str, list[str]]:
    """Currículo e carta reescritos para a vaga. Devolve (dados, carta, o que falhou).

    Uma etapa que falha não derruba as outras: com modelo local, tempo esgotado
    numa delas é rotina, e perder o resumo já pronto por causa da carta seria o
    pior desfecho. Os nomes das etapas que falharam voltam para a tela dizer.
    """
    dados = dict(resume)
    falhas: list[str] = []

    try:
        dados["summary"] = tailor_summary(dados, job, lang)
    except Exception as exc:  # noqa: BLE001 — provedor externo: a falha é informação, não erro do app
        falhas.append(f"resumo ({exc})")

    try:
        dados["ai_bullets"] = tailor_bullets(dados, job, lang)
    except Exception as exc:  # noqa: BLE001 — idem
        falhas.append(f"marcadores ({exc})")

    nova_carta = letter
    try:
        nova_carta = polish_letter(letter, dados, job, lang)
    except Exception as exc:  # noqa: BLE001 — idem
        falhas.append(f"carta ({exc})")

    return dados, nova_carta, falhas
