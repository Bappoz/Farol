"""Fluxo de ponta a ponta pelas rotas HTTP, com fontes simuladas."""

import conftest
import httpx
import pytest
from fastapi.testclient import TestClient

from farol import ats, collect, db, sources
from farol import resume as resume_mod
from farol import skills as skills_mod
from farol.app import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def perfil():
    db.save_profile(
        {
            "name": "Ana Ribeiro",
            "headline": "Desenvolvedora back-end júnior",
            "email": "ana@exemplo.com",
            "phone": "41 90000-0000",
            "city": "Curitiba, PR",
            "area": "backend",
            "seniority": "junior",
            "summary": "",
            "links": [{"label": "GitHub", "url": "https://github.com/ana"}],
            "skills": ["python", "sql", "docker", "fastapi", "postgresql"],
            "languages": [{"name": "Inglês", "level": "B2"}],
            "education": [{"school": "UFPR", "course": "Sistemas", "period": "2023–2026", "note": ""}],
            "experience": [],
            "projects": [
                {
                    "name": "API de biblioteca",
                    "url": "https://github.com/ana/api",
                    "stack": "FastAPI, PostgreSQL",
                    "bullets": ["Cobri 80% do código com pytest", "Subi com Docker"],
                }
            ],
        }
    )
    return db.get_profile()


