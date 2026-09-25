"""Alertas de vaga nova (issue #12).

Um alerta é uma busca guardada — termos, nível, região, modelo de trabalho e fit
mínimo. Depois de cada coleta, as vagas que acabaram de entrar são comparadas com
os alertas ativos e o que casa vira um resumo dentro do app; o aviso do desktop é
um extra por cima disso, não o mecanismo.

Três coisas que o módulo garante, e que são o que o issue pedia:

**Deduplicação.** A chave primária de `alert_hits` é o par (alerta, vaga). A mesma
vaga reaparece em toda coleta enquanto o anúncio estiver no ar; sem a chave, ela
avisaria de novo toda vez, e o alerta viraria ruído em dois dias.

**Nenhuma requisição própria.** Não existe coleta de alerta: o casamento roda
sobre o que a coleta normal acabou de gravar. O intervalo de descanso entre
coletas continua sendo o único regulador de tráfego.

**Opt-out que desliga mesmo.** `enabled = 0` para de casar; `notify = 0` mantém o
resumo na tela e cala só o desktop. Apagar o alerta leva junto o histórico dele
(`ON DELETE CASCADE`), porque guardar casamento de alerta que não existe mais é
só lixo esperando para confundir.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from . import db, scoring
from .sources.query import matches as termos_casam

# teto do resumo mostrado na tela e do aviso do desktop: uma coleta que traga
# quarenta vagas casando não deve empurrar quarenta linhas para ninguém
DIGEST_LIMIT = 30
NOTIFY_LIMIT = 5


def _row(row: Any) -> dict[str, Any]:
    return dict(row)


def all_alerts(only_enabled: bool = False) -> list[dict[str, Any]]:
    clause = " WHERE enabled = 1" if only_enabled else ""
    return [_row(r) for r in db.query(f"SELECT * FROM alerts{clause} ORDER BY id")]


def get(alert_id: int) -> dict[str, Any] | None:
    row = db.one("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    return _row(row) if row else None


def normalize(form: dict[str, Any]) -> dict[str, Any]:
    """Traduz o formulário para os campos do alerta, recusando valor fora de lista."""
    # `or 70` não serve aqui: zero é falso em Python e é um fit mínimo legítimo —
    # é justamente como se escreve "me avise de qualquer vaga que case nos termos"
    bruto = str(form.get("min_score") if form.get("min_score") is not None else 70).strip()
    try:
        min_score = int(bruto)
    except ValueError:
        min_score = 70
    nivel = str(form.get("level") or "")
    regiao = str(form.get("region") or "")
    modo = str(form.get("work_mode") or "")
    keywords = str(form.get("keywords") or "").strip()
    label = str(form.get("label") or "").strip() or keywords or "Alerta sem nome"
    return {
        "label": label[:60],
        "keywords": keywords[:120],
        "level": nivel if nivel in scoring.LEVEL_TERMS else "",
        "region": regiao if regiao in scoring.REGIONS else "",
        "work_mode": modo if modo in scoring.WORK_MODES else "",
        "min_score": max(0, min(100, min_score)),
        "notify": 1 if form.get("notify") else 0,
    }


FIELDS = ("label", "keywords", "level", "region", "work_mode", "min_score", "notify")


def create(form: dict[str, Any]) -> int:
    campos = normalize(form)
    return db.execute(
        f"INSERT INTO alerts ({', '.join(FIELDS)}) VALUES ({', '.join('?' for _ in FIELDS)})",
        [campos[f] for f in FIELDS],
    )


def update(alert_id: int, form: dict[str, Any]) -> None:
    campos = normalize(form)
    db.execute(
        f"UPDATE alerts SET {', '.join(f'{f} = ?' for f in FIELDS)} WHERE id = ?",
        [*(campos[f] for f in FIELDS), alert_id],
    )


def toggle(alert_id: int) -> None:
    db.execute("UPDATE alerts SET enabled = 1 - enabled WHERE id = ?", (alert_id,))


def delete(alert_id: int) -> None:
    db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))


# ------------------------------------------------------------------ casamento


def matches(alert: dict[str, Any], job: dict[str, Any]) -> bool:
    """A vaga atende a este alerta?

    Vale sobre a linha da vaga já lida do banco — o mesmo dicionário que a tela
    usa. Nada aqui consulta rede nem reabre o anúncio.
    """
    if (job.get("score") or 0) < (alert.get("min_score") or 0):
        return False
    if job.get("state") != "novo":
        return False
    if alert.get("region") and job.get("region") != alert["region"]:
        return False
    if alert.get("work_mode") and job.get("work_mode") != alert["work_mode"]:
        return False
    if not scoring.level_matches(job, alert.get("level") or ""):
        return False
    return termos_casam(
        alert.get("keywords") or "",
        job.get("title"), job.get("company"), job.get("description"),
    )


_MATCH_COLUMNS = "id, title, company, description, score, state, region, work_mode"

# Vagas lidas por vez. Duas razões, e as duas doem em base grande: o `IN (...)`
# do SQLite tem teto de parâmetros por consulta, e a descrição chega a 20 KB por
# anúncio — carregar milhares de uma vez seria dezenas de megabytes na memória
# para comparar meia dúzia de termos.
CHUNK = 200


def _blocos(job_ids: list[int] | None) -> Iterator[list[dict[str, Any]]]:
    """Vagas ativas em blocos de `CHUNK`, da rodada ou da base inteira."""
    if job_ids is None:
        offset = 0
        while True:
            rows = db.query(
                f"""SELECT {_MATCH_COLUMNS} FROM jobs WHERE state = 'novo'
                    ORDER BY id LIMIT ? OFFSET ?""",
                (CHUNK, offset),
            )
            if not rows:
                return
            yield [_row(r) for r in rows]
            offset += CHUNK
    for inicio in range(0, len(job_ids), CHUNK):
        bloco = job_ids[inicio:inicio + CHUNK]
        marcas = ",".join("?" for _ in bloco)
        yield [
            _row(r)
            for r in db.query(
                f"SELECT {_MATCH_COLUMNS} FROM jobs WHERE state = 'novo' AND id IN ({marcas})",
                bloco,
            )
        ]


def evaluate(job_ids: list[int] | None = None, *, seen: bool = False) -> list[dict[str, Any]]:
    """Casa vagas com os alertas ativos e grava o que é inédito.

    `job_ids` limita a checagem às vagas de uma rodada; sem ele, varre a base
    ativa inteira — é o que acontece quando um alerta acaba de ser criado.
    `seen=True` grava o casamento já marcado como lido: serve justamente para o
    alerta recém-criado não disparar um aviso com meses de acervo.

    Devolve só o que foi gravado agora, na ordem do fit.
    """
    ativos = all_alerts(only_enabled=True)
    if not ativos or job_ids == []:
        return []

    novos: list[dict[str, Any]] = []
    conn = db.connect()
    for vagas in _blocos(job_ids):
        with conn:
            for alerta in ativos:
                for vaga in vagas:
                    if not matches(alerta, vaga):
                        continue
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO alert_hits (alert_id, job_id, seen) VALUES (?, ?, ?)",
                        (alerta["id"], vaga["id"], 1 if seen else 0),
                    )
                    if not cursor.rowcount:
                        continue  # já casava antes: a chave composta é a deduplicação
                    novos.append(
                        {
                            "alert_id": alerta["id"],
                            "alert": alerta["label"],
                            "notify": bool(alerta["notify"]),
                            "job_id": vaga["id"],
                            "title": vaga["title"],
                            "company": vaga["company"],
                            "score": vaga["score"],
                        }
                    )
    if novos:
        with conn:
            conn.executemany(
                "UPDATE alerts SET last_hit_at = datetime('now') WHERE id = ?",
                [(identificador,) for identificador in {n["alert_id"] for n in novos}],
            )
    novos.sort(key=lambda n: n["score"], reverse=True)
    return novos


def notify(hits: list[dict[str, Any]]) -> bool:
    """Manda ao desktop só o que veio de alerta com aviso ligado.

    Reaproveita `collect.notify`, que já sabe conviver com máquina sem
    `notify-send`: o aviso é enfeite, e falhar nele não pode estragar a coleta.
    """
    from . import collect  # local: `collect` chama este módulo no fim da rodada

    avisaveis = [h for h in hits if h["notify"]][:NOTIFY_LIMIT]
    if not avisaveis:
        return False
    return collect.notify(
        [{"title": h["title"], "company": h["company"], "score": h["score"]} for h in avisaveis]
    )


def run(job_ids: list[int] | None = None) -> dict[str, Any]:
    """O que a coleta chama no fim da rodada. Nunca levanta exceção para fora."""
    try:
        novos = evaluate(job_ids)
    except Exception as exc:  # noqa: BLE001 — alerta quebrado não pode derrubar a coleta
        return {"hits": [], "notified": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"hits": novos, "notified": notify(novos), "error": ""}


# ------------------------------------------------------------------ resumo


def digest(limit: int = DIGEST_LIMIT) -> list[dict[str, Any]]:
    """Casamentos ainda não lidos, do mais aderente para o menos."""
    return [
        _row(r)
        for r in db.query(
            """SELECT h.alert_id, h.job_id, h.created_at, a.label AS alert,
                      j.title, j.company, j.score, j.source
               FROM alert_hits h
               JOIN alerts a ON a.id = h.alert_id
               JOIN jobs j ON j.id = h.job_id
               WHERE h.seen = 0 AND j.state = 'novo'
               ORDER BY j.score DESC, h.created_at DESC
               LIMIT ?""",
            (limit,),
        )
    ]


def pending_count() -> int:
    row = db.one(
        """SELECT COUNT(*) AS n FROM alert_hits h JOIN jobs j ON j.id = h.job_id
           WHERE h.seen = 0 AND j.state = 'novo'"""
    )
    return row["n"] if row else 0


def mark_seen(alert_id: int | None = None) -> int:
    """Marca o resumo como lido. Devolve quantos casamentos saíram da fila.

    Vai pela conexão direto porque `db.execute` devolve `lastrowid or rowcount`,
    e depois de um INSERT anterior na mesma conexão o `lastrowid` não é zero —
    a contagem viria errada.
    """
    conn = db.connect()
    with conn:
        if alert_id is None:
            cursor = conn.execute("UPDATE alert_hits SET seen = 1 WHERE seen = 0")
        else:
            cursor = conn.execute(
                "UPDATE alert_hits SET seen = 1 WHERE seen = 0 AND alert_id = ?", (alert_id,)
            )
    return cursor.rowcount or 0
