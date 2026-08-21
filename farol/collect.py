"""Ingestão: busca nas fontes ativas, deduplica, grava e pontua.

A coleta acontece uma vez quando você abre o aplicativo e só isso. Entre uma
abertura e outra vale a janela de descanso (Ajustes → intervalo mínimo): abrir o
app cinco vezes em dez minutos não vira cinco rodadas de requisição nos portais.
Quem quiser forçar usa o botão "Atualizar vagas" dentro do app.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from . import db, scoring, skills, sources

# pausa entre requisições — portal nenhum gosta de rajada, e rajada é o que
# costuma disparar CAPTCHA e bloqueio por IP. FAROL_REQUEST_DELAY=0 desliga
# (é o que os testes fazem, já que lá não sai requisição de verdade).
REQUEST_DELAY_SECONDS = float(os.environ.get("FAROL_REQUEST_DELAY", "1.5"))

# quantos portais falam com a rede ao mesmo tempo. São servidores diferentes, e o
# gargalo aqui é espera de rede, não CPU.
MAX_PARALLEL_SOURCES = int(os.environ.get("FAROL_PARALLEL_SOURCES", "5"))

# Depois de quantos dias sem reaparecer numa coleta a vaga é dada como encerrada.
# Portal nenhum avisa que tirou o anúncio do ar; o sumiço é o único sinal, e sem
# uma janela a base só cresce — com anúncio morto sujando lista e roadmap.
STALE_AFTER_DAYS = int(os.environ.get("FAROL_STALE_DAYS", "21"))


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
    # as skills do anúncio saem de graça daqui: score_job já as extraiu para
    # comparar com o perfil. Gravadas na coluna, o roadmap não precisa reprocessar
    # a descrição de centenas de vagas para montar a tela.
    job_skills = list(result["matched"]) + list(result["missing"])
    payload = (
        item["title"], item["company"], item["url"], item["apply_url"], item["location"],
        item["remote"], scoring.work_mode(item), scoring.region(item), item["salary"],
        salary_min, salary_max, currency, db.dumps(item["tags"]), db.dumps(job_skills),
        item["description"], item["published_at"], result["score"], db.dumps(result), fp,
    )
    if existing is None:
        conn.execute(
            """INSERT INTO jobs (title, company, url, apply_url, location, remote, work_mode,
                                 region, salary, salary_min, salary_max, salary_currency, tags,
                                 skills, description, published_at, score, score_data, fingerprint,
                                 source, source_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (*payload, item["source"], item["source_id"]),
        )
    else:
        conn.execute(
            """UPDATE jobs SET title=?, company=?, url=?, apply_url=?, location=?, remote=?,
                               work_mode=?, region=?, salary=?, salary_min=?, salary_max=?,
                               salary_currency=?, tags=?, skills=?, description=?, published_at=?,
                               score=?, score_data=?, fingerprint=?, last_seen_at=datetime('now')
               WHERE id=?""",
            (*payload, existing["id"]),
        )
    return verdict


def highlights(since: str, min_score: int, limit: int = 5) -> list[dict[str, Any]]:
    """Vagas vistas pela primeira vez a partir de `since` com fit >= min_score."""
    return [
        dict(r)
        for r in db.query(
            """SELECT title, company, score FROM jobs
               WHERE first_seen_at >= ? AND score >= ? AND state = 'novo'
               ORDER BY score DESC LIMIT ?""",
            (since, min_score, limit),
        )
    ]