def _fontes_gravadas(fixtures, monkeypatch) -> None:
    """Faz as fontes responderem com as amostras de tests/fixtures, sem rede."""
    mapping = {
        "remotive.com": "remotive.json",
        "remoteok.com": "remoteok.json",
        "arbeitnow.com": "arbeitnow.json",
        "himalayas.app": "himalayas.json",
        "weworkremotely.com": "wwr.xml",
        "api.github.com": "vagasbr.json",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        for fragment, filename in mapping.items():
            if fragment in str(request.url):
                return httpx.Response(200, content=(fixtures / filename).read_bytes())
        return httpx.Response(404)

    monkeypatch.setattr(
        sources, "client", lambda timeout=25.0: httpx.Client(transport=httpx.MockTransport(handler))
    )
    db.execute("UPDATE searches SET keywords = 'junior'")


@pytest.fixture
def com_vagas(fixtures, monkeypatch, perfil):
    """Popula a base usando as respostas gravadas em tests/fixtures."""
    _fontes_gravadas(fixtures, monkeypatch)
    return collect.run()


def test_coleta_grava_e_pontua(com_vagas):
    assert com_vagas["new"] >= 5
    rows = db.query("SELECT title, score FROM jobs ORDER BY score DESC")
    assert rows
    assert rows[0]["score"] > rows[-1]["score"]
    assert all(source["status"] == "ok" for source in com_vagas["sources"])


def test_coleta_e_idempotente(com_vagas, fixtures, monkeypatch):
    antes = db.one("SELECT COUNT(*) AS n FROM jobs")["n"]
    collect.run()
    assert db.one("SELECT COUNT(*) AS n FROM jobs")["n"] == antes


def test_coleta_grava_modo_e_faixa_salarial(com_vagas):
    remotive = db.one("SELECT work_mode, salary_min, salary_max FROM jobs WHERE title = 'Junior Python Developer'")
    assert remotive["work_mode"] == "remoto"
    assert (remotive["salary_min"], remotive["salary_max"]) == (40000, 60000)

    sem_salario = db.one("SELECT salary_min, salary_max FROM jobs WHERE title = 'Senior Staff Engineer'")
    assert (sem_salario["salary_min"], sem_salario["salary_max"]) == (None, None)


def test_filtro_de_localizacao_vale_para_vaga_remota(client, com_vagas):
    resposta = client.get("/vagas?estado=todas&min=0&local=Worldwide")
    assert resposta.status_code == 200
    assert "Junior Python Developer" in resposta.text  # candidate_required_location = Worldwide
    assert "Junior Data Analyst" not in resposta.text  # location = Berlin


def test_select_de_localizacao_lista_valores_reais_da_base(client, com_vagas):
    resposta = client.get("/vagas?estado=todas&min=0")
    assert 'value="Worldwide"' in resposta.text
    assert 'value="Berlin"' in resposta.text


def test_filtro_de_modelo_de_trabalho(client, com_vagas):
    """Presencial só aparece desde que os murais brasileiros entraram nas fontes."""
    presenciais = client.get("/vagas?estado=todas&min=0&modo=presencial")
    assert presenciais.status_code == 200
    assert "Desenvolvedor Python Júnior" in presenciais.text

    todos_remotos = client.get("/vagas?estado=todas&min=0&modo=remoto")
    assert "Junior Python Developer" in todos_remotos.text
    assert "Desenvolvedor Python Júnior" not in todos_remotos.text


def test_filtro_de_nivel_encontra_estagios_e_internships(client, perfil):
    db.execute(
        """INSERT INTO jobs (source, source_id, fingerprint, title, description, score)
           VALUES
           ('x', 'estagio', 'fp-estagio', 'Estágio em Python', 'Aprenda com o time.', 60),
           ('x', 'intern', 'fp-intern', 'Software Engineering Internship', 'Internship for students.', 60),
           ('x', 'junior', 'fp-junior', 'Desenvolvedor Python Júnior', 'Primeiro emprego.', 60),
           ('x', 'senior', 'fp-senior', 'Senior Python Engineer', '5+ years experience.', 60)"""
    )
    estagios = client.get("/vagas?estado=todas&min=0&nivel=estagio")
    assert "Estágio em Python" in estagios.text
    assert "Software Engineering Internship" in estagios.text
    assert "Desenvolvedor Python Júnior" not in estagios.text
    assert "Senior Python Engineer" not in estagios.text

    entrada = client.get("/vagas?estado=todas&min=0&nivel=entrada")
    assert "Desenvolvedor Python Júnior" in entrada.text
    assert "Senior Python Engineer" not in entrada.text


def test_paginas_principais_expoem_marcos_acessiveis(client):
    resposta = client.get("/vagas")
    assert resposta.status_code == 200
    assert 'href="#conteudo-principal"' in resposta.text
    assert 'aria-label="Navegação principal"' in resposta.text
    assert 'aria-current="page"' in resposta.text
    assert 'id="conteudo-principal"' in resposta.text


def test_lista_vazia_por_modelo_explica_o_porque(client, perfil):
    """Empty state tem de dizer o porquê, não só 'afrouxe o fit'."""
    db.execute("INSERT INTO jobs (source, source_id, fingerprint, title, work_mode) "
               "VALUES ('x', '1', 'f', 'Dev remoto', 'remoto')")
    resposta = client.get("/vagas?estado=todas&min=0&modo=hibrido")
    assert "Nada por aqui" in resposta.text
    assert "feed" in resposta.text


def test_filtro_de_regiao_agrupa_localizacoes(client, com_vagas):
    brasil = client.get("/vagas?estado=todas&min=0&regiao=brasil")
    assert "Junior Backend Developer" in brasil.text  # Himalayas: "Brazil, Latin America"
    assert "Junior Data Analyst" not in brasil.text   # Berlin

    mundial = client.get("/vagas?estado=todas&min=0&regiao=mundial")
    assert "Junior Python Developer" in mundial.text  # Worldwide
    assert "Junior Backend Developer" not in mundial.text

    outros = client.get("/vagas?estado=todas&min=0&regiao=outros")
    assert "Junior Data Analyst" in outros.text       # Berlin


def test_filtro_de_salario_combina_com_localizacao(client, com_vagas):
    alto = client.get("/vagas?estado=todas&min=0&salario=55000")
    assert "Junior Python Developer" in alto.text       # faixa 40k–60k
    assert "Junior Backend Developer" not in alto.text  # faixa 24k–36k (Himalayas)
    assert "Junior Frontend Engineer" not in alto.text  # faixa 30k–50k (RemoteOK)

    combinado = client.get("/vagas?estado=todas&min=0&salario=55000&local=Worldwide")
    assert "Junior Python Developer" in combinado.text


def test_filtro_de_salario_nao_compara_moedas_diferentes(client, com_vagas):
    """Vaga em euro não pode aparecer num filtro em dólar: o app não converte câmbio."""
    db.execute(
        """INSERT INTO jobs (source, source_id, fingerprint, title, company, location, remote,
                             work_mode, region, salary, salary_min, salary_max, salary_currency,
                             score, score_data)
           VALUES ('arbeitnow', '900', 'eur', 'Euro Engineer', 'Datenhaus', 'Berlin', 1,
                   'remoto', 'outros', 'EUR 90.000', 90000, 90000, 'EUR', 60,
                   '{"matched": [], "missing": [], "flags": [], "components": []}')"""
    )
    em_dolar = client.get("/vagas?estado=todas&min=0&salario=80000&moeda=USD")
    assert "Euro Engineer" not in em_dolar.text

    em_euro = client.get("/vagas?estado=todas&min=0&salario=80000&moeda=EUR")
    assert "Euro Engineer" in em_euro.text


def test_vaga_sem_score_data_nao_derruba_as_paginas(client, perfil):
    """score_data tem DEFAULT '{}' no schema — template não pode assumir as chaves."""
    db.execute(
        """INSERT INTO jobs (source, source_id, fingerprint, title, company, score)
           VALUES ('x', '1', 'fp', 'Vaga crua', 'Sem Nome', 40)"""
    )
    job_id = db.one("SELECT id FROM jobs WHERE title = 'Vaga crua'")["id"]
    assert client.get("/vagas?estado=todas&min=0").status_code == 200
    assert client.get(f"/vagas/{job_id}").status_code == 200


def test_lista_de_vagas_pagina(client, com_vagas, monkeypatch):
    from farol import app as app_mod

    monkeypatch.setattr(app_mod, "PAGE_SIZE", 2)
    primeira = client.get("/vagas?estado=todas&min=0&ordem=empresa")
    assert "página 1 de" in primeira.text
    assert "próximas" in primeira.text

    segunda = client.get("/vagas?estado=todas&min=0&ordem=empresa&pagina=2")
    assert "página 2 de" in segunda.text
    assert "anteriores" in segunda.text

    # títulos da página 2 não repetem os da página 1
    def titulos(texto):
        return {t for t in ("Junior Python Developer", "Junior Frontend Engineer",
                            "Junior Data Analyst", "Junior Backend Developer") if t in texto}

    assert not (titulos(primeira.text) & titulos(segunda.text))


def test_pagina_acima_do_total_cai_na_ultima(client, com_vagas):
    resposta = client.get("/vagas?estado=todas&min=0&pagina=999")
    assert resposta.status_code == 200
    assert "Nada por aqui" not in resposta.text


def test_notificacao_sai_para_vaga_nova_com_fit_alto(fixtures, monkeypatch, perfil):
    chamadas = []
    monkeypatch.setattr(collect.subprocess, "run", lambda cmd, **kw: chamadas.append(cmd))
    db.set_setting("notify_new_jobs", "1")
    db.set_setting("notify_min_score", "40")
    _fontes_gravadas(fixtures, monkeypatch)

    report = collect.run()

    assert report["highlights"], "as vagas de teste têm fit acima de 40"
    assert len(chamadas) == 1
    assert chamadas[0][0] == "notify-send"
    assert "Farol" in " ".join(chamadas[0])


def test_notificacao_desligada_por_padrao(fixtures, monkeypatch, perfil):
    chamadas = []
    monkeypatch.setattr(collect.subprocess, "run", lambda cmd, **kw: chamadas.append(cmd))
    _fontes_gravadas(fixtures, monkeypatch)

    report = collect.run()

    assert report["new"] >= 5
    assert chamadas == []
    assert report["highlights"] == []


def test_notificacao_nao_derruba_coleta_sem_notify_send(monkeypatch):
    def sem_binario(cmd, **kw):
        raise FileNotFoundError("notify-send")

    monkeypatch.setattr(collect.subprocess, "run", sem_binario)
    assert collect.notify([{"title": "Dev", "company": "X", "score": 90}]) is False


def test_notificacao_ignora_fit_abaixo_do_limite(fixtures, monkeypatch, perfil):
    chamadas = []
    monkeypatch.setattr(collect.subprocess, "run", lambda cmd, **kw: chamadas.append(cmd))
    db.set_setting("notify_new_jobs", "1")
    db.set_setting("notify_min_score", "99")
    _fontes_gravadas(fixtures, monkeypatch)

    report = collect.run()

    assert report["new"] >= 5
    assert report["highlights"] == []
    assert chamadas == []


def test_fonte_quebrada_vira_diagnostico(monkeypatch, perfil):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    monkeypatch.setattr(
        sources, "client", lambda timeout=25.0: httpx.Client(transport=httpx.MockTransport(handler))
    )
    report = collect.run(["remotive"])
    assert report["sources"][0]["status"] == "erro"
    assert "500" in report["sources"][0]["error"]
    assert db.one("SELECT last_status FROM sources WHERE id = 'remotive'")["last_status"] == "erro"


def test_abertura_do_app_coleta_uma_vez(monkeypatch, perfil):
    """Sem histórico, a abertura coleta; logo depois, a janela de descanso segura."""
    chamadas = []

    def fake_run(source_ids=None):
        chamadas.append(source_ids)
        db.execute("UPDATE sources SET last_run_at = datetime('now'), last_status = 'ok'")
        return {"sources": [], "new": 0}

    monkeypatch.setattr(collect, "run", fake_run)
    db.set_setting("refresh_cooldown_min", "45")

    assert collect.start()["verdict"] == "iniciada"
    conftest.wait_for_collect()
    assert len(chamadas) == 1

    # reabrir o app agora não pode gerar requisição nenhuma
    segunda = collect.start()
    assert segunda["verdict"] == "descanso"
    assert segunda["next_in_min"] > 0
    assert len(chamadas) == 1

    # o botão dentro do app fura a janela
    assert collect.start(force=True)["verdict"] == "iniciada"
    conftest.wait_for_collect()
    assert len(chamadas) == 2


def test_janela_zerada_sempre_coleta(monkeypatch, perfil):
    monkeypatch.setattr(collect, "run", lambda source_ids=None: {"sources": [], "new": 0})
    db.execute("UPDATE sources SET last_run_at = datetime('now'), last_status = 'ok'")
    db.set_setting("refresh_cooldown_min", "0")
    assert collect.start()["verdict"] == "iniciada"
    conftest.wait_for_collect()


def test_rotas_de_coleta(client, monkeypatch, perfil):
    monkeypatch.setattr(collect, "run", lambda source_ids=None: {"sources": [], "new": 3})

    resposta = client.post("/coleta")
    assert resposta.status_code == 200
    assert resposta.json()["verdict"] == "iniciada"
    estado = conftest.wait_for_collect()
    assert estado["report"]["new"] == 3

    status = client.get("/coleta/status").json()
    assert status["running"] is False
    assert status["report"]["new"] == 3

    # a coleta manual não bloqueia a resposta HTTP
    manual = client.post("/vagas/atualizar", data={"back": "/"}, follow_redirects=False)
    assert manual.status_code == 303
    assert manual.headers["location"].startswith("/?msg=")
    conftest.wait_for_collect()


@pytest.mark.parametrize("rota", ["/", "/vagas", "/pipeline", "/curriculos", "/roadmap", "/perfil", "/ajustes"])
def test_paginas_abrem(client, rota, com_vagas):
    response = client.get(rota)
    assert response.status_code == 200
    assert "Farol" in response.text


def test_fluxo_vaga_ate_curriculo(client, com_vagas):
    job = db.query("SELECT id FROM jobs ORDER BY score DESC LIMIT 1")[0]

    assert client.get(f"/vagas/{job['id']}").status_code == 200

    salvar = client.post(f"/vagas/{job['id']}/salvar", follow_redirects=False)
    assert salvar.status_code == 303
    app_id = int(salvar.headers["location"].split("/candidaturas/")[1].split("?")[0])

    detalhe = client.get(f"/candidaturas/{app_id}")
    assert detalhe.status_code == 200

    client.post(
        f"/candidaturas/{app_id}",
        data={"title": "Dev júnior", "company": "Northwind", "url": "", "status": "candidatado",
              "next_action": "Follow-up", "next_action_at": "2026-08-05", "contact": "", "notes": "", "prep": ""},
        follow_redirects=False,
    )
    atualizada = db.one("SELECT * FROM applications WHERE id = ?", (app_id,))
    assert atualizada["status"] == "candidatado"
    assert atualizada["applied_at"] is not None
    assert db.query("SELECT * FROM events WHERE application_id = ? AND kind = 'status'", (app_id,))

    criar = client.post("/curriculos", data={"job_id": str(job["id"]), "name": ""}, follow_redirects=False)
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])
    editor = client.get(f"/curriculos/{resume_id}")
    assert editor.status_code == 200
    assert "Ana Ribeiro" in client.get(f"/curriculos/{resume_id}/imprimir").text


