"""Rotas e renderização. Tudo server-side: HTML pronto, JS só onde ajuda."""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from . import __version__, ai, collect, db, markup, pdfs, roadmap, scoring, skills
from . import resume as resume_mod

PKG_DIR = Path(__file__).resolve().parent

# vagas por página em /vagas — a lista antes cortava em 200 sem dizer que havia mais
PAGE_SIZE = 50

# colunas da listagem: `description` chega a 20 KB por vaga e não aparece na lista.
# Trazer 50 delas era mais de um megabyte lido do disco a cada página.
JOB_LIST_COLUMNS = """id, source, title, company, url, apply_url, location, remote, work_mode,
                      region, salary, tags, published_at, first_seen_at, last_seen_at, score,
                      score_data, state"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.bootstrap()
    yield
    db.close()


app = FastAPI(title="Farol", version=__version__, docs_url=None, redoc_url=None, lifespan=lifespan)
# HTML server-side comprime muito bem; abaixo de 1 KB o ganho não paga o trabalho
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", StaticFiles(directory=PKG_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(PKG_DIR / "templates"))
templates.env.filters["skill"] = skills.display
# markup.render escapa o texto antes de marcar, então o resultado entra sem autoescape
templates.env.filters["descricao"] = lambda text: Markup(markup.render(text))


# ------------------------------------------------------------------ helpers


def go(path: str, msg: str = "", tone: str = "ok") -> RedirectResponse:
    if msg:
        path += ("&" if "?" in path else "?") + urlencode({"msg": msg, "tone": tone})
    return RedirectResponse(path, status_code=303)


def render(request: Request, template: str, **context: Any) -> HTMLResponse:
    settings = db.get_settings()
    profile = context.pop("profile", None) or db.get_profile()
    base = {
        "request": request,
        "settings": settings,
        "profile": profile,
        "statuses": db.STATUSES,
        "status_labels": db.STATUS_LABELS,
        "areas": skills.AREAS,
        "seniorities": skills.SENIORITIES,
        "work_mode_labels": scoring.WORK_MODE_LABELS,
        "region_labels": scoring.REGION_LABELS,
        "currency_labels": scoring.SALARY_CURRENCY_LABELS,
        "msg": request.query_params.get("msg", ""),
        "tone": request.query_params.get("tone", "ok"),
        "nav": context.pop("nav", ""),
        "ai_ready": bool((settings.get("anthropic_api_key") or "").strip()),
        "collect_state": collect.status(),
    }
    base.update(context)
    return templates.TemplateResponse(request, template, base)


def job_dict(row: Any) -> dict[str, Any]:
    job = dict(row)
    job["tags"] = db.loads(job.get("tags"), [])
    job["score_data"] = db.loads(job.get("score_data"), {}) or {}
    job["age"] = scoring.days_old(job.get("published_at"))
    job["label"] = scoring.label(job.get("score", 0))
    return job


def resume_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["data"] = db.loads(item.get("data"), {}) or {}
    return item


def _bullets(raw: str) -> list[str]:
    return [line.strip("•- ").strip() for line in (raw or "").splitlines() if line.strip()]


def _int(value: Any, default: int = 0) -> int:
    """Inteiro vindo de formulário ou query string, sem derrubar a página.

    Todo campo numérico que chega do navegador passa por aqui: `?pagina=abc` e
    `id=` são entrada possível (link colado, extensão, formulário editado) e não
    podem virar erro 500.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


@app.get("/saude")
def health() -> JSONResponse:
    return JSONResponse({"ok": True, "app": "farol", "db": str(db.db_path())})


# ------------------------------------------------------------------ painel


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    profile = db.get_profile()
    settings = db.get_settings()

    counts = dict.fromkeys(db.STATUSES, 0)
    for row in db.query("SELECT status, COUNT(*) AS n FROM applications GROUP BY status"):
        counts[row["status"]] = row["n"]

    week_ago = (date.today() - timedelta(days=7)).isoformat()
    applied_week = db.one(
        "SELECT COUNT(*) AS n FROM applications WHERE applied_at >= ?", (week_ago,)
    )["n"]

    upcoming = [
        dict(r)
        for r in db.query(
            """SELECT id, title, company, status, next_action, next_action_at
               FROM applications
               WHERE next_action <> '' AND next_action_at IS NOT NULL
               ORDER BY next_action_at LIMIT 8"""
        )
    ]
    today = date.today().isoformat()
    for item in upcoming:
        item["late"] = (item["next_action_at"] or "") < today

    top_jobs = [
        job_dict(r)
        for r in db.query(
            f"""SELECT {JOB_LIST_COLUMNS} FROM jobs
                WHERE state = 'novo'
                  AND id NOT IN (SELECT job_id FROM applications WHERE job_id IS NOT NULL)
                ORDER BY score DESC, last_seen_at DESC LIMIT 6"""
        )
    ]

    total_jobs = db.one("SELECT COUNT(*) AS n FROM jobs")["n"]
    demand = roadmap.demand().most_common(8)
    owned = set(profile.get("skills") or [])
    demand_rows = [
        {"skill": name, "count": count, "owned": name in owned} for name, count in demand
    ]
    max_demand = max([d["count"] for d in demand_rows], default=1)

    last_run = db.one("SELECT MAX(last_run_at) AS at FROM sources")["at"]
    profile_complete = bool(profile.get("name")) and bool(profile.get("skills"))

    return render(
        request,
        "dashboard.html",
        nav="painel",
        profile=profile,
        counts=counts,
        total_applications=sum(counts.values()),
        applied_week=applied_week,
        weekly_goal=int(settings.get("weekly_goal") or 5),
        upcoming=upcoming,
        top_jobs=top_jobs,
        total_jobs=total_jobs,
        demand_rows=demand_rows,
        max_demand=max_demand,
        last_run=last_run,
        profile_complete=profile_complete,
    )


