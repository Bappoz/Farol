"""Ingestão: busca nas fontes ativas, deduplica, grava e pontua.

A coleta acontece uma vez quando você abre o aplicativo e só isso. Entre uma
abertura e outra vale a janela de descanso (Ajustes → intervalo mínimo): abrir o
app cinco vezes em dez minutos não vira cinco rodadas de requisição nos portais.
Quem quiser forçar usa o botão "Atualizar vagas" dentro do app.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from . import db, scoring, skills, sources

# pausa entre requisições — portal nenhum gosta de rajada, e rajada é o que
# costuma disparar CAPTCHA e bloqueio por IP. FAROL_REQUEST_DELAY=0 desliga
# (é o que os testes fazem, já que lá não sai requisição de verdade).
REQUEST_DELAY_SECONDS = float(os.environ.get("FAROL_REQUEST_DELAY", "1.5"))


def fingerprint(title: str, company: str) -> str:
    raw = f"{skills.normalize(title)}|{skills.normalize(company)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _upsert(conn, item: dict[str, Any], profile: dict, settings: dict) -> str:
    """Grava a vaga. Devolve 'nova', 'atualizada' ou 'duplicada'."""
    fp = fingerprint(item["title"], item["company"])
    existing = conn.execute(
        "SELECT id, source, source_id FROM jobs WHERE source = ? AND source_id = ?",
        (item["source"], item["source_id"]),
    ).fetchone()

    verdict = "atualizada"
    if existing is None:
        twin = conn.execute(
            "SELECT id FROM jobs WHERE fingerprint = ?", (fp,)
        ).fetchone()
        if twin is not None:
            # mesma vaga em outro portal: mantém a primeira e só renova o "visto em"
            conn.execute(
                "UPDATE jobs SET last_seen_at = datetime('now') WHERE id = ?", (twin["id"],)
            )
            return "duplicada"
        verdict = "nova"

    result = scoring.score_job(item, profile, settings)
    salary_min, salary_max, currency = scoring.salary_range(item["salary"]) or (None, None, "")
    payload = (
        item["title"], item["company"], item["url"], item["apply_url"], item["location"],
        item["remote"], scoring.work_mode(item), scoring.region(item), item["salary"],
        salary_min, salary_max, currency, db.dumps(item["tags"]), item["description"],
        item["published_at"], result["score"], db.dumps(result), fp,
    )
    if existing is None:
        conn.execute(
            """INSERT INTO jobs (title, company, url, apply_url, location, remote, work_mode,
                                 region, salary, salary_min, salary_max, salary_currency, tags,
                                 description, published_at, score, score_data, fingerprint,
                                 source, source_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            payload + (item["source"], item["source_id"]),
        )
    else:
        conn.execute(
            """UPDATE jobs SET title=?, company=?, url=?, apply_url=?, location=?, remote=?,
                               work_mode=?, region=?, salary=?, salary_min=?, salary_max=?,
                               salary_currency=?, tags=?, description=?, published_at=?, score=?,
                               score_data=?, fingerprint=?, last_seen_at=datetime('now')
               WHERE id=?""",
            payload + (existing["id"],),
        )
    return verdict


def run(source_ids: list[str] | None = None) -> dict[str, Any]:
    """Atualiza a base de vagas. Devolve um relatório por fonte."""
    profile = db.get_profile()
    settings = db.get_settings()
    searches = [
        row["keywords"].strip()
        for row in db.query("SELECT keywords FROM searches WHERE enabled = 1")
        if row["keywords"].strip()
    ] or [""]

    rows = db.query("SELECT * FROM sources WHERE enabled = 1 ORDER BY id")
    active = [dict(r) for r in rows if not source_ids or r["id"] in source_ids]

    report: list[dict[str, Any]] = []
    total_new = 0
    first_request = True
    with sources.client() as http:
        for source in active:
            found = new = 0
            error = ""
            for query in searches:
                if not first_request:
                    time.sleep(REQUEST_DELAY_SECONDS)
                first_request = False
                try:
                    items = sources.fetch_source(source, query, http)
                except Exception as exc:  # noqa: BLE001 — o erro vira diagnóstico na tela
                    error = f"{type(exc).__name__}: {exc}"[:400]
                    continue
                found += len(items)
                with db.connect() as conn:
                    for item in items:
                        if _upsert(conn, item, profile, settings) == "nova":
                            new += 1
            status = "erro" if error and not found else "ok"
            db.execute(
                """UPDATE sources SET last_run_at = datetime('now'), last_status = ?,
                                      last_count = ?, last_error = ? WHERE id = ?""",
                (status, found, error, source["id"]),
            )
            total_new += new
            report.append(
                {
                    "id": source["id"],
                    "label": source["label"],
                    "found": found,
                    "new": new,
                    "status": status,
                    "error": error,
                }
            )
    return {"sources": report, "new": total_new}