def test_curriculo_em_ingles(client, com_vagas, perfil):
    job = db.query("SELECT id FROM jobs ORDER BY score DESC LIMIT 1")[0]
    criar = client.post(
        "/curriculos", data={"job_id": str(job["id"]), "name": "", "lang": "en"},
        follow_redirects=False,
    )
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])
    assert db.one("SELECT lang FROM resumes WHERE id = ?", (resume_id,))["lang"] == "en"

    impresso = client.get(f"/curriculos/{resume_id}/imprimir").text
    assert "Summary" in impresso and "Skills" in impresso and "Education" in impresso
    assert "Competências" not in impresso
    assert "Automated testing" not in impresso  # o perfil de teste não tem essa skill
    assert 'lang="en"' in impresso

    carta = db.one("SELECT letter FROM resumes WHERE id = ?", (resume_id,))["letter"]
    assert "I'm applying for the" in carta
    assert resume_mod.PLACEHOLDER in carta


def test_traducao_fica_no_curriculo_e_nao_no_perfil(client, com_vagas, perfil):
    criar = client.post("/curriculos", data={"name": "CV EN", "lang": "en"}, follow_redirects=False)
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])

    client.post(
        f"/curriculos/{resume_id}",
        data={
            "name": "CV EN", "lang": "en",
            "headline": "Junior Backend Developer",
            "summary": "Final-year IT student with two projects in production.",
            "skills": ["python", "sql"],
            "proj_indice": ["0"], "proj_incluir": ["0"],
            "proj_name_0": "Library API", "proj_url_0": "https://github.com/ana/api",
            "proj_stack_0": "FastAPI, PostgreSQL",
            "proj_bullets_0": "Covered 80% of the code with pytest\nShipped with Docker",
            "letter": "Hello,",
        },
        follow_redirects=False,
    )

    salvo = db.loads(db.one("SELECT data FROM resumes WHERE id = ?", (resume_id,))["data"])
    assert salvo["headline"] == "Junior Backend Developer"
    assert salvo["projects"][0]["name"] == "Library API"
    assert salvo["projects"][0]["bullets"] == [
        "Covered 80% of the code with pytest", "Shipped with Docker",
    ]
    assert salvo["skills"] == ["python", "sql"]

    # o perfil segue em português, intocado
    assert db.get_profile()["projects"][0]["name"] == "API de biblioteca"

    # e o texto traduzido sobrevive a um novo salvamento
    assert "Library API" in client.get(f"/curriculos/{resume_id}/imprimir").text


def test_modelo_de_curriculo_e_escolhido_na_criacao(client, com_vagas, perfil):
    criar = client.post(
        "/curriculos", data={"name": "CV moderno", "lang": "pt", "template": "moderno"},
        follow_redirects=False,
    )
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])
    assert db.one("SELECT template FROM resumes WHERE id = ?", (resume_id,))["template"] == "moderno"

    impresso = client.get(f"/curriculos/{resume_id}/imprimir").text
    assert 'class="sheet t-moderno"' in impresso


def test_modelo_padrao_e_o_recomendado_para_ats(client, perfil):
    criar = client.post("/curriculos", data={"name": "CV"}, follow_redirects=False)
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])
    assert db.one("SELECT template FROM resumes WHERE id = ?", (resume_id,))["template"] == "sober"
    assert resume_mod.TEMPLATES["sober"]["recommended"] is True
    assert sum(1 for m in resume_mod.TEMPLATES.values() if m["recommended"]) == 1


def test_modelo_invalido_cai_no_padrao(client, perfil):
    criar = client.post(
        "/curriculos", data={"name": "CV", "template": "../etc/passwd"}, follow_redirects=False
    )
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])
    assert db.one("SELECT template FROM resumes WHERE id = ?", (resume_id,))["template"] == "sober"


def test_trocar_de_modelo_nao_perde_o_texto_escrito(client, perfil):
    criar = client.post("/curriculos", data={"name": "CV", "template": "sober"}, follow_redirects=False)
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])

    client.post(
        f"/curriculos/{resume_id}",
        data={"name": "CV", "lang": "pt", "template": "compacto",
              "headline": "Dev júnior", "summary": "Resumo que eu escrevi.",
              "skills": ["python"]},
        follow_redirects=False,
    )

    linha = db.one("SELECT template, data FROM resumes WHERE id = ?", (resume_id,))
    assert linha["template"] == "compacto"
    assert db.loads(linha["data"])["summary"] == "Resumo que eu escrevi."


def test_banco_antigo_ganha_a_coluna_de_modelo():
    with db.connect() as conn:
        conn.execute("DROP TABLE resumes")
        conn.execute(
            """CREATE TABLE resumes (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                   job_id INTEGER, application_id INTEGER, lang TEXT NOT NULL DEFAULT 'pt',
                   kind TEXT NOT NULL DEFAULT 'montado', file TEXT NOT NULL DEFAULT '',
                   data TEXT NOT NULL DEFAULT '{}', letter TEXT NOT NULL DEFAULT '',
                   created_at TEXT NOT NULL DEFAULT (datetime('now')),
                   updated_at TEXT NOT NULL DEFAULT (datetime('now')))"""
        )
        conn.execute("INSERT INTO resumes (name) VALUES ('CV sem modelo')")

    db.bootstrap()

    assert db.one("SELECT template FROM resumes WHERE name = 'CV sem modelo'")["template"] == "sober"


def test_remontar_descarta_edicoes(client, com_vagas, perfil):
    criar = client.post("/curriculos", data={"name": "CV", "lang": "pt"}, follow_redirects=False)
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])
    client.post(f"/curriculos/{resume_id}",
                data={"name": "CV", "lang": "pt", "headline": "Traduzido", "summary": "x"},
                follow_redirects=False)
    assert db.loads(db.one("SELECT data FROM resumes WHERE id=?", (resume_id,))["data"])["headline"] == "Traduzido"

    client.post(f"/curriculos/{resume_id}/reconstruir", follow_redirects=False)
    refeito = db.loads(db.one("SELECT data FROM resumes WHERE id=?", (resume_id,))["data"])
    assert refeito["headline"] == "Desenvolvedora back-end júnior"
    assert refeito["projects"][0]["name"] == "API de biblioteca"


def test_banco_antigo_ganha_a_coluna_de_idioma():
    """Quem já tinha o app instalado não pode precisar apagar o banco."""
    with db.connect() as conn:
        conn.execute("DROP TABLE resumes")
        conn.execute(  # recria a tabela como era antes do idioma existir
            """CREATE TABLE resumes (
                   id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                   job_id INTEGER, application_id INTEGER, data TEXT NOT NULL DEFAULT '{}',
                   letter TEXT NOT NULL DEFAULT '',
                   created_at TEXT NOT NULL DEFAULT (datetime('now')),
                   updated_at TEXT NOT NULL DEFAULT (datetime('now')))"""
        )
        conn.execute("INSERT INTO resumes (name) VALUES ('CV antigo')")

    db.bootstrap()

    linha = db.one("SELECT * FROM resumes WHERE name = 'CV antigo'")
    assert linha["lang"] == "pt"  # currículo que já existia continua em português