# ------------------------------------------------------------------ vagas


@app.get("/vagas", response_class=HTMLResponse)
def jobs_list(request: Request) -> HTMLResponse:
    params = request.query_params
    settings = db.get_settings()
    term = (params.get("q") or "").strip()
    source = params.get("fonte") or ""
    state = params.get("estado") or "novo"
    order = params.get("ordem") or "score"
    local = (params.get("local") or "").strip()
    modo = params.get("modo") or ""
    regiao = params.get("regiao") or ""
    moeda = params.get("moeda") or "USD"
    if moeda not in scoring.SALARY_CURRENCIES:
        moeda = "USD"
    min_score = max(0, min(100, _int(params.get("min"), _int(settings.get("min_score"), 0))))
    salario = max(0, _int(params.get("salario")))
    pagina = max(1, _int(params.get("pagina"), 1))

    where = ["score >= ?"]
    args: list[Any] = [min_score]
    if state in ("novo", "descartada"):
        where.append("state = ?")
        args.append(state)
    if source:
        where.append("source = ?")
        args.append(source)
    if term:
        where.append("(LOWER(title) LIKE ? OR LOWER(company) LIKE ? OR LOWER(description) LIKE ?)")
        needle = f"%{term.lower()}%"
        args += [needle, needle, needle]
    if local:
        # vale mesmo para vaga remota: location guarda a região aceita ("Brazil", "Worldwide"...)
        # comparação exata com um valor que já existe na base — o select não deixa digitar errado
        where.append("location = ?")
        args.append(local)
    if regiao in scoring.REGIONS:
        where.append("region = ?")
        args.append(regiao)
    if modo in scoring.WORK_MODES:
        where.append("work_mode = ?")
        args.append(modo)
    if salario:
        # compara com o topo da faixa: a vaga pode pagar até ali. Só entre vagas da
        # mesma moeda — o app não converte câmbio, então comparar EUR com USD mentiria.
        where.append("salary_max >= ? AND salary_currency = ?")
        args += [salario, moeda]

    order_sql = {
        "score": "score DESC, last_seen_at DESC",
        "recente": "COALESCE(published_at, first_seen_at) DESC",
        "empresa": "company COLLATE NOCASE, title COLLATE NOCASE",
    }.get(order, "score DESC")

    clause = " AND ".join(where)
    found = db.one(f"SELECT COUNT(*) AS n FROM jobs WHERE {clause}", args)["n"]
    pages = max(1, -(-found // PAGE_SIZE))  # divisão para cima
    pagina = min(pagina, pages)
    rows = db.query(
        f"SELECT {JOB_LIST_COLUMNS} FROM jobs WHERE {clause} ORDER BY {order_sql} LIMIT ? OFFSET ?",
        [*args, PAGE_SIZE, (pagina - 1) * PAGE_SIZE],
    )
    jobs = [job_dict(r) for r in rows]
    saved = {r["job_id"]: r["id"] for r in db.query("SELECT id, job_id FROM applications WHERE job_id IS NOT NULL")}
    for job in jobs:
        job["application_id"] = saved.get(job["id"])

    sources = [dict(r) for r in db.query("SELECT * FROM sources ORDER BY label")]
    locations = [
        dict(r)
        for r in db.query(
            """SELECT location, COUNT(*) AS n FROM jobs WHERE location <> ''
               GROUP BY location ORDER BY n DESC, location COLLATE NOCASE LIMIT 200"""
        )
    ]
    total = db.one("SELECT COUNT(*) AS n FROM jobs")["n"]
    filters = {
        "q": term, "fonte": source, "estado": state, "ordem": order, "min": min_score,
        "local": local, "regiao": regiao, "modo": modo, "salario": salario, "moeda": moeda,
    }
    back_qs = urlencode({k: v for k, v in filters.items() if v} | {"pagina": pagina})
    return render(
        request,
        "jobs.html",
        nav="vagas",
        jobs=jobs,
        sources=sources,
        locations=locations,
        total=total,
        found=found,
        pagina=pagina,
        pages=pages,
        page_qs=urlencode({k: v for k, v in filters.items() if v}),
        filters=filters,
        back_qs=back_qs,
    )


@app.post("/vagas/atualizar")
async def jobs_refresh(request: Request) -> RedirectResponse:
    """Coleta manual: sempre roda, mesmo dentro da janela de descanso."""
    form = await request.form()
    back = str(form.get("back") or "/vagas")
    result = collect.start(force=True)
    if result["verdict"] == "em-curso":
        return go(back, "Já tem uma coleta rodando agora.")
    return go(back, "Coletando vagas nos portais — a página atualiza sozinha ao terminar.")


@app.post("/coleta")
async def collect_start(request: Request) -> JSONResponse:
    """Disparo automático da abertura do app (o launcher chama esta rota).

    Respeita a janela de descanso: reabrir o app cinco vezes seguidas não vira
    cinco rodadas de requisição nos portais.
    """
    force = False
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            force = bool((await request.json()).get("forcar"))
        except Exception:  # noqa: BLE001 — corpo vazio é o caso normal do launcher
            force = False
    return JSONResponse(collect.start(force=force))


@app.get("/coleta/status")
def collect_status() -> JSONResponse:
    return JSONResponse(collect.status())


@app.get("/vagas/{job_id}", response_class=HTMLResponse)
def job_detail(request: Request, job_id: int) -> HTMLResponse:
    row = db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if row is None:
        return go("/vagas", "Vaga não encontrada.", "warn")  # type: ignore[return-value]
    job = job_dict(row)
    application = db.one("SELECT * FROM applications WHERE job_id = ?", (job_id,))
    resumes = [resume_dict(r) for r in db.query("SELECT * FROM resumes WHERE job_id = ?", (job_id,))]
    return render(
        request,
        "job_detail.html",
        nav="vagas",
        job=job,
        application=dict(application) if application else None,
        resumes=resumes,
        questions=resume_mod.interview_questions(job),
    )


@app.post("/vagas/{job_id}/salvar")
def job_save(job_id: int) -> RedirectResponse:
    row = db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if row is None:
        return go("/vagas", "Vaga não encontrada.", "warn")
    existing = db.one("SELECT id FROM applications WHERE job_id = ?", (job_id,))
    if existing:
        return go(f"/candidaturas/{existing['id']}", "Essa vaga já está no pipeline.")
    app_id = db.execute(
        """INSERT INTO applications (job_id, title, company, url, status, next_action)
           VALUES (?, ?, ?, ?, 'salva', 'Adaptar currículo e enviar')""",
        (job_id, row["title"], row["company"], row["apply_url"] or row["url"]),
    )
    db.execute(
        "INSERT INTO events (application_id, kind, note) VALUES (?, 'criada', ?)",
        (app_id, f"Salva a partir de {row['source']}"),
    )
    return go(f"/candidaturas/{app_id}", "Vaga adicionada ao pipeline.")


JOB_STATES = ("novo", "descartada")


@app.post("/vagas/{job_id}/estado")
async def job_state(request: Request, job_id: int) -> RedirectResponse:
    form = await request.form()
    state = str(form.get("state") or "novo")
    back = str(form.get("back") or "/vagas")
    if state not in JOB_STATES:
        # um valor fora da lista sumiria com a vaga: ela não aparece nem em
        # "ativas" nem em "descartadas"
        return go(back, "Estado de vaga desconhecido.", "warn")
    db.execute("UPDATE jobs SET state = ? WHERE id = ?", (state, job_id))
    return go(back, "Vaga descartada." if state == "descartada" else "Vaga restaurada.")


# ------------------------------------------------------------------ pipeline


@app.get("/pipeline", response_class=HTMLResponse)
def pipeline(request: Request) -> HTMLResponse:
    columns: dict[str, list[dict[str, Any]]] = {status: [] for status in db.STATUSES}
    today = date.today().isoformat()
    for row in db.query("SELECT * FROM applications ORDER BY position, updated_at DESC"):
        item = dict(row)
        item["late"] = bool(item["next_action_at"]) and item["next_action_at"] < today
        columns.setdefault(item["status"], []).append(item)
    return render(request, "pipeline.html", nav="pipeline", columns=columns)


@app.post("/candidaturas")
async def application_create(request: Request) -> RedirectResponse:
    form = await request.form()
    title = str(form.get("title") or "").strip()
    if not title:
        return go("/pipeline", "Informe ao menos o cargo.", "warn")
    app_id = db.execute(
        "INSERT INTO applications (title, company, url, status) VALUES (?, ?, ?, ?)",
        (title, str(form.get("company") or "").strip(), str(form.get("url") or "").strip(),
         str(form.get("status") or "salva")),
    )
    db.execute("INSERT INTO events (application_id, kind, note) VALUES (?, 'criada', 'Adicionada manualmente')", (app_id,))
    return go(f"/candidaturas/{app_id}", "Candidatura criada.")


@app.get("/candidaturas/{app_id}", response_class=HTMLResponse)
def application_detail(request: Request, app_id: int) -> HTMLResponse:
    row = db.one("SELECT * FROM applications WHERE id = ?", (app_id,))
    if row is None:
        return go("/pipeline", "Candidatura não encontrada.", "warn")  # type: ignore[return-value]
    application = dict(row)
    job = None
    if application["job_id"]:
        job_row = db.one("SELECT * FROM jobs WHERE id = ?", (application["job_id"],))
        job = job_dict(job_row) if job_row else None
    events = [dict(r) for r in db.query(
        "SELECT * FROM events WHERE application_id = ? ORDER BY created_at DESC, id DESC", (app_id,)
    )]
    resumes = [resume_dict(r) for r in db.query(
        "SELECT * FROM resumes WHERE application_id = ? OR (job_id IS NOT NULL AND job_id = ?)",
        (app_id, application["job_id"] or -1),
    )]
    return render(
        request,
        "application.html",
        nav="pipeline",
        application=application,
        job=job,
        events=events,
        resumes=resumes,
        questions=resume_mod.interview_questions(job),
    )


@app.post("/candidaturas/{app_id}")
async def application_update(request: Request, app_id: int) -> RedirectResponse:
    form = await request.form()
    status = str(form.get("status") or "salva")
    current = db.one("SELECT status, applied_at FROM applications WHERE id = ?", (app_id,))
    applied_at = current["applied_at"] if current else None
    if status != "salva" and not applied_at:
        applied_at = date.today().isoformat()
    db.execute(
        """UPDATE applications SET title=?, company=?, url=?, status=?, next_action=?,
                                   next_action_at=?, contact=?, notes=?, prep=?, applied_at=?,
                                   updated_at=datetime('now')
           WHERE id=?""",
        (
            str(form.get("title") or ""), str(form.get("company") or ""), str(form.get("url") or ""),
            status, str(form.get("next_action") or ""), str(form.get("next_action_at") or "") or None,
            str(form.get("contact") or ""), str(form.get("notes") or ""), str(form.get("prep") or ""),
            applied_at, app_id,
        ),
    )
    if current and current["status"] != status:
        db.execute(
            "INSERT INTO events (application_id, kind, note) VALUES (?, 'status', ?)",
            (app_id, f"{db.STATUS_LABELS.get(current['status'], current['status'])} → {db.STATUS_LABELS.get(status, status)}"),
        )
    return go(f"/candidaturas/{app_id}", "Candidatura atualizada.")


@app.post("/candidaturas/{app_id}/status")
async def application_status(request: Request, app_id: int) -> JSONResponse:
    try:
        payload = await request.json()
    except (ValueError, UnicodeDecodeError):
        return JSONResponse({"ok": False, "erro": "corpo JSON inválido"}, status_code=400)
    status = str((payload or {}).get("status") or "")
    if status not in db.STATUSES:
        return JSONResponse({"ok": False, "erro": "status inválido"}, status_code=400)
    current = db.one("SELECT status, applied_at FROM applications WHERE id = ?", (app_id,))
    if current is None:
        return JSONResponse({"ok": False, "erro": "não encontrada"}, status_code=404)
    applied_at = current["applied_at"]
    if status != "salva" and not applied_at:
        applied_at = date.today().isoformat()
    db.execute(
        "UPDATE applications SET status=?, applied_at=?, updated_at=datetime('now') WHERE id=?",
        (status, applied_at, app_id),
    )
    if current["status"] != status:
        db.execute(
            "INSERT INTO events (application_id, kind, note) VALUES (?, 'status', ?)",
            (app_id, f"{db.STATUS_LABELS.get(current['status'])} → {db.STATUS_LABELS.get(status)}"),
        )
    return JSONResponse({"ok": True})


@app.post("/candidaturas/{app_id}/eventos")
async def application_event(request: Request, app_id: int) -> RedirectResponse:
    form = await request.form()
    note = str(form.get("note") or "").strip()
    if note:
        db.execute(
            "INSERT INTO events (application_id, kind, note) VALUES (?, 'nota', ?)", (app_id, note)
        )
        db.execute("UPDATE applications SET updated_at = datetime('now') WHERE id = ?", (app_id,))
    return go(f"/candidaturas/{app_id}", "Anotação registrada.")


@app.post("/candidaturas/{app_id}/excluir")
def application_delete(app_id: int) -> RedirectResponse:
    db.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    return go("/pipeline", "Candidatura removida.")


# ------------------------------------------------------------------ currículos


@app.get("/curriculos", response_class=HTMLResponse)
def resumes_list(request: Request) -> HTMLResponse:
    rows = db.query(
        """SELECT r.*, j.title AS job_title, j.company AS job_company
           FROM resumes r LEFT JOIN jobs j ON j.id = r.job_id
           ORDER BY r.updated_at DESC"""
    )
    items = [resume_dict(r) for r in rows]
    jobs = [dict(r) for r in db.query(
        """SELECT j.id, j.title, j.company FROM jobs j
           JOIN applications a ON a.job_id = j.id ORDER BY a.updated_at DESC LIMIT 30"""
    )]
    return render(request, "resumes.html", nav="curriculos", resumes=items, jobs=jobs,
                  langs=resume_mod.LANGS, resume_templates=resume_mod.TEMPLATES)


@app.post("/curriculos")
async def resume_create(request: Request) -> RedirectResponse:
    form = await request.form()
    profile = db.get_profile()
    job_id = _int(form.get("job_id")) or None
    job = None
    if job_id:
        row = db.one("SELECT * FROM jobs WHERE id = ?", (job_id,))
        job = job_dict(row) if row else None
        if job is None:
            job_id = None
    lang = "en" if str(form.get("lang") or "pt") == "en" else "pt"
    template = resume_mod.template_or_default(str(form.get("template") or ""))
    data = resume_mod.build(profile, job)
    name = str(form.get("name") or "").strip()
    if not name:
        name = f"{job['title']} · {job['company']}" if job else "Currículo base"
        if lang == "en":
            name += " (EN)"
    letter = resume_mod.cover_letter(profile, job, lang)
    application = db.one("SELECT id FROM applications WHERE job_id = ?", (job_id,)) if job_id else None
    resume_id = db.execute(
        """INSERT INTO resumes (name, job_id, application_id, lang, template, data, letter)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name[:120], job_id, application["id"] if application else None,
         lang, template, db.dumps(data), letter),
    )
    msg = "Currículo criado a partir do seu perfil."
    if lang == "en":
        msg += " Os textos vieram do perfil em português — traduza aqui dentro; a tradução fica só neste currículo."
    return go(f"/curriculos/{resume_id}", msg)


@app.post("/curriculos/arquivo")
async def resume_upload(request: Request) -> RedirectResponse:
    """Sobe um PDF que você já tem e registra como currículo."""
    form = await request.form()
    upload = form.get("arquivo")
    if upload is None or not getattr(upload, "filename", ""):
        return go("/curriculos", "Escolha um arquivo PDF.", "warn")

    content = await upload.read()  # type: ignore[union-attr]
    if len(content) > pdfs.MAX_BYTES:
        return go("/curriculos", "Arquivo maior que 15 MB.", "warn")
    if not pdfs.is_pdf(content):
        return go("/curriculos", "Só aceito PDF por enquanto — esse arquivo não é um.", "warn")

    job_id = _int(form.get("job_id")) or None
    if job_id and db.one("SELECT id FROM jobs WHERE id = ?", (job_id,)) is None:
        job_id = None
    application = db.one("SELECT id FROM applications WHERE job_id = ?", (job_id,)) if job_id else None
    name = str(form.get("name") or "").strip() or Path(upload.filename).stem[:120]  # type: ignore[union-attr]
    lang = "en" if str(form.get("lang") or "pt") == "en" else "pt"

    resume_id = db.execute(
        """INSERT INTO resumes (name, job_id, application_id, lang, kind, file, data)
           VALUES (?, ?, ?, ?, 'arquivo', '', '{}')""",
        (name[:120], job_id, application["id"] if application else None, lang),
    )
    relative = pdfs.save(resume_id, name, content)
    db.execute("UPDATE resumes SET file = ? WHERE id = ?", (relative, resume_id))
    return go(f"/curriculos/{resume_id}", "PDF guardado como currículo.")


@app.get("/curriculos/{resume_id}/arquivo")
def resume_file(resume_id: int, baixar: int = 0) -> Any:
    row = db.one("SELECT name, file FROM resumes WHERE id = ?", (resume_id,))
    target = pdfs.path_for(row["file"]) if row else None
    if target is None:
        return go("/curriculos", "Arquivo não encontrado no disco.", "warn")
    return FileResponse(
        target,
        media_type="application/pdf",
        filename=f"{pdfs.slug(row['name'])}.pdf" if baixar else None,
    )


@app.get("/curriculos/{resume_id}", response_class=HTMLResponse)
def resume_detail(request: Request, resume_id: int) -> HTMLResponse:
    row = db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,))
    if row is None:
        return go("/curriculos", "Currículo não encontrado.", "warn")  # type: ignore[return-value]
    item = resume_dict(row)
    profile = db.get_profile()

    if item["kind"] == "arquivo":
        job = None
        if item["job_id"]:
            job_row = db.one("SELECT * FROM jobs WHERE id = ?", (item["job_id"],))
            job = job_dict(job_row) if job_row else None
        text, warning = pdfs.extract_text(item["file"])
        found = skills.extract(text)
        owned = set(profile.get("skills") or [])
        wanted = (job or {}).get("score_data", {}).get("matched", []) + \
                 (job or {}).get("score_data", {}).get("missing", [])
        return render(
            request,
            "resume_file.html",
            nav="curriculos",
            resume=item,
            job=job,
            profile=profile,
            langs=resume_mod.LANGS,
            resume_templates=resume_mod.TEMPLATES,
            text=text,
            warning=warning,
            found=found,
            novas=[s for s in found if s not in owned],
            cobertas=[s for s in wanted if s in found],
            faltantes=[s for s in wanted if s not in found],
        )
    job = None
    if item["job_id"]:
        job_row = db.one("SELECT * FROM jobs WHERE id = ?", (item["job_id"],))
        job = job_dict(job_row) if job_row else None
    return render(
        request,
        "resume_edit.html",
        nav="curriculos",
        resume=item,
        job=job,
        profile=profile,
        langs=resume_mod.LANGS,
        resume_templates=resume_mod.TEMPLATES,
        checklist=resume_mod.checklist(item["data"]),
    )


@app.post("/curriculos/{resume_id}")
async def resume_save(request: Request, resume_id: int) -> RedirectResponse:
    """Salva o currículo como documento próprio.

    O perfil é a semente, não o dono: o que você escreve aqui (inclusive uma
    tradução para o inglês) fica guardado neste currículo e não volta para o
    perfil nem se perde no próximo salvamento.
    """
    row = db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,))
    if row is None:
        return go("/curriculos", "Currículo não encontrado.", "warn")
    if row["kind"] == "arquivo":
        return go(f"/curriculos/{resume_id}", "Este currículo é um PDF seu: o app não edita o arquivo.", "warn")
    form = await request.form()
    data = resume_dict(row)["data"]
    lang = "en" if str(form.get("lang") or row["lang"]) == "en" else "pt"

    data["headline"] = str(form.get("headline") or "").strip()
    data["summary"] = str(form.get("summary") or "").strip()
    data["skills"] = [s for s in form.getlist("skills")]

    def items(prefix: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        """Lê os blocos numerados do formulário, mantendo só os marcados."""
        keep = set(form.getlist(f"{prefix}_incluir"))
        result = []
        for index in form.getlist(f"{prefix}_indice"):
            if index not in keep:
                continue
            entry: dict[str, Any] = {
                field: str(form.get(f"{prefix}_{field}_{index}") or "").strip()
                for field in fields
            }
            entry["bullets"] = _bullets(str(form.get(f"{prefix}_bullets_{index}") or ""))
            result.append(entry)
        return result

    data["experience"] = items("exp", ("role", "org", "period"))
    data["projects"] = items("proj", ("name", "url", "stack"))
    data["education"] = [
        {k: v for k, v in entry.items() if k != "bullets"}
        for entry in items("edu", ("course", "school", "period", "note"))
    ]
    data["languages"] = [
        {k: v for k, v in entry.items() if k != "bullets"}
        for entry in items("idi", ("name", "level"))
    ]

    template = resume_mod.template_or_default(str(form.get("template") or row["template"]))
    db.execute(
        """UPDATE resumes SET name=?, lang=?, template=?, data=?, letter=?,
                              updated_at=datetime('now') WHERE id=?""",
        (str(form.get("name") or row["name"])[:120], lang, template, db.dumps(data),
         str(form.get("letter") or ""), resume_id),
    )
    return go(f"/curriculos/{resume_id}", "Currículo salvo.")


@app.post("/curriculos/{resume_id}/reconstruir")
def resume_rebuild(resume_id: int) -> RedirectResponse:
    """Descarta as edições e monta de novo a partir do perfil."""
    row = db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,))
    if row is None:
        return go("/curriculos", "Currículo não encontrado.", "warn")
    if row["kind"] == "arquivo":
        return go(f"/curriculos/{resume_id}", "Nada a remontar: este currículo é um PDF seu.", "warn")
    profile = db.get_profile()
    job = None
    if row["job_id"]:
        job_row = db.one("SELECT * FROM jobs WHERE id = ?", (row["job_id"],))
        job = job_dict(job_row) if job_row else None
    db.execute(
        "UPDATE resumes SET data=?, letter=?, updated_at=datetime('now') WHERE id=?",
        (db.dumps(resume_mod.build(profile, job)),
         resume_mod.cover_letter(profile, job, row["lang"]), resume_id),
    )
    return go(f"/curriculos/{resume_id}", "Currículo remontado a partir do perfil.")


@app.get("/curriculos/{resume_id}/imprimir", response_class=HTMLResponse)
def resume_print(request: Request, resume_id: int) -> HTMLResponse:
    row = db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,))
    if row is None:
        return go("/curriculos", "Currículo não encontrado.", "warn")  # type: ignore[return-value]
    if row["kind"] == "arquivo":
        return go(f"/curriculos/{resume_id}", "Este currículo já é um PDF — use “Abrir”.", "warn")
    item = resume_dict(row)
    return templates.TemplateResponse(
        request,
        "resume_print.html",
        {
            "resume": item,
            "data": item["data"],
            "lang": item["lang"],
            "template": resume_mod.template_or_default(item.get("template")),
            "templates": resume_mod.TEMPLATES,
            "sections": resume_mod.sections(item["lang"]),
        },
    )


@app.post("/curriculos/{resume_id}/ia")
async def resume_ai(request: Request, resume_id: int) -> RedirectResponse:
    row = db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,))
    if row is None:
        return go("/curriculos", "Currículo não encontrado.", "warn")
    if row["kind"] == "arquivo":
        return go(f"/curriculos/{resume_id}", "A IA revisa currículos do editor, não PDF enviado.", "warn")
    form = await request.form()
    action = str(form.get("acao") or "")
    item = resume_dict(row)
    job = None
    if item["job_id"]:
        job_row = db.one("SELECT * FROM jobs WHERE id = ?", (item["job_id"],))
        job = job_dict(job_row) if job_row else None
    try:
        if action == "resumo":
            text = ai.tailor_summary(item["data"], job, item["lang"])
            item["data"]["summary"] = text
            db.execute("UPDATE resumes SET data=?, updated_at=datetime('now') WHERE id=?",
                       (db.dumps(item["data"]), resume_id))
            msg = "Resumo revisado pela IA."
        elif action == "marcadores":
            item["data"]["ai_bullets"] = ai.tailor_bullets(item["data"], job, item["lang"])
            db.execute("UPDATE resumes SET data=?, updated_at=datetime('now') WHERE id=?",
                       (db.dumps(item["data"]), resume_id))
            msg = "Sugestões de marcadores geradas."
        elif action == "carta":
            text = ai.polish_letter(item["letter"], item["data"], job, item["lang"])
            db.execute("UPDATE resumes SET letter=?, updated_at=datetime('now') WHERE id=?",
                       (text, resume_id))
            msg = "Carta revisada pela IA."
        else:
            msg = "Ação desconhecida."
    except Exception as exc:  # noqa: BLE001
        return go(f"/curriculos/{resume_id}", f"IA indisponível: {exc}", "warn")
    return go(f"/curriculos/{resume_id}", msg)


@app.post("/curriculos/{resume_id}/excluir")
def resume_delete(resume_id: int) -> RedirectResponse:
    row = db.one("SELECT file FROM resumes WHERE id = ?", (resume_id,))
    if row and row["file"]:
        pdfs.remove(row["file"])
    db.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
    return go("/curriculos", "Currículo removido.")


@app.post("/curriculos/{resume_id}/skills")
async def resume_import_skills(request: Request, resume_id: int) -> RedirectResponse:
    """Acrescenta ao Perfil as skills encontradas no PDF que você marcou."""
    form = await request.form()
    escolhidas = [s for s in form.getlist("skill") if s]
    if not escolhidas:
        return go(f"/curriculos/{resume_id}", "Nenhuma skill marcada.", "warn")
    profile = db.get_profile()
    atuais = list(profile.get("skills") or [])
    novas = [s for s in escolhidas if s not in atuais]
    profile["skills"] = atuais + novas
    db.save_profile(profile)
    await run_in_threadpool(collect.rescore)
    return go(f"/curriculos/{resume_id}",
              f"{len(novas)} skill(s) adicionada(s) ao Perfil e vagas repontuadas.")


# ------------------------------------------------------------------ roadmap


@app.get("/roadmap", response_class=HTMLResponse)
def roadmap_page(request: Request) -> HTMLResponse:
    profile = db.get_profile()
    # uma leitura da demanda serve às três seções da tela
    demand = roadmap.demand()
    gaps = roadmap.gaps(profile, counter=demand)
    recommendations = roadmap.recommend(profile, counter=demand)
    return render(
        request,
        "roadmap.html",
        nav="roadmap",
        profile=profile,
        gaps=gaps,
        max_gap=max([g["count"] for g in gaps], default=1),
        strengths=roadmap.strengths(profile, counter=demand),
        projects=recommendations["projects"][:8],
        certifications=recommendations["certifications"][:8],
        board=roadmap.board(),
        total_jobs=db.one("SELECT COUNT(*) AS n FROM jobs")["n"],
    )


@app.post("/roadmap/itens")
async def roadmap_track(request: Request) -> RedirectResponse:
    form = await request.form()
    kind = str(form.get("kind") or "projeto")
    ref = str(form.get("ref") or "")
    status = str(form.get("status") or "planejado")
    if status == "remover":
        roadmap.untrack(kind, ref)
        return go("/roadmap", "Item removido do seu plano.")
    roadmap.track(kind, ref, str(form.get("title") or ref), str(form.get("url") or ""), status)
    return go("/roadmap", "Plano atualizado.")


# ------------------------------------------------------------------ perfil


@app.get("/perfil", response_class=HTMLResponse)
def profile_page(request: Request) -> HTMLResponse:
    return render(request, "profile.html", nav="perfil", all_skills=sorted(skills.TAXONOMY))


@app.post("/perfil")
async def profile_save(request: Request) -> RedirectResponse:
    form = await request.form()

    links = [
        {"label": label.strip(), "url": url.strip()}
        for label, url in zip(form.getlist("link_label"), form.getlist("link_url"))
        if url.strip()
    ]
    languages = [
        {"name": name.strip(), "level": level.strip()}
        for name, level in zip(form.getlist("lang_name"), form.getlist("lang_level"))
        if name.strip()
    ]
    education = [
        {"school": school.strip(), "course": course.strip(), "period": period.strip(), "note": note.strip()}
        for school, course, period, note in zip(
            form.getlist("edu_school"), form.getlist("edu_course"),
            form.getlist("edu_period"), form.getlist("edu_note"),
        )
        if school.strip() or course.strip()
    ]
    experience = [
        {"role": role.strip(), "org": org.strip(), "period": period.strip(), "bullets": _bullets(bullets)}
        for role, org, period, bullets in zip(
            form.getlist("exp_role"), form.getlist("exp_org"),
            form.getlist("exp_period"), form.getlist("exp_bullets"),
        )
        if role.strip() or org.strip()
    ]
    projects = [
        {"name": name.strip(), "url": url.strip(), "stack": stack.strip(), "bullets": _bullets(bullets)}
        for name, url, stack, bullets in zip(
            form.getlist("proj_name"), form.getlist("proj_url"),
            form.getlist("proj_stack"), form.getlist("proj_bullets"),
        )
        if name.strip()
    ]

    db.save_profile(
        {
            "name": str(form.get("name") or ""),
            "headline": str(form.get("headline") or ""),
            "email": str(form.get("email") or ""),
            "phone": str(form.get("phone") or ""),
            "city": str(form.get("city") or ""),
            "area": str(form.get("area") or "backend"),
            "seniority": str(form.get("seniority") or "junior"),
            "summary": str(form.get("summary") or ""),
            "links": links,
            "skills": skills.parse_skill_list(str(form.get("skills") or "")),
            "languages": languages,
            "education": education,
            "experience": experience,
            "projects": projects,
        }
    )
    # repontuar percorre a base inteira: numa thread, para não travar o servidor
    # enquanto roda (é o mesmo processo que serve as outras abas abertas)
    updated = await run_in_threadpool(collect.rescore)
    return go("/perfil", f"Perfil salvo. {updated} vagas repontuadas com o novo perfil.")


# ------------------------------------------------------------------ ajustes


@app.get("/ajustes", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    sources = [dict(r) for r in db.query("SELECT * FROM sources ORDER BY kind, label")]
    searches = [dict(r) for r in db.query("SELECT * FROM searches ORDER BY id")]
    return render(
        request,
        "settings.html",
        nav="ajustes",
        sources=sources,
        searches=searches,
        db_path=str(db.db_path()),
        total_jobs=db.one("SELECT COUNT(*) AS n FROM jobs")["n"],
    )


@app.post("/ajustes")
async def settings_save(request: Request) -> RedirectResponse:
    form = await request.form()
    for key in ("weekly_goal", "min_score", "region_preference", "keywords",
                "exclude_keywords", "anthropic_api_key", "anthropic_model", "theme",
                "refresh_cooldown_min", "notify_min_score"):
        if key in form:
            db.set_setting(key, str(form.get(key) or ""))
    # checkbox não é enviado quando desmarcado: só grava se o bloco veio no formulário
    if "notify_min_score" in form:
        db.set_setting("notify_new_jobs", "1" if form.get("notify_new_jobs") else "")
    await run_in_threadpool(collect.rescore)
    return go("/ajustes", "Ajustes salvos e vagas repontuadas.")


@app.post("/ajustes/fontes")
async def settings_sources(request: Request) -> RedirectResponse:
    form = await request.form()
    action = str(form.get("acao") or "")
    if action == "toggle":
        db.execute("UPDATE sources SET enabled = 1 - enabled WHERE id = ?", (str(form.get("id")),))
        return go("/ajustes", "Fonte atualizada.")
    if action == "adicionar":
        url = str(form.get("url") or "").strip()
        label = str(form.get("label") or "").strip() or "Feed RSS"
        if not url:
            return go("/ajustes", "Informe a URL do feed.", "warn")
        # hash estável entre execuções: `hash()` do Python é aleatorizado por
        # processo, e o mesmo feed acabava cadastrado de novo a cada reinício
        sid = "rss-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        db.execute(
            "INSERT OR REPLACE INTO sources (id, label, kind, url, enabled) VALUES (?, ?, 'rss', ?, 1)",
            (sid, label, url),
        )
        return go("/ajustes", "Feed adicionado.")
    if action == "remover":
        db.execute("DELETE FROM sources WHERE id = ? AND kind = 'rss'", (str(form.get("id")),))
        return go("/ajustes", "Feed removido.")
    if action == "testar":
        source_id = str(form.get("id") or "")
        if not db.one("SELECT id FROM sources WHERE id = ?", (source_id,)):
            return go("/ajustes", "Fonte não encontrada.", "warn")
        report = await run_in_threadpool(collect.run, [source_id])
        entry = report["sources"][0] if report["sources"] else {}
        if entry.get("status") == "ok":
            return go("/ajustes", f"{entry.get('label')}: {entry.get('found')} vagas, {entry.get('new')} novas.")
        return go("/ajustes", f"{entry.get('label')}: {entry.get('error') or 'sem retorno'}", "warn")
    return go("/ajustes", "Ação desconhecida.", "warn")


@app.post("/ajustes/buscas")
async def settings_searches(request: Request) -> RedirectResponse:
    form = await request.form()
    action = str(form.get("acao") or "")
    if action == "adicionar":
        keywords = str(form.get("keywords") or "").strip()
        if not keywords:
            return go("/ajustes", "Escreva o termo de busca.", "warn")
        db.execute(
            "INSERT INTO searches (label, keywords) VALUES (?, ?)",
            (str(form.get("label") or keywords)[:60], keywords),
        )
        return go("/ajustes", "Busca adicionada.")
    search_id = _int(form.get("id"))
    if action in ("remover", "toggle") and not search_id:
        return go("/ajustes", "Busca não encontrada.", "warn")
    if action == "remover":
        db.execute("DELETE FROM searches WHERE id = ?", (search_id,))
        return go("/ajustes", "Busca removida.")
    if action == "toggle":
        db.execute("UPDATE searches SET enabled = 1 - enabled WHERE id = ?", (search_id,))
        return go("/ajustes", "Busca atualizada.")
    return go("/ajustes", "Ação desconhecida.", "warn")


@app.post("/ajustes/exportar")
def settings_export() -> JSONResponse:
    payload = {
        "profile": db.get_profile(),
        "applications": [dict(r) for r in db.query("SELECT * FROM applications")],
        "resumes": [resume_dict(r) for r in db.query("SELECT * FROM resumes")],
        "learning": [dict(r) for r in db.query("SELECT * FROM learning")],
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }
    return JSONResponse(
        json.loads(json.dumps(payload, default=str)),
        headers={"Content-Disposition": 'attachment; filename="farol-backup.json"'},
    )
