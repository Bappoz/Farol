"""Métricas da própria busca: conversão, tempo entre etapas e o que dá retorno.

O Farol registra cada mudança de etapa com data desde a primeira candidatura, e
até aqui nunca devolvia isso como informação. A diferença importa: quarenta
candidaturas sem nenhuma triagem é problema de currículo; quarenta candidaturas
com doze triagens e nenhuma entrevista é problema de conversa técnica. São
diagnósticos opostos, e sem os números não dá para distinguir um do outro.

Tudo aqui é descritivo. Não há previsão, modelo nem recomendação automática: as
contas são as que qualquer pessoa faria à mão se tivesse os dados na frente.
"""

from __future__ import annotations

import itertools
import statistics
from datetime import date, datetime, timedelta
from typing import Any

from . import db

# O funil são as etapas por onde a candidatura avança. 'encerrada' fica de fora
# porque é desfecho, não progresso: uma candidatura encerrada depois da
# entrevista chegou à entrevista, e é isso que o funil precisa contar.
FUNNEL = [status for status in db.STATUSES if status != "encerrada"]

# A partir daqui houve resposta de alguém do outro lado — o divisor de águas
# entre "enviei" e "me responderam".
RESPONDEU = "triagem"

# Amostra abaixo da qual um percentual engana mais do que informa.
MINIMO_PARA_PERCENTUAL = 5


def _rank(status: str) -> int:
    return FUNNEL.index(status) if status in FUNNEL else -1


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def stage_reached() -> dict[int, str]:
    """Etapa mais avançada que cada candidatura alcançou, não a etapa atual.

    Uma candidatura recusada depois da entrevista está hoje em 'encerrada'; para
    o funil, ela chegou à entrevista.
    """
    reached = {row["id"]: row["status"] for row in db.query("SELECT id, status FROM applications")}
    for row in db.query("SELECT application_id, to_status FROM events WHERE to_status <> ''"):
        atual = reached.get(row["application_id"])
        if atual is not None and _rank(row["to_status"]) > _rank(atual):
            reached[row["application_id"]] = row["to_status"]
    return reached