def _recria_jobs_sem_colunas_derivadas(conn) -> None:
    """Recria a tabela jobs como era antes de work_mode/region/salary_* existirem."""
    conn.execute("DROP TABLE jobs")
    conn.execute(
        """CREATE TABLE jobs (
               id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, source_id TEXT NOT NULL,
               fingerprint TEXT NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL DEFAULT '',
               url TEXT NOT NULL DEFAULT '', apply_url TEXT NOT NULL DEFAULT '',
               location TEXT NOT NULL DEFAULT '', remote INTEGER NOT NULL DEFAULT 1,
               salary TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
               description TEXT NOT NULL DEFAULT '', published_at TEXT,
               first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
               last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
               score INTEGER NOT NULL DEFAULT 0, score_data TEXT NOT NULL DEFAULT '{}',
               state TEXT NOT NULL DEFAULT 'novo')"""
    )


def test_banco_antigo_ganha_as_colunas_de_modelo_e_salario():
    """Idem para jobs: banco de antes do filtro de modelo/salário não pode quebrar."""
    with db.connect() as conn:
        _recria_jobs_sem_colunas_derivadas(conn)
        conn.execute(
            "INSERT INTO jobs (source, source_id, fingerprint, title) VALUES ('x', '1', 'fp', 'Vaga antiga')"
        )

    db.bootstrap()

    linha = db.one("SELECT * FROM jobs WHERE title = 'Vaga antiga'")
    assert linha["work_mode"] == "remoto"
    assert linha["salary_min"] is None and linha["salary_max"] is None


def test_migracao_recalcula_modo_das_vagas_que_ja_estavam_no_banco():
    """O DEFAULT do ALTER TABLE marcaria toda vaga como remota — e aí presencial vinha vazio."""
    with db.connect() as conn:
        _recria_jobs_sem_colunas_derivadas(conn)
        conn.execute(
            """INSERT INTO jobs (source, source_id, fingerprint, title, location, remote, salary)
               VALUES ('arbeitnow', '1', 'a', 'Dev presencial', 'Berlin', 0, 'EUR 50.000 - 70.000')"""
        )
        conn.execute(
            """INSERT INTO jobs (source, source_id, fingerprint, title, location, remote, salary)
               VALUES ('arbeitnow', '2', 'b', 'Dev híbrido', 'São Paulo (híbrido)', 0, '')"""
        )
        conn.execute(
            """INSERT INTO jobs (source, source_id, fingerprint, title, location, remote, salary)
               VALUES ('remotive', '3', 'c', 'Dev remoto', 'Brazil', 1, 'US$ 40.000')"""
        )

    db.bootstrap()

    modos = {r["title"]: r["work_mode"] for r in db.query("SELECT title, work_mode FROM jobs")}
    assert modos == {
        "Dev presencial": "presencial",
        "Dev híbrido": "hibrido",
        "Dev remoto": "remoto",
    }

    presencial = db.one("SELECT * FROM jobs WHERE title = 'Dev presencial'")
    assert presencial["region"] == "outros"
    assert (presencial["salary_min"], presencial["salary_currency"]) == (50000, "EUR")

    remoto = db.one("SELECT region, salary_currency FROM jobs WHERE title = 'Dev remoto'")
    assert remoto["region"] == "brasil"
    assert remoto["salary_currency"] == "USD"


def test_kanban_move_por_json(client, com_vagas):
    app_id = db.execute("INSERT INTO applications (title, status) VALUES ('Dev', 'salva')")
    response = client.post(f"/candidaturas/{app_id}/status", json={"status": "entrevista"})
    assert response.status_code == 200
    assert db.one("SELECT status FROM applications WHERE id = ?", (app_id,))["status"] == "entrevista"
    assert client.post(f"/candidaturas/{app_id}/status", json={"status": "inventado"}).status_code == 400


