"""Assistência opcional por LLM (Claude).

O app funciona inteiro sem chave de API. Com uma chave configurada em Ajustes, os
botões de "revisar com IA" passam a existir. A instrução de sistema proíbe inventar
experiência: o modelo só reescreve o que já está no seu perfil.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from . import db

ENDPOINT = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

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


def available() -> bool:
    return bool((db.get_settings().get("anthropic_api_key") or "").strip())


def complete(prompt: str, max_tokens: int = 1200) -> str:
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


def _context(resume: dict[str, Any], job: dict[str, Any] | None) -> str:
    payload: dict[str, Any] = {"curriculo": resume}
    if job:
        payload["vaga"] = {
            "titulo": job.get("title"),
            "empresa": job.get("company"),
            "descricao": (job.get("description") or "")[:6000],
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _idioma(lang: str) -> str:
    return ("Escreva a resposta em inglês (o currículo é em inglês). "
            if lang == "en" else "Escreva a resposta em português do Brasil. ")


def tailor_summary(resume: dict[str, Any], job: dict[str, Any] | None, lang: str = "pt") -> str:
    return complete(
        _idioma(lang)
        + "Reescreva o campo 'summary' do currículo abaixo em no máximo 4 linhas, direcionado à vaga "
        "quando ela existir. Use apenas fatos presentes nos dados.\n\n" + _context(resume, job),
        max_tokens=500,
    )


def tailor_bullets(resume: dict[str, Any], job: dict[str, Any] | None, lang: str = "pt") -> str:
    return complete(
        _idioma(lang)
        + "Reescreva os marcadores de experiência e projetos do currículo abaixo. Um marcador por linha, "
        "começando com verbo de ação, mantendo os fatos originais e explicitando resultado quando o dado "
        "existir. Agrupe por item usando o nome do projeto ou cargo como cabeçalho.\n\n"
        + _context(resume, job),
        max_tokens=1500,
    )


def polish_letter(letter: str, resume: dict[str, Any], job: dict[str, Any] | None,
                  lang: str = "pt") -> str:
    return complete(
        _idioma(lang)
        + "Revise a carta de apresentação abaixo mantendo a estrutura e o tamanho (no máximo 200 palavras). "
        "Preserve os marcadores [preencher] que o candidato ainda precisa responder.\n\n"
        f"CARTA:\n{letter}\n\nDADOS:\n" + _context(resume, job),
        max_tokens=900,
    )