def funnel(reached: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """Quantas candidaturas chegaram a cada etapa, com a conversão de uma à outra."""
    reached = stage_reached() if reached is None else reached
    linhas: list[dict[str, Any]] = []
    for indice, status in enumerate(FUNNEL):
        quantas = sum(1 for alcancada in reached.values() if _rank(alcancada) >= indice)
        linhas.append({"status": status, "label": db.STATUS_LABELS[status], "count": quantas})
    total = linhas[0]["count"] if linhas else 0
    for indice, linha in enumerate(linhas):
        linha["share"] = round(100 * linha["count"] / total) if total else 0
        anterior = linhas[indice - 1]["count"] if indice else 0
        linha["step"] = round(100 * linha["count"] / anterior) if indice and anterior else None
    return linhas


def _first_timestamps() -> dict[int, dict[str, datetime]]:
    """Primeira vez que cada candidatura entrou em cada etapa."""
    marcos: dict[int, dict[str, datetime]] = {}
    for row in db.query(
        """SELECT application_id, to_status, created_at FROM events
           WHERE to_status <> '' ORDER BY created_at, id"""
    ):
        quando = _parse(row["created_at"])
        if quando is None:
            continue
        por_etapa = marcos.setdefault(row["application_id"], {})
        por_etapa.setdefault(row["to_status"], quando)
    return marcos


def stage_durations() -> list[dict[str, Any]]:
    """Dias medianos entre uma etapa e a seguinte, com o tamanho da amostra."""
    marcos = _first_timestamps()
    resultado = []
    for origem, destino in itertools.pairwise(FUNNEL):
        dias = [
            (por_etapa[destino] - por_etapa[origem]).total_seconds() / 86400
            for por_etapa in marcos.values()
            if origem in por_etapa and destino in por_etapa
            and por_etapa[destino] >= por_etapa[origem]
        ]
        resultado.append({
            "de": db.STATUS_LABELS[origem],
            "para": db.STATUS_LABELS[destino],
            "dias": round(statistics.median(dias)) if dias else None,
            "amostra": len(dias),
        })
    return resultado


def weekly(weeks: int = 8) -> list[dict[str, Any]]:
    """Candidaturas enviadas e respostas recebidas, semana a semana."""
    hoje = date.today()
    inicio_atual = hoje - timedelta(days=hoje.weekday())
    semanas = [inicio_atual - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
    corte = semanas[0].isoformat()

    enviadas: dict[str, int] = {}
    for row in db.query(
        "SELECT applied_at FROM applications WHERE applied_at IS NOT NULL AND applied_at >= ?",
        (corte,),
    ):
        quando = _parse(row["applied_at"])
        if quando:
            dia = quando.date()
            enviadas[(dia - timedelta(days=dia.weekday())).isoformat()] = \
                enviadas.get((dia - timedelta(days=dia.weekday())).isoformat(), 0) + 1

    respostas: dict[str, int] = {}
    avancadas = FUNNEL[_rank(RESPONDEU):]
    marcadores = ",".join("?" for _ in avancadas)
    for row in db.query(
        f"""SELECT created_at FROM events
            WHERE to_status IN ({marcadores}) AND created_at >= ?""",
        (*avancadas, corte),
    ):
        quando = _parse(row["created_at"])
        if quando:
            dia = quando.date()
            chave = (dia - timedelta(days=dia.weekday())).isoformat()
            respostas[chave] = respostas.get(chave, 0) + 1

    linhas = [
        {
            "semana": inicio.isoformat(),
            "rotulo": inicio.strftime("%d/%m"),
            "enviadas": enviadas.get(inicio.isoformat(), 0),
            "respostas": respostas.get(inicio.isoformat(), 0),
        }
        for inicio in semanas
    ]
    teto = max([max(linha["enviadas"], linha["respostas"]) for linha in linhas], default=0)
    for linha in linhas:
        linha["altura_enviadas"] = round(100 * linha["enviadas"] / teto) if teto else 0
        linha["altura_respostas"] = round(100 * linha["respostas"] / teto) if teto else 0
    return linhas


def stalled(days: int = 10) -> list[dict[str, Any]]:
    """Candidaturas ativas sem nenhum movimento há mais de `days` dias."""
    corte = (datetime.now() - timedelta(days=days)).isoformat(sep=" ", timespec="seconds")
    return [
        dict(row) | {"parada_ha": (datetime.now() - (_parse(row["updated_at"]) or datetime.now())).days}
        for row in db.query(
            """SELECT id, title, company, status, updated_at FROM applications
               WHERE status NOT IN ('encerrada', 'oferta') AND updated_at < ?
               ORDER BY updated_at LIMIT 12""",
            (corte,),
        )
    ]


def fit_by_outcome() -> dict[str, Any]:
    """Fit médio das vagas que responderam × das que não responderam.

    Serve para conferir se a própria pontuação prevê alguma coisa. Só aparece com
    amostra suficiente: com três candidaturas, a média não diz nada.
    """
    reached = stage_reached()
    limite = _rank(RESPONDEU)
    responderam, ignoraram = [], []
    for row in db.query(
        """SELECT a.id, j.score FROM applications a
           JOIN jobs j ON j.id = a.job_id WHERE a.job_id IS NOT NULL"""
    ):
        alvo = responderam if _rank(reached.get(row["id"], "")) >= limite else ignoraram
        alvo.append(row["score"])

    def media(valores: list[int]) -> int | None:
        return round(statistics.mean(valores)) if valores else None

    total = len(responderam) + len(ignoraram)
    return {
        "responderam": media(responderam),
        "ignoraram": media(ignoraram),
        "n_responderam": len(responderam),
        "n_ignoraram": len(ignoraram),
        "confiavel": total >= MINIMO_PARA_PERCENTUAL and bool(responderam) and bool(ignoraram),
    }


def by_source() -> list[dict[str, Any]]:
    """De qual portal saem as candidaturas que avançam."""
    reached = stage_reached()
    limite = _rank(RESPONDEU)
    por_fonte: dict[str, dict[str, Any]] = {}
    for row in db.query(
        """SELECT a.id, j.source FROM applications a
           JOIN jobs j ON j.id = a.job_id WHERE a.job_id IS NOT NULL"""
    ):
        linha = por_fonte.setdefault(row["source"], {"source": row["source"], "enviadas": 0, "responderam": 0})
        linha["enviadas"] += 1
        if _rank(reached.get(row["id"], "")) >= limite:
            linha["responderam"] += 1
    linhas = sorted(por_fonte.values(), key=lambda item: item["enviadas"], reverse=True)
    for linha in linhas:
        linha["taxa"] = (round(100 * linha["responderam"] / linha["enviadas"])
                         if linha["enviadas"] >= MINIMO_PARA_PERCENTUAL else None)
    return linhas


def salary_snapshot() -> list[dict[str, Any]]:
    """Faixa salarial mediana das vagas coletadas, por moeda.

    Só entram vagas cuja faixa o anúncio publicou e cuja moeda o app reconheceu —
    o Farol não converte câmbio nem chuta valor ausente.
    """
    linhas = []
    for row in db.query(
        """SELECT salary_currency AS moeda, COUNT(*) AS n,
                  AVG(salary_min) AS media_min, AVG(salary_max) AS media_max
           FROM jobs
           WHERE salary_currency <> '' AND salary_max IS NOT NULL AND state = 'novo'
           GROUP BY salary_currency ORDER BY n DESC"""
    ):
        linhas.append({
            "moeda": row["moeda"],
            "vagas": row["n"],
            "min": round(row["media_min"] or 0),
            "max": round(row["media_max"] or 0),
        })
    return linhas


def summary() -> dict[str, Any]:
    """Tudo que a tela de métricas precisa, numa passada só."""
    reached = stage_reached()
    total = len(reached)
    responderam = sum(1 for status in reached.values() if _rank(status) >= _rank(RESPONDEU))
    enviadas = sum(1 for status in reached.values() if _rank(status) >= _rank("candidatado"))
    return {
        "total": total,
        "enviadas": enviadas,
        "responderam": responderam,
        "taxa_resposta": round(100 * responderam / enviadas) if enviadas else None,
        "amostra_suficiente": enviadas >= MINIMO_PARA_PERCENTUAL,
        "funnel": funnel(reached),
        "duracoes": stage_durations(),
        "semanas": weekly(),
        "paradas": stalled(),
        "fit": fit_by_outcome(),
        "fontes": by_source(),
        "salarios": salary_snapshot(),
    }