def test_perfil_salva_e_repontua(client, com_vagas):
    antes = db.one("SELECT score FROM jobs ORDER BY id LIMIT 1")["score"]
    response = client.post(
        "/perfil",
        data={
            "name": "Ana Ribeiro", "headline": "Dev", "email": "ana@exemplo.com", "phone": "",
            "city": "", "area": "backend", "seniority": "senior", "summary": "",
            "skills": "kubernetes, go",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.get_profile()["skills"] == ["kubernetes", "go"]
    depois = db.one("SELECT score FROM jobs ORDER BY id LIMIT 1")["score"]
    assert depois != antes


def test_curriculo_nao_inventa_dados(perfil):
    data = resume_mod.build(perfil, None)
    assert data["name"] == "Ana Ribeiro"
    assert data["projects"][0]["name"] == "API de biblioteca"
    assert resume_mod.PLACEHOLDER in data["summary"]  # perfil sem resumo → marca o que falta
    # e o verificador acusa o rascunho que ficou, em vez de deixar passar
    pendentes = {fix["key"] for fix in ats.check(data)["fixes"]}
    assert {"resumo", "pendencias"} <= pendentes
    assert "codigo" not in pendentes  # o GitHub do perfil está no cabeçalho


def test_carta_marca_o_que_falta(perfil):
    job = {"title": "Junior Python Developer", "company": "Northwind",
           "description": "Python e FastAPI", "tags": []}
    letter = resume_mod.cover_letter(perfil, job)
    assert "Junior Python Developer" in letter
    assert "Northwind" in letter
    assert resume_mod.PLACEHOLDER in letter


def test_roadmap_usa_as_vagas_coletadas(com_vagas, perfil):
    from farol import roadmap

    gaps = roadmap.gaps(perfil)
    assert gaps, "deveria haver lacunas com as vagas de teste"
    assert all(g["skill"] not in perfil["skills"] for g in gaps)

    recomendacoes = roadmap.recommend(perfil)
    assert recomendacoes["projects"][0]["in_area"] is True
    assert recomendacoes["certifications"]


def test_ajustes_alteram_pontuacao(client, com_vagas):
    response = client.post(
        "/ajustes",
        data={"weekly_goal": "7", "min_score": "10", "region_preference": "worldwide",
              "keywords": "junior", "exclude_keywords": "senior",
              "anthropic_api_key": "", "anthropic_model": "claude-sonnet-5"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.get_settings()["weekly_goal"] == "7"


def test_fonte_rss_customizada(client, com_vagas):
    response = client.post(
        "/ajustes/fontes",
        data={"acao": "adicionar", "label": "Meu feed", "url": "https://exemplo.com/f.rss"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db.one("SELECT COUNT(*) AS n FROM sources WHERE kind = 'rss'")["n"] == 1


def test_idiomas_do_curriculo_sao_editaveis(client, com_vagas, perfil):
    criar = client.post("/curriculos", data={"name": "CV EN", "lang": "en"}, follow_redirects=False)
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])
    client.post(
        f"/curriculos/{resume_id}",
        data={"name": "CV EN", "lang": "en", "headline": "Dev", "summary": "x",
              "idi_indice": ["0"], "idi_incluir": ["0"],
              "idi_name_0": "English", "idi_level_0": "B2"},
        follow_redirects=False,
    )
    salvo = db.loads(db.one("SELECT data FROM resumes WHERE id = ?", (resume_id,))["data"])
    assert salvo["languages"] == [{"name": "English", "level": "B2"}]
    assert db.get_profile()["languages"][0]["name"] == "Inglês"  # perfil intocado


def _pdf_bytes(*linhas: str) -> bytes:
    """PDF de uma página com camada de texto de verdade, montado à mão."""
    content = "BT /F1 11 Tf 40 760 Td 14 TL\n" + "\n".join(f"({line}) Tj T*" for line in linhas) + "\nET"
    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        None,  # o stream de conteúdo
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for numero, objeto in enumerate(objetos, start=1):
        offsets.append(len(out))
        if objeto is None:
            data = content.encode("latin-1")
            out += f"{numero} 0 obj\n<< /Length {len(data)} >>\nstream\n".encode()
            out += data + b"\nendstream\nendobj\n"
        else:
            out += f"{numero} 0 obj\n{objeto}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_pdf_enviado_vira_curriculo(client, com_vagas, perfil):
    from farol import pdfs

    job = db.query("SELECT id FROM jobs ORDER BY score DESC LIMIT 1")[0]
    conteudo = _pdf_bytes("Ana Ribeiro", "Python, FastAPI, Kubernetes and Terraform", "Junior developer")

    resposta = client.post(
        "/curriculos/arquivo",
        data={"name": "CV atual", "lang": "pt", "job_id": str(job["id"])},
        files={"arquivo": ("meu-cv.pdf", conteudo, "application/pdf")},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    resume_id = int(resposta.headers["location"].split("/curriculos/")[1].split("?")[0])

    linha = db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,))
    assert linha["kind"] == "arquivo"
    assert pdfs.path_for(linha["file"]).exists()
    assert linha["job_id"] == job["id"]

    # a página mostra o que foi lido do PDF e oferece as skills novas
    pagina = client.get(f"/curriculos/{resume_id}").text
    assert "Kubernetes" in pagina and "Terraform" in pagina

    # o arquivo é servido de volta
    baixado = client.get(f"/curriculos/{resume_id}/arquivo")
    assert baixado.status_code == 200
    assert baixado.content[:5] == b"%PDF-"

    # importar as skills encontradas acrescenta ao perfil sem apagar as antigas
    client.post(f"/curriculos/{resume_id}/skills",
                data={"skill": ["kubernetes", "terraform"]}, follow_redirects=False)
    skills_perfil = db.get_profile()["skills"]
    assert "kubernetes" in skills_perfil and "terraform" in skills_perfil
    assert "python" in skills_perfil

    # excluir tira o arquivo do disco também
    caminho = pdfs.path_for(linha["file"])
    client.post(f"/curriculos/{resume_id}/excluir", follow_redirects=False)
    assert not caminho.exists()


def test_upload_recusa_o_que_nao_e_pdf(client, perfil):
    resposta = client.post(
        "/curriculos/arquivo",
        files={"arquivo": ("virus.pdf", b"MZ\x90\x00 nao sou pdf", "application/pdf")},
        follow_redirects=False,
    )
    assert resposta.status_code == 303
    assert "n%C3%A3o+%C3%A9" in resposta.headers["location"] or "tone=warn" in resposta.headers["location"]
    assert db.one("SELECT COUNT(*) AS n FROM resumes")["n"] == 0


def test_pdf_sem_texto_avisa_em_vez_de_fingir(client, perfil):
    import io

    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)

    resposta = client.post(
        "/curriculos/arquivo", data={"name": "Escaneado"},
        files={"arquivo": ("scan.pdf", buffer.getvalue(), "application/pdf")},
        follow_redirects=False,
    )
    resume_id = int(resposta.headers["location"].split("/curriculos/")[1].split("?")[0])
    pagina = client.get(f"/curriculos/{resume_id}").text
    assert "camada de texto" in pagina


def test_editor_nao_mexe_em_pdf_enviado(client, perfil):
    conteudo = _pdf_bytes("Ana Ribeiro")
    resposta = client.post("/curriculos/arquivo", data={"name": "CV"},
                           files={"arquivo": ("cv.pdf", conteudo, "application/pdf")},
                           follow_redirects=False)
    resume_id = int(resposta.headers["location"].split("/curriculos/")[1].split("?")[0])

    for rota in (f"/curriculos/{resume_id}", f"/curriculos/{resume_id}/reconstruir",
                 f"/curriculos/{resume_id}/ia"):
        assert client.post(rota, data={"acao": "resumo"}, follow_redirects=False).status_code == 303
    assert client.get(f"/curriculos/{resume_id}/imprimir", follow_redirects=False).status_code == 303
    assert client.get(f"/curriculos/{resume_id}/preview", follow_redirects=False).status_code == 303
    assert db.one("SELECT kind, data FROM resumes WHERE id = ?", (resume_id,))["data"] == "{}"


def test_preview_e_a_mesma_folha_sem_a_barra_de_acoes(client, com_vagas, perfil):
    """O iframe da edição carrega esta rota: mesmo documento, sem os botões."""
    criar = client.post("/curriculos", data={"name": "CV"}, follow_redirects=False)
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])

    impresso = client.get(f"/curriculos/{resume_id}/imprimir").text
    preview = client.get(f"/curriculos/{resume_id}/preview").text

    assert "Ana Ribeiro" in preview
    assert 'class="sheet' in preview
    assert "print-bar" in impresso and "print-bar" not in preview
    assert 'class="embed"' in preview

    editor = client.get(f"/curriculos/{resume_id}").text
    assert f"/curriculos/{resume_id}/preview" in editor


# ------------------------------------------------------ entrada malformada
# Todos estes casos devolviam 500 antes: valor não numérico onde a rota esperava
# inteiro, e corpo JSON vazio. São entrada possível — link colado, formulário
# editado, extensão do navegador — e não podem derrubar a página.


@pytest.mark.parametrize(
    "url",
    [
        "/vagas?pagina=abc",
        "/vagas?pagina=-3",
        "/vagas?min=abc",
        "/vagas?min=999",
        "/vagas?salario=abc",
        "/vagas?salario=-1",
        "/vagas?moeda=XPTO&salario=10",
        "/vagas?regiao=inexistente",
        "/vagas?modo=inexistente",
        "/vagas?ordem=inexistente",
    ],
)
def test_filtros_com_valor_invalido_nao_derrubam_a_lista(client, com_vagas, url):
    assert client.get(url).status_code == 200


def test_remover_busca_com_id_nao_numerico(client):
    resposta = client.post("/ajustes/buscas", data={"acao": "remover", "id": "abc"},
                           follow_redirects=False)
    assert resposta.status_code == 303
    assert "encontrada" in resposta.headers["location"]


def test_criar_curriculo_com_job_id_nao_numerico(client, perfil):
    resposta = client.post("/curriculos", data={"job_id": "abc"}, follow_redirects=False)
    assert resposta.status_code == 303
    resume_id = int(resposta.headers["location"].split("/curriculos/")[1].split("?")[0])
    assert db.one("SELECT job_id FROM resumes WHERE id = ?", (resume_id,))["job_id"] is None


def test_mudar_etapa_com_corpo_vazio(client):
    app_id = db.execute("INSERT INTO applications (title) VALUES ('Vaga')")
    resposta = client.post(f"/candidaturas/{app_id}/status", content=b"",
                           headers={"Content-Type": "application/json"})
    assert resposta.status_code == 400


def test_estado_de_vaga_fora_da_lista_e_recusado(client, com_vagas):
    job_id = db.one("SELECT id FROM jobs LIMIT 1")["id"]
    resposta = client.post(f"/vagas/{job_id}/estado", data={"state": "lixo"},
                           follow_redirects=False)
    assert resposta.status_code == 303
    # a vaga continua visível: um estado desconhecido a esconderia de todo filtro
    assert db.one("SELECT state FROM jobs WHERE id = ?", (job_id,))["state"] == "novo"


def test_endereco_inexistente_devolve_pagina_e_404(client):
    resposta = client.get("/nao-existe")
    assert resposta.status_code == 404
    assert "text/html" in resposta.headers["content-type"]
    assert "não encontrada" in resposta.text


# ------------------------------------------------------------- fontes RSS