# ------------------------------------------------------- coleta em segundo plano

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "report": None,
    "error": "",
    "skipped": "",
}


def _utcnow() -> datetime:
    """Agora em UTC e sem fuso, no mesmo formato que o SQLite grava."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def last_run_at() -> datetime | None:
    """Momento da última coleta bem-sucedida de qualquer fonte."""
    row = db.one("SELECT MAX(last_run_at) AS at FROM sources WHERE last_status IS NOT NULL")
    if not row or not row["at"]:
        return None
    try:
        return datetime.fromisoformat(row["at"])
    except ValueError:
        return None


def cooldown_minutes() -> int:
    try:
        return max(0, int(db.get_settings().get("refresh_cooldown_min") or 0))
    except ValueError:
        return 45


def minutes_until_next() -> int:
    """Quantos minutos faltam para a próxima coleta automática ser permitida."""
    previous = last_run_at()
    if previous is None:
        return 0
    elapsed = _utcnow() - previous
    remaining = timedelta(minutes=cooldown_minutes()) - elapsed
    return max(0, int(remaining.total_seconds() // 60) + (1 if remaining.total_seconds() % 60 else 0))


def status() -> dict[str, Any]:
    previous = last_run_at()
    snapshot = dict(_state)
    snapshot["last_run_at"] = previous.isoformat(sep=" ", timespec="minutes") if previous else None
    snapshot["cooldown_min"] = cooldown_minutes()
    snapshot["next_in_min"] = minutes_until_next()
    return snapshot


def _worker(source_ids: list[str] | None) -> None:
    try:
        report = run(source_ids)
        _state["report"] = report
        _state["error"] = ""
    except Exception as exc:  # noqa: BLE001 — vira aviso na tela, não derruba o app
        _state["report"] = None
        _state["error"] = f"{type(exc).__name__}: {exc}"[:400]
    finally:
        _state["running"] = False
        _state["finished_at"] = _utcnow().isoformat(timespec="seconds")


def start(force: bool = False, source_ids: list[str] | None = None) -> dict[str, Any]:
    """Dispara a coleta em uma thread. Devolve o que aconteceu com o pedido.

    'iniciada'  — thread no ar
    'em-curso'  — já havia uma coleta rodando
    'descanso'  — dentro da janela mínima entre coletas (só `force` fura)
    """
    with _lock:
        if _state["running"]:
            return {"verdict": "em-curso", **status()}
        if not force:
            remaining = minutes_until_next()
            if remaining:
                _state["skipped"] = f"última coleta há pouco; próxima em {remaining} min"
                return {"verdict": "descanso", **status()}
        _state.update(
            running=True,
            started_at=_utcnow().isoformat(timespec="seconds"),
            finished_at=None,
            report=None,
            error="",
            skipped="",
        )
    threading.Thread(target=_worker, args=(source_ids,), daemon=True, name="farol-coleta").start()
    return {"verdict": "iniciada", **status()}


def rescore() -> int:
    """Recalcula o fit de todas as vagas (após mudar perfil ou preferências)."""
    profile = db.get_profile()
    settings = db.get_settings()
    updated = 0
    with db.connect() as conn:
        for row in conn.execute("SELECT * FROM jobs").fetchall():
            job = dict(row)
            job["tags"] = db.loads(job.get("tags"), [])
            result = scoring.score_job(job, profile, settings)
            salary_min, salary_max, currency = scoring.salary_range(job.get("salary")) or (None, None, "")
            conn.execute(
                """UPDATE jobs SET score = ?, score_data = ?, work_mode = ?, region = ?,
                                   salary_min = ?, salary_max = ?, salary_currency = ?
                   WHERE id = ?""",
                (result["score"], db.dumps(result), scoring.work_mode(job), scoring.region(job),
                 salary_min, salary_max, currency, job["id"]),
            )
            updated += 1
    return updated
