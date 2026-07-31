from datetime import datetime, timedelta, timezone

from farol import db, scoring, skills

PERFIL = {
    "skills": ["python", "sql", "docker", "fastapi", "postgresql"],
    "seniority": "junior",
}
AJUSTES = dict(db.DEFAULT_SETTINGS)


def recente(dias=1):
    return (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()


def test_vaga_ideal_pontua_alto():
    job = {
        "title": "Junior Python Developer",
        "company": "Northwind",
        "description": "Python, FastAPI, PostgreSQL e Docker. Testes com pytest.",
        "location": "Worldwide",
        "remote": 1,
        "tags": ["python", "fastapi"],
        "published_at": recente(),
    }
    result = scoring.score_job(job, PERFIL, AJUSTES)
    assert result["score"] >= 75
    assert "python" in result["matched"]
    assert scoring.label(result["score"]) == "forte"


def test_vaga_senior_afunda_para_quem_busca_junior():
    job = {
        "title": "Senior Python Engineer",
        "description": "Python, FastAPI. 8+ years of experience required.",
        "location": "Worldwide",
        "remote": 1,
        "tags": [],
        "published_at": recente(),
    }
    result = scoring.score_job(job, PERFIL, AJUSTES)
    senioridade = next(c for c in result["components"] if c["label"] == "Senioridade")
    assert senioridade["points"] == 0
    assert "senioridade acima do seu alvo" in result["flags"]


def test_restricao_geografica_zera_regiao():
    job = {
        "title": "Junior Developer",
        "description": "Python. US only, must be located in the United States.",
        "location": "United States",
        "remote": 1,
        "tags": [],
        "published_at": recente(),
    }
    result = scoring.score_job(job, PERFIL, AJUSTES)
    regiao = next(c for c in result["components"] if c["label"] == "Região")
    assert regiao["points"] == 0
    assert "restrição geográfica" in result["flags"]


def test_vaga_antiga_perde_recencia():
    job = {
        "title": "Junior Python Developer",
        "description": "Python e SQL.",
        "location": "Brazil",
        "remote": 1,
        "tags": [],
        "published_at": recente(dias=60),
    }
    result = scoring.score_job(job, PERFIL, AJUSTES)
    recencia = next(c for c in result["components"] if c["label"] == "Recência")
    assert recencia["points"] == 0
    assert "vaga antiga" in result["flags"]


def test_termo_excluido_no_titulo_limita_a_nota():
    job = {
        "title": "Tech Lead Python",
        "description": "Python, SQL, Docker, FastAPI, PostgreSQL.",
        "location": "Brazil",
        "remote": 1,
        "tags": [],
        "published_at": recente(),
    }
    result = scoring.score_job(job, PERFIL, AJUSTES)
    assert result["score"] <= 25


def test_soma_dos_componentes_bate_com_o_total():
    job = {
        "title": "Junior Data Analyst",
        "description": "SQL e Power BI.",
        "location": "Brazil",
        "remote": 1,
        "tags": [],
        "published_at": recente(),
    }
    result = scoring.score_job(job, PERFIL, AJUSTES)
    assert result["score"] == sum(c["points"] for c in result["components"])
    assert all(0 <= c["points"] <= c["max"] for c in result["components"])


def test_extracao_de_skills_reconhece_apelidos():
    found = skills.extract("Experiência com JS, TS, k8s e Postgres. Inglês avançado.")
    assert {"javascript", "typescript", "kubernetes", "postgresql", "inglês"} <= set(found)


def test_lista_de_skills_do_usuario_vira_canonica():
    assert skills.parse_skill_list("JS, postgres , k8s") == ["javascript", "postgresql", "kubernetes"]


def test_modo_hibrido_detectado_no_texto():
    job = {"title": "Dev júnior", "location": "São Paulo (modelo híbrido)", "remote": 0}
    assert scoring.work_mode(job) == "hibrido"


def test_modo_remoto_quando_flag_remote_e_sem_marcador():
    job = {"title": "Dev júnior", "location": "Worldwide", "remote": 1}
    assert scoring.work_mode(job) == "remoto"


def test_modo_presencial_quando_remote_falso_e_sem_marcador():
    job = {"title": "Dev júnior", "location": "Berlin", "remote": 0}
    assert scoring.work_mode(job) == "presencial"


def test_salario_extrai_faixa_do_texto_formatado():
    assert scoring.salary_range("US$ 80.000–120.000/ano") == (80000, 120000, "USD")


def test_salario_extrai_faixa_de_texto_cru_com_moeda():
    assert scoring.salary_range("USD 40.000 - 60.000") == (40000, 60000, "USD")


def test_salario_um_numero_vira_faixa_igual():
    assert scoring.salary_range("US$ 90.000/ano") == (90000, 90000, "USD")


def test_salario_sem_numero_reconhecivel_e_none():
    assert scoring.salary_range("Competitive") is None
    assert scoring.salary_range("") is None
    assert scoring.salary_range(None) is None


def test_salario_em_euro_nao_e_tratado_como_dolar():
    assert scoring.salary_range("EUR 50.000 - 70.000") == (50000, 70000, "EUR")
    assert scoring.salary_range("€ 60.000/ano") == (60000, 60000, "EUR")


def test_salario_em_real_nao_cai_no_dolar_pelo_cifrao():
    assert scoring.salary_range("R$ 4.000 - 6.000/mês") == (48000, 72000, "BRL")


def test_salario_mensal_e_normalizado_para_anual():
    assert scoring.salary_range("US$ 5.000/month") == (60000, 60000, "USD")


def test_salario_sem_moeda_declarada_fica_indefinido():
    assert scoring.salary_range("40.000 - 60.000") == (40000, 60000, "")


def test_regiao_classifica_pelo_campo_de_localizacao():
    assert scoring.region({"location": "Brazil", "title": "Dev"}) == "brasil"
    assert scoring.region({"location": "Brazil, Latin America", "title": "Dev"}) == "brasil"
    assert scoring.region({"location": "Latin America", "title": "Dev"}) == "latam"
    assert scoring.region({"location": "Worldwide", "title": "Dev"}) == "mundial"
    assert scoring.region({"location": "Berlin", "title": "Dev"}) == "outros"


def test_regiao_respeita_restricao_explicita_a_outro_pais():
    assert scoring.region({"location": "US only", "title": "Dev"}) == "outros"


def test_regiao_ignora_mencao_solta_na_descricao():
    """'Brazil' citado no corpo do anúncio não transforma vaga de Berlim em vaga BR."""
    job = {"location": "Berlin", "title": "Dev", "description": "Our team spans Brazil and Spain."}
    assert scoring.region(job) == "outros"