def test_feed_rss_recebe_id_estavel(client):
    """`hash()` do Python é aleatório por processo: o mesmo feed voltava duplicado."""
    url = "https://exemplo.com/vagas.rss"
    for _ in range(2):
        client.post("/ajustes/fontes", data={"acao": "adicionar", "label": "Feed", "url": url})
    feeds = db.query("SELECT id FROM sources WHERE kind = 'rss'")
    assert len(feeds) == 1

    esperado = feeds[0]["id"]
    db.execute("DELETE FROM sources WHERE kind = 'rss'")
    client.post("/ajustes/fontes", data={"acao": "adicionar", "label": "Feed", "url": url})
    assert db.one("SELECT id FROM sources WHERE kind = 'rss'")["id"] == esperado


def test_testar_fonte_inexistente_avisa(client):
    resposta = client.post("/ajustes/fontes", data={"acao": "testar", "id": "nao-existe"},
                           follow_redirects=False)
    assert "Fonte+n%C3%A3o+encontrada" in resposta.headers["location"]


# ------------------------------------------------- skills gravadas na vaga


def test_skills_da_vaga_sao_gravadas_na_ingestao(com_vagas):
    """O Roadmap lê esta coluna em vez de reprocessar a descrição de cada vaga."""
    row = db.one("SELECT skills, description FROM jobs WHERE skills <> '[]' LIMIT 1")
    assert row is not None
    gravadas = db.loads(row["skills"], [])
    assert gravadas
    assert set(gravadas) <= set(skills_mod.TAXONOMY)


def test_repontuar_atualiza_as_skills_gravadas(com_vagas):
    db.execute("UPDATE jobs SET skills = '[]'")
    collect.rescore()
    assert db.one("SELECT COUNT(*) AS n FROM jobs WHERE skills <> '[]'")["n"] > 0


def test_demanda_do_roadmap_sai_da_coluna_gravada(com_vagas):
    from farol import roadmap

    assert roadmap.demand()
    db.execute("UPDATE jobs SET skills = '[]'")
    assert roadmap.demand() == {}


# ------------------------------------------------------------- layout servido
# Regras que não têm como falhar de forma barulhenta: o layout continua
# "funcionando", só quebra a página em silêncio. Ficam travadas aqui.


def test_toda_tabela_larga_rola_dentro_do_cartao():
    """`table.data` fora de `.table-wrap` empurra a página inteira na horizontal.

    Aconteceu no Roadmap e na lista de currículos: a folha de estilo já previa o
    contêiner de rolagem, mas dois templates não o usavam.
    """
    from pathlib import Path

    from farol.app import PKG_DIR

    faltando = [
        caminho.name
        for caminho in sorted(Path(PKG_DIR / "templates").glob("*.html"))
        for texto in [caminho.read_text(encoding="utf-8")]
        if '<table class="data">' in texto
        and texto.count('<div class="table-wrap"><table class="data">') != texto.count('<table class="data">')
    ]
    assert not faltando, f"tabela sem .table-wrap em: {faltando}"


def test_url_dos_estaticos_muda_quando_o_arquivo_muda(client):
    """Sem isso o navegador serve o CSS antigo do cache depois de um `farol update`."""
    from farol import __version__
    from farol.app import ASSETS_VERSION

    assert ASSETS_VERSION.startswith(__version__)
    assert __version__ != ASSETS_VERSION  # a versão sozinha não invalida nada

    html = client.get("/").text
    assert f"/static/app.css?v={ASSETS_VERSION}" in html
    assert f"/static/app.js?v={ASSETS_VERSION}" in html


def test_pipeline_usa_a_tela_toda_e_declara_o_numero_de_colunas(client):
    """O quadro divide a largura entre as etapas; o CSS precisa saber quantas são."""
    html = client.get("/pipeline").text
    assert 'class="content wide"' in html
    assert f"--cols: {len(db.STATUSES)}" in html


def test_paginas_fecham_todas_as_divs(client, com_vagas, perfil):
    """`</div>` sobrando fecha o grid cedo e joga o cartão seguinte para fora dele.

    Foi o que acontecia em Métricas: "Paradas" saía da grade de duas colunas e
    ia para a largura inteira, deixando meia tela vazia ao lado do cartão irmão.
    O navegador não reclama — ele conserta o HTML e mostra o layout errado.
    """
    db.execute(
        """INSERT INTO applications (job_id, title, company, status, next_action)
           VALUES (NULL, 'Vaga manual', 'Empresa', 'salva', 'Enviar')"""
    )
    criar = client.post("/curriculos", data={"name": "CV"}, follow_redirects=False)
    resume_id = int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])
    app_id = db.one("SELECT id FROM applications LIMIT 1")["id"]

    rotas = ["/", "/vagas", "/pipeline", "/curriculos", "/metricas", "/roadmap",
             "/perfil", "/ajustes", f"/candidaturas/{app_id}", f"/curriculos/{resume_id}"]
    desbalanceadas = {
        rota: (html.count("<div"), html.count("</div>"))
        for rota in rotas
        for html in [client.get(rota).text]
        if html.count("<div") != html.count("</div>")
    }
    assert not desbalanceadas, f"<div> sem fechamento par: {desbalanceadas}"


# ------------------------------------------------------- oficina de currículo


def _novo_curriculo(client, **campos) -> int:
    criar = client.post("/curriculos", data={"name": "CV", **campos}, follow_redirects=False)
    return int(criar.headers["location"].split("/curriculos/")[1].split("?")[0])


def _formulario(resume_id: int, **mudancas) -> dict:
    """O formulário da oficina como o navegador o enviaria, a partir do que está salvo."""
    linha = db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,))
    data = db.loads(linha["data"], {})
    form: dict = {
        "name": linha["name"], "lang": linha["lang"], "template": linha["template"],
        "headline": data["headline"], "summary": data["summary"], "skills": data["skills"],
        "letter": linha["letter"],
    }
    for prefixo, chave, campos in (
        ("exp", "experience", ("role", "org", "period")),
        ("proj", "projects", ("name", "url", "stack")),
        ("edu", "education", ("course", "school", "period", "note")),
        ("idi", "languages", ("name", "level")),
    ):
        indices = [str(i) for i in range(len(data[chave]))]
        form[f"{prefixo}_indice"] = indices
        form[f"{prefixo}_incluir"] = list(indices)
        for i, item in enumerate(data[chave]):
            for campo in campos:
                form[f"{prefixo}_{campo}_{i}"] = item.get(campo, "")
            if "bullets" in item:
                form[f"{prefixo}_bullets_{i}"] = "\n".join(item["bullets"])
    form.update(mudancas)
    return form


@pytest.mark.parametrize("modelo", ["harvard", "faang", "designer"])
def test_padroes_conhecidos_de_curriculo(client, perfil, modelo):
    resume_id = _novo_curriculo(client, template=modelo)
    folha = client.get(f"/curriculos/{resume_id}/imprimir").text
    assert f'class="sheet t-{modelo}"' in folha
    assert "Ana Ribeiro" in folha and "API de biblioteca" in folha


def test_harvard_poe_formacao_antes_dos_projetos_e_sobrio_depois(client, perfil):
    harvard = client.get(f"/curriculos/{_novo_curriculo(client, template='harvard')}/imprimir").text
    sobrio = client.get(f"/curriculos/{_novo_curriculo(client, template='sober')}/imprimir").text
    assert harvard.index("<h2>Formação</h2>") < harvard.index("<h2>Projetos</h2>")
    assert sobrio.index("<h2>Projetos</h2>") < sobrio.index("<h2>Formação</h2>")


def test_designer_e_o_unico_de_duas_colunas_e_o_verificador_avisa(client, perfil):
    assert [k for k in resume_mod.TEMPLATES if resume_mod.layout(k)["columns"] == "duas-colunas"] == ["designer"]
    resume_id = _novo_curriculo(client, template="designer")
    assert 'class="cols"' in client.get(f"/curriculos/{resume_id}/imprimir").text
    assert "usa duas colunas" in client.get(f"/curriculos/{resume_id}").text