def notify(jobs: list[dict[str, Any]]) -> bool:
    """Avisa pelo notificador do desktop. Devolve se a notificação saiu.

    Sem `notify-send` instalado (ou fora de uma sessão gráfica) o app segue igual:
    a coleta não pode falhar por causa de um aviso.
    """
    if not jobs:
        return False
    top = jobs[0]
    corpo = "\n".join(f"{j['score']} · {j['title']} — {j['company'] or 'empresa não informada'}" for j in jobs)
    titulo = (
        f"Farol: {len(jobs)} vaga nova com bom fit" if len(jobs) == 1
        else f"Farol: {len(jobs)} vagas novas com bom fit"
    )
    try:
        subprocess.run(
            ["notify-send", "--app-name=Farol", "--icon=farol",
             f"--urgency={'normal' if top['score'] < 85 else 'critical'}", titulo, corpo],
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False
    return True


def _fetch_all(source: dict[str, Any], searches: list[str]) -> tuple[list[dict[str, Any]], str]:
    """Busca uma fonte para cada termo. Devolve (itens, erro).

    A pausa entre requisições vale **dentro** da fonte: é o mesmo servidor sendo
    consultado de novo. Fonte que já é a própria seleção — um feed RSS, um mural
    da comunidade — não recebe termo de busca e é consultada uma vez só, e não
    uma vez por termo.
    """
    queries = [""] if sources.fetches_once(source) else searches
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    with sources.client() as http:
        for index, query in enumerate(queries):
            if index:
                time.sleep(REQUEST_DELAY_SECONDS)
            try:
                items.extend(sources.fetch_source(source, query, http))
            except Exception as exc:  # noqa: BLE001 — o erro vira diagnóstico na tela
                errors.append(f"{type(exc).__name__}: {exc}")
    return items, "; ".join(dict.fromkeys(errors))[:400]


def run(source_ids: list[str] | None = None) -> dict[str, Any]:
    """Atualiza a base de vagas. Devolve um relatório por fonte.

    Portais diferentes são consultados em paralelo — são servidores distintos, e
    esperar o Remotive para só então falar com o RemoteOK não protege ninguém. A
    cortesia que importa (a pausa entre duas requisições ao **mesmo** portal)
    continua valendo dentro de cada fonte.
    """
    profile = db.get_profile()
    settings = db.get_settings()
    started = _utcnow().isoformat(sep=" ", timespec="seconds")
    searches = [
        row["keywords"].strip()
        for row in db.query("SELECT keywords FROM searches WHERE enabled = 1")
        if row["keywords"].strip()
    ] or [""]

    rows = db.query("SELECT * FROM sources WHERE enabled = 1 ORDER BY id")
    active = [dict(r) for r in rows if not source_ids or r["id"] in source_ids]

    harvest: dict[str, tuple[list[dict[str, Any]], str]] = {}
    if active:
        with ThreadPoolExecutor(max_workers=min(len(active), MAX_PARALLEL_SOURCES)) as pool:
            futures = {pool.submit(_fetch_all, s, searches): s["id"] for s in active}
            for future in as_completed(futures):
                sid = futures[future]
                try:
                    harvest[sid] = future.result()
                except Exception as exc:  # noqa: BLE001 — nunca derruba a rodada inteira
                    harvest[sid] = ([], f"{type(exc).__name__}: {exc}"[:400])

    # a gravação é sequencial de propósito: uma transação, uma thread, sem disputa
    # de escrita no SQLite
    report: list[dict[str, Any]] = []
    total_new = 0
    conn = db.connect()
    for source in active:
        items, error = harvest.get(source["id"], ([], "fonte não executada"))
        new = 0
        with conn:
            for item in items:
                if _upsert(conn, item, profile, settings) == "nova":
                    new += 1
        status = "erro" if error and not items else "ok"
        with conn:
            conn.execute(
                """UPDATE sources SET last_run_at = datetime('now'), last_status = ?,
                                      last_count = ?, last_error = ? WHERE id = ?""",
                (status, len(items), error, source["id"]),
            )
        total_new += new
        report.append(
            {
                "id": source["id"],
                "label": source["label"],
                "found": len(items),
                "new": new,
                "status": status,
                "error": error,
            }
        )

    expiradas = expire(conn) if any(r["found"] for r in report) else 0

    destaques: list[dict[str, Any]] = []
    if total_new and settings.get("notify_new_jobs") == "1":
        try:
            limite = int(settings.get("notify_min_score") or 70)
        except ValueError:
            limite = 70
        destaques = highlights(started, limite)
        notify(destaques)
    return {"sources": report, "new": total_new, "highlights": destaques,
            "expired": expiradas}


def expire(conn=None) -> int:
    """Marca como expirada a vaga que parou de aparecer nas coletas.

    Só roda depois de uma rodada que trouxe alguma coisa: se todas as fontes
    falharam, o sumiço é do coletor, não do anúncio, e expirar a base inteira
    por causa de uma queda de rede seria o pior desfecho possível.

    Nada é apagado — a vaga sai da lista e do roadmap, mas continua no banco,
    porque pode estar ligada a uma candidatura em andamento.
    """
    conn = conn or db.connect()
    corte = (_utcnow() - timedelta(days=STALE_AFTER_DAYS)).isoformat(sep=" ", timespec="seconds")
    with conn:
        cursor = conn.execute(
            "UPDATE jobs SET state = 'expirada' WHERE state = 'novo' AND last_seen_at < ?",
            (corte,),
        )
    return cursor.rowcount or 0


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
    """Recalcula o fit de todas as vagas (após mudar perfil ou preferências).

    Uma leitura, um `executemany`, uma transação: com alguns milhares de vagas na
    base a versão anterior fazia um UPDATE por linha dentro do laço.
    """
    profile = db.get_profile()
    settings = db.get_settings()
    conn = db.connect()
    with conn:
        rows = conn.execute(
            """SELECT id, title, company, description, tags, location, salary, remote,
                      published_at FROM jobs"""
        ).fetchall()
        updates = []
        for row in rows:
            job = dict(row)
            job["tags"] = db.loads(job.get("tags"), [])
            result = scoring.score_job(job, profile, settings)
            low, high, currency = scoring.salary_range(job.get("salary")) or (None, None, "")
            updates.append(
                (result["score"], db.dumps(result), scoring.work_mode(job), scoring.region(job),
                 low, high, currency,
                 db.dumps(list(result["matched"]) + list(result["missing"])), job["id"])
            )
        conn.executemany(
            """UPDATE jobs SET score = ?, score_data = ?, work_mode = ?, region = ?,
                               salary_min = ?, salary_max = ?, salary_currency = ?, skills = ?
               WHERE id = ?""",
            updates,
        )
    return len(updates)