def test_todo_modelo_mostra_todas_as_secoes(perfil):
    todas = set(resume_mod.DEFAULT_ORDER)
    for codigo in resume_mod.TEMPLATES:
        desenho = resume_mod.layout(codigo)
        assert set(desenho["order"]) | set(desenho["side"]) == todas, codigo
        assert not set(desenho["order"]) & set(desenho["side"]), codigo


def test_trocar_para_modelo_novo_nao_muda_o_conteudo(client, perfil):
    resume_id = _novo_curriculo(client)
    antes = db.loads(db.one("SELECT data FROM resumes WHERE id = ?", (resume_id,))["data"], {})
    client.post(f"/curriculos/{resume_id}", data=_formulario(resume_id, template="designer"),
                follow_redirects=False)
    linha = db.one("SELECT template, data FROM resumes WHERE id = ?", (resume_id,))
    assert linha["template"] == "designer"
    assert db.loads(linha["data"], {}) == antes


def test_folha_ao_vivo_mostra_a_edicao_sem_gravar(client, perfil):
    resume_id = _novo_curriculo(client)
    antes = dict(db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,)))

    resposta = client.post(
        f"/curriculos/{resume_id}/ao-vivo",
        data=_formulario(resume_id, summary="Resumo digitado agora.", template="faang", lang="en"),
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "Resumo digitado agora." in corpo["sheet"]
    assert 'class="sheet t-faang"' in corpo["sheet"]
    assert "<h2>Summary</h2>" in corpo["sheet"]
    assert corpo["sheet"].lstrip().startswith("<article")  # só a folha, sem a página em volta
    assert 0 <= corpo["score"] <= 100
    assert f'data-ats-score="{corpo["score"]}"' in corpo["ats"]

    assert dict(db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,))) == antes


def test_nota_ao_vivo_cai_ao_escolher_duas_colunas(client, perfil):
    resume_id = _novo_curriculo(client)
    # resumo escrito de verdade: com o [preencher] do rascunho a nota fica travada nos dois casos
    resumo = "Desenvolvedora back-end com projetos publicados em Python, FastAPI e PostgreSQL."
    uma = client.post(f"/curriculos/{resume_id}/ao-vivo",
                      data=_formulario(resume_id, summary=resumo)).json()
    duas = client.post(f"/curriculos/{resume_id}/ao-vivo",
                       data=_formulario(resume_id, summary=resumo, template="designer")).json()
    assert duas["score"] < uma["score"]
    assert "usa duas colunas" in duas["ats"]


def test_folha_ao_vivo_escapa_o_que_foi_digitado(client, perfil):
    resume_id = _novo_curriculo(client)
    corpo = client.post(f"/curriculos/{resume_id}/ao-vivo",
                        data=_formulario(resume_id, summary="<script>alert(1)</script>")).json()
    assert "<script>" not in corpo["sheet"]
    assert "&lt;script&gt;" in corpo["sheet"]


def test_folha_ao_vivo_de_curriculo_inexistente_ou_pdf_devolve_404(client, perfil):
    assert client.post("/curriculos/9999/ao-vivo", data={}).status_code == 404
    envio = client.post(
        "/curriculos/arquivo", data={"name": "CV"},
        files={"arquivo": ("cv.pdf", _pdf_bytes("Ana Ribeiro"), "application/pdf")},
        follow_redirects=False,
    )
    pdf_id = int(envio.headers["location"].split("/curriculos/")[1].split("?")[0])
    assert client.post(f"/curriculos/{pdf_id}/ao-vivo", data={}).status_code == 404


def test_bloco_adicionado_na_oficina_e_salvo_e_o_vazio_e_descartado(client, perfil):
    resume_id = _novo_curriculo(client)
    form = _formulario(resume_id)
    form["exp_indice"] = ["nabc", "nvazio"]
    form["exp_incluir"] = ["nabc", "nvazio"]
    form.update({
        "exp_role_nabc": "Estagiária", "exp_org_nabc": "Acme", "exp_period_nabc": "2025 – atual",
        "exp_bullets_nabc": "Reduzi o tempo de build de 9 para 3 minutos",
        "exp_role_nvazio": "", "exp_org_nvazio": "", "exp_period_nvazio": "", "exp_bullets_nvazio": "",
    })
    client.post(f"/curriculos/{resume_id}", data=form, follow_redirects=False)
    salvo = db.loads(db.one("SELECT data FROM resumes WHERE id = ?", (resume_id,))["data"], {})
    assert salvo["experience"] == [{
        "role": "Estagiária", "org": "Acme", "period": "2025 – atual",
        "bullets": ["Reduzi o tempo de build de 9 para 3 minutos"],
    }]
    assert db.get_profile()["experience"] == []  # o Perfil continua como estava


def test_salvar_e_gerar_pdf_leva_para_a_folha(client, perfil):
    resume_id = _novo_curriculo(client)
    resposta = client.post(f"/curriculos/{resume_id}",
                           data=_formulario(resume_id, depois="imprimir"), follow_redirects=False)
    assert resposta.headers["location"] == f"/curriculos/{resume_id}/imprimir"


def test_duplicar_cria_documento_proprio(client, perfil):
    original = _novo_curriculo(client, template="harvard", lang="en")
    client.post(f"/curriculos/{original}",
                data=_formulario(original, summary="Texto lapidado à mão."), follow_redirects=False)

    resposta = client.post(f"/curriculos/{original}/derivar", follow_redirects=False)
    copia = int(resposta.headers["location"].split("/curriculos/")[1].split("?")[0])
    assert copia != original
    linha = db.one("SELECT * FROM resumes WHERE id = ?", (copia,))
    assert (linha["parent_id"], linha["template"], linha["lang"]) == (original, "harvard", "en")
    assert linha["name"] == "CV (cópia)"
    assert db.loads(linha["data"], {})["summary"] == "Texto lapidado à mão."

    # mexer na cópia não mexe no original
    client.post(f"/curriculos/{copia}", data=_formulario(copia, summary="Outro texto."), follow_redirects=False)
    assert db.loads(db.one("SELECT data FROM resumes WHERE id = ?", (original,))["data"], {})["summary"] \
        == "Texto lapidado à mão."
    assert "criado a partir de" in client.get(f"/curriculos/{copia}").text


def test_derivar_para_uma_vaga_reordena_sem_tocar_no_texto(client, com_vagas, perfil):
    original = _novo_curriculo(client)
    client.post(f"/curriculos/{original}",
                data=_formulario(original, summary="Texto lapidado à mão."), follow_redirects=False)
    job = dict(db.query("SELECT * FROM jobs ORDER BY score DESC LIMIT 1")[0])

    resposta = client.post(f"/curriculos/{original}/derivar",
                           data={"nova_vaga": str(job["id"])}, follow_redirects=False)
    copia = int(resposta.headers["location"].split("/curriculos/")[1].split("?")[0])
    linha = db.one("SELECT * FROM resumes WHERE id = ?", (copia,))
    data = db.loads(linha["data"], {})

    assert linha["job_id"] == job["id"]
    assert linha["name"].startswith(job["title"])
    assert data["summary"] == "Texto lapidado à mão."
    assert data["target"]["title"] == job["title"]
    assert data["headline"] == "Desenvolvedora back-end júnior"  # o cargo fica: quem decide é você
    destaque = data["highlight_skills"]
    assert data["skills"][: len(destaque)] == destaque
    assert sorted(data["skills"]) == sorted(perfil["skills"])
    assert job["company"] in linha["letter"]
    # e o original segue sem vaga
    assert db.one("SELECT job_id FROM resumes WHERE id = ?", (original,))["job_id"] is None


def test_derivar_leva_o_que_esta_na_tela_e_nao_foi_salvo(client, perfil):
    original = _novo_curriculo(client)
    form = _formulario(original, summary="Digitado e ainda não salvo.", novo_nome="Versão B")
    resposta = client.post(f"/curriculos/{original}/derivar", data=form, follow_redirects=False)
    copia = int(resposta.headers["location"].split("/curriculos/")[1].split("?")[0])
    linha = db.one("SELECT * FROM resumes WHERE id = ?", (copia,))
    assert linha["name"] == "Versão B"
    assert db.loads(linha["data"], {})["summary"] == "Digitado e ainda não salvo."


def test_derivar_de_pdf_e_recusado(client, perfil):
    envio = client.post(
        "/curriculos/arquivo", data={"name": "CV"},
        files={"arquivo": ("cv.pdf", _pdf_bytes("Ana Ribeiro"), "application/pdf")},
        follow_redirects=False,
    )
    pdf_id = int(envio.headers["location"].split("/curriculos/")[1].split("?")[0])
    client.post(f"/curriculos/{pdf_id}/derivar", follow_redirects=False)
    assert db.one("SELECT COUNT(*) AS n FROM resumes")["n"] == 1


def test_excluir_o_original_nao_leva_a_copia(client, perfil):
    original = _novo_curriculo(client)
    resposta = client.post(f"/curriculos/{original}/derivar", follow_redirects=False)
    copia = int(resposta.headers["location"].split("/curriculos/")[1].split("?")[0])
    client.post(f"/curriculos/{original}/excluir", follow_redirects=False)
    assert db.one("SELECT parent_id FROM resumes WHERE id = ?", (copia,))["parent_id"] is None
    assert client.get(f"/curriculos/{copia}").status_code == 200
    assert client.get("/curriculos").status_code == 200


def test_retarget_nao_altera_a_origem_e_mede_o_que_falta_contra_o_perfil(perfil):
    origem = resume_mod.build(perfil, None)
    origem["skills"] = ["sql", "python"]  # docker desmarcado neste currículo
    origem["ats_ai"] = {"text": "parecer antigo"}
    copia_da_origem = db.loads(db.dumps(origem), {})
    vaga = {"title": "Dev", "company": "X", "description": "Python, Docker, Kubernetes", "tags": []}

    novo = resume_mod.retarget(origem, vaga, perfil["skills"])

    assert origem == copia_da_origem
    assert novo["skills"] == ["python", "sql"]
    assert novo["missing_skills"] == ["kubernetes"]  # docker está no Perfil: não é "falta"
    assert "ats_ai" not in novo


def test_lista_mostra_a_nota_ats_de_cada_curriculo(client, perfil):
    resume_id = _novo_curriculo(client)
    linha = resume_dict_de(resume_id)
    nota = ats.check(linha["data"], lang="pt")["score"]
    pagina = client.get("/curriculos").text
    assert f'class="ats-badge g-{ats.grade(nota)[0]}"' in pagina
    assert f">{nota}<span" in pagina


def resume_dict_de(resume_id: int) -> dict:
    linha = dict(db.one("SELECT * FROM resumes WHERE id = ?", (resume_id,)))
    linha["data"] = db.loads(linha["data"], {})
    return linha


def test_oficina_mostra_nota_e_sugestoes_sem_ia(client, perfil, monkeypatch):
    from farol import ai

    def proibido(*args, **kwargs):
        raise AssertionError("o verificador de regras não pode chamar modelo nenhum")

    monkeypatch.setattr(ai, "complete", proibido)
    resume_id = _novo_curriculo(client)
    pagina = client.get(f"/curriculos/{resume_id}").text
    assert "data-ats-score=" in pagina
    assert "O que mais devolve ponto" in pagina
    assert "Verificar com IA" not in pagina          # sem assistente, o botão não existe
    assert "ligue um assistente" in pagina           # e a tela diz como ligar


def test_pdf_enviado_ganha_nota_ats_e_ela_aparece_na_lista(client, perfil):
    envio = client.post(
        "/curriculos/arquivo", data={"name": "CV pronto"},
        files={"arquivo": ("cv.pdf", _pdf_bytes("Ana Ribeiro", "ana@exemplo.com", "Python e Docker"),
                           "application/pdf")},
        follow_redirects=False,
    )
    pdf_id = int(envio.headers["location"].split("/curriculos/")[1].split("?")[0])
    assert "data-ats-score=" in client.get(f"/curriculos/{pdf_id}").text
    nota = db.one("SELECT ats_score FROM resumes WHERE id = ?", (pdf_id,))["ats_score"]
    assert isinstance(nota, int)
    assert f">{nota}<span" in client.get("/curriculos").text


def test_verificacao_com_ia_sem_assistente_avisa_e_nao_chama_nada(client, perfil, monkeypatch):
    from farol import ai

    monkeypatch.setattr(ai, "complete", lambda *a, **k: pytest.fail("não há assistente configurado"))
    resume_id = _novo_curriculo(client)
    resposta = client.post(f"/curriculos/{resume_id}/ats-ia", follow_redirects=False)
    assert "tone=warn" in resposta.headers["location"]
    assert "ats_ai" not in resume_dict_de(resume_id)["data"]


def test_verificacao_com_ia_complementa_as_regras_e_guarda_o_parecer(client, perfil, monkeypatch):
    from farol import ai

    db.set_setting("ai_provider", "local")
    db.set_setting("local_ai_model", "qwen2.5:7b")
    pedidos: list[str] = []

    def modelo(prompt: str, max_tokens: int = 0) -> str:
        pedidos.append(prompt)
        return "Marcadores fracos:\n- Subi com Docker → Publiquei a imagem em [preencher]"

    monkeypatch.setattr(ai, "complete", modelo)
    resume_id = _novo_curriculo(client)

    resposta = client.post(f"/curriculos/{resume_id}/ats-ia",
                           data=_formulario(resume_id, headline="Dev Python"), follow_redirects=False)
    assert "tone=warn" not in resposta.headers["location"]
    nota = ats.check(resume_dict_de(resume_id)["data"])["score"]

    # o modelo recebe o que as regras já apontaram e a ordem de não dar nota
    assert len(pedidos) == 1
    assert f"nota {nota}/100" in pedidos[0]
    assert "Não repita esses pontos e não dê nota" in pedidos[0]
    assert "Nada por preencher" in pedidos[0]

    salvo = resume_dict_de(resume_id)["data"]
    assert salvo["headline"] == "Dev Python"  # a edição na tela foi gravada antes
    assert salvo["ats_ai"]["by"] == "Modelo local"
    assert salvo["ats_ai"]["model"] == "qwen2.5:7b"
    pagina = client.get(f"/curriculos/{resume_id}").text
    assert "Publiquei a imagem em [preencher]" in pagina
    assert "Refazer a verificação com IA" in pagina
    # o parecer não entra na folha nem volta para o modelo na próxima rodada
    assert "Marcadores fracos" not in client.get(f"/curriculos/{resume_id}/imprimir").text
    client.post(f"/curriculos/{resume_id}/ats-ia", follow_redirects=False)
    assert "Publiquei a imagem em" not in pedidos[1]


def test_falha_da_ia_na_verificacao_vira_aviso(client, perfil, monkeypatch):
    from farol import ai

    db.set_setting("ai_provider", "local")
    db.set_setting("local_ai_model", "qwen2.5:7b")

    def fora_do_ar(prompt: str, max_tokens: int = 0) -> str:
        raise RuntimeError("servidor local não respondeu")

    monkeypatch.setattr(ai, "complete", fora_do_ar)
    resume_id = _novo_curriculo(client)
    resposta = client.post(f"/curriculos/{resume_id}/ats-ia", follow_redirects=False)
    assert resposta.status_code == 303
    assert "tone=warn" in resposta.headers["location"]
    assert client.get(f"/curriculos/{resume_id}").status_code == 200


def test_banco_antigo_ganha_as_colunas_da_oficina(perfil):
    conn = db.connect()
    conn.execute("ALTER TABLE resumes DROP COLUMN parent_id")
    conn.execute("ALTER TABLE resumes DROP COLUMN ats_score")
    conn.commit()
    db.bootstrap()
    colunas = {row["name"] for row in db.query("PRAGMA table_info(resumes)")}
    assert {"parent_id", "ats_score"} <= colunas
