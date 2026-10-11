"""O verificador ATS: nota reproduzível, cada checagem isolada, nenhuma sugestão desonesta."""

import copy

import pytest

from farol import ats

VAGA = {
    "title": "Junior Python Developer",
    "company": "Northwind",
    "description": "We use Python, FastAPI, PostgreSQL, Docker and AWS. Kubernetes is a plus.",
    "tags": ["python", "backend"],
}


@pytest.fixture
def bom() -> dict:
    """Currículo sem nada a corrigir — a base de onde cada teste tira uma coisa só."""
    return {
        "name": "Ana Ribeiro",
        "headline": "Desenvolvedora Python júnior",
        "email": "ana@exemplo.com",
        "phone": "+55 41 90000-0000",
        "city": "Curitiba, PR",
        "links": [
            {"label": "LinkedIn", "url": "https://linkedin.com/in/ana"},
            {"label": "GitHub", "url": "https://github.com/ana"},
        ],
        "summary": (
            "Desenvolvedora back-end com dois anos de projetos em Python e FastAPI. Publiquei três "
            "APIs com PostgreSQL e Docker, todas com testes automatizados e pipeline de entrega. "
            "Procuro uma vaga júnior em que possa cuidar de serviços em produção."
        ),
        "skills": ["python", "sql", "docker", "fastapi", "postgresql", "git", "pytest", "linux"],
        "experience": [
            {
                "role": "Estagiária de desenvolvimento", "org": "Acme", "period": "mar 2025 – atual",
                "bullets": [
                    "Reduzi o tempo de resposta da API de pedidos de 800 ms para 200 ms com cache em Redis",
                    "Automatizei o deploy com GitHub Actions, cortando a entrega de 40 para 6 minutos",
                    "Escrevi os testes de integração do módulo de pagamento com pytest",
                ],
            }
        ],
        "projects": [
            {
                "name": "API de biblioteca", "url": "https://github.com/ana/api",
                "stack": "FastAPI, PostgreSQL",
                "bullets": [
                    "Desenvolvi uma API REST em FastAPI com 24 rotas e autenticação por token",
                    "Cobri 80% do código com pytest e publiquei a imagem Docker no registro",
                    "Modelei o banco PostgreSQL com migrações versionadas",
                ],
            },
            {
                "name": "Coletor de vagas", "url": "https://github.com/ana/coletor",
                "stack": "Python, SQLite",
                "bullets": [
                    "Construí um coletor em Python que lê 6 portais e deduplica 2 mil vagas por semana",
                    "Publiquei o pacote com instalador para Linux, macOS e Windows",
                ],
            },
        ],
        "education": [{"course": "Sistemas de Informação", "school": "UFPR", "period": "2023 – 2026", "note": ""}],
        "languages": [{"name": "Inglês", "level": "B2"}],
    }


def _checks(report: dict) -> dict[str, dict]:
    return {c["key"]: c for cat in report["categories"] for c in cat["checks"]}


def _status(report: dict, key: str) -> str:
    return _checks(report)[key]["status"]


# ------------------------------------------------------------------- a nota


def test_curriculo_bom_tira_nota_alta_e_nao_tem_pendencia(bom):
    report = ats.check(bom)
    assert report["score"] >= 95, report["fixes"]
    assert report["grade"] == "forte"
    assert report["fixes"] == []


def test_mesma_entrada_mesma_nota(bom):
    primeira = ats.check(copy.deepcopy(bom), job=VAGA)
    segunda = ats.check(copy.deepcopy(bom), job=VAGA)
    assert primeira == segunda


def test_verificar_nao_altera_o_curriculo(bom):
    antes = copy.deepcopy(bom)
    ats.check(bom, job=VAGA)
    assert bom == antes


def test_curriculo_vazio_nao_quebra_e_tira_nota_baixa():
    report = ats.check({})
    assert 0 <= report["score"] < 30
    assert report["grade"] == "fraco"
    assert report["fixes"]


@pytest.mark.parametrize("lixo", [
    {"experience": None, "projects": None, "links": None, "skills": None},
    {"experience": [{"bullets": None}], "projects": [{}], "education": [{}], "languages": [{}]},
    {"experience": ["texto solto"], "links": ["x"], "name": None, "email": 3},
])
def test_dado_malformado_nao_derruba(lixo):
    report = ats.check(lixo)
    assert 0 <= report["score"] <= 100


def test_nota_fica_entre_zero_e_cem_e_categorias_tem_peso(bom):
    report = ats.check(bom, job=VAGA)
    assert 0 <= report["score"] <= 100
    assert [c["key"] for c in report["categories"]] == ["formato", "contato", "estrutura", "conteudo", "vaga"]
    assert all(0 <= c["score"] <= 100 for c in report["categories"])


def test_sem_vaga_a_nota_ainda_vai_a_cem(bom):
    report = ats.check(bom)
    assert "vaga" not in [c["key"] for c in report["categories"]]
    assert report["score"] == 100


def test_pendencias_vem_ordenadas_pelo_que_mais_devolve_ponto(bom):
    bom["email"] = ""
    bom["city"] = ""
    fixes = ats.check(bom)["fixes"]
    assert [f["key"] for f in fixes] == ["email", "cidade"]
    assert fixes[0]["gain"] >= fixes[1]["gain"] >= 1


def test_entre_pendencias_comuns_vence_a_que_devolve_mais_ponto(bom):
    bom["city"] = ""                                   # contato, peso pequeno
    for item in bom["experience"] + bom["projects"]:   # conteúdo, peso grande
        item["bullets"] = [f"Responsável por tarefa {i} com 3 pessoas" for i in range(3)]
    chaves = [f["key"] for f in ats.check(bom)["fixes"]]
    assert chaves.index("verbos") < chaves.index("cidade")


@pytest.mark.parametrize("estrago", [
    lambda cv: cv.update(email=""),
    lambda cv: cv.update(summary=cv["summary"] + " [preencher]"),
    lambda cv: cv.update(experience=[], projects=[]),
])
def test_falha_grave_trava_a_nota_por_melhor_que_seja_o_resto(bom, estrago):
    estrago(bom)
    report = ats.check(bom)
    assert report["score"] <= ats.BLOCKED_CAP
    assert report["grade"] not in {"forte", "bom"}
    assert report["blocked"]
    assert report["fixes"][0]["blocker"] is True


def test_curriculo_sem_falha_grave_nao_tem_trava(bom):
    bom["phone"] = ""
    report = ats.check(bom)
    assert report["blocked"] == []
    assert report["score"] > ats.BLOCKED_CAP


def test_rascunho_recem_montado_do_perfil_nao_sai_como_pronto():
    """O caso que mais acontece: perfil magro, resumo ainda com o lembrete do app."""
    rascunho = {
        "name": "Ana Ribeiro", "headline": "Desenvolvedora back-end júnior", "email": "ana@exemplo.com",
        "phone": "41 90000-0000", "city": "Curitiba, PR",
        "links": [{"label": "GitHub", "url": "https://github.com/ana"}],
        "summary": "Profissional em início de carreira. [preencher]: escreva aqui duas linhas.",
        "skills": ["python", "sql", "docker", "fastapi", "postgresql"],
        "experience": [],
        "projects": [{"name": "API de biblioteca", "url": "https://github.com/ana/api",
                      "stack": "FastAPI", "bullets": ["Cobri 80% do código com pytest", "Subi com Docker"]}],
        "education": [{"course": "Sistemas", "school": "UFPR", "period": "2023–2026"}],
        "languages": [{"name": "Inglês", "level": "B2"}],
    }
    report = ats.check(rascunho)
    assert report["grade"] in {"regular", "fraco"}
    assert {"pendencias", "marcadores", "tamanho"} <= {fix["key"] for fix in report["fixes"]}


def test_faixas_da_nota():
    assert ats.grade(100)[0] == "forte"
    assert ats.grade(85)[0] == "forte"
    assert ats.grade(84)[0] == "bom"
    assert ats.grade(70)[0] == "bom"
    assert ats.grade(69)[0] == "regular"
    assert ats.grade(50)[0] == "regular"
    assert ats.grade(49)[0] == "fraco"
    assert ats.grade(0)[0] == "fraco"


# ------------------------------------------------------------------ formato


def test_duas_colunas_reprova_no_formato(bom):
    report = ats.check(bom, layout="duas-colunas", template_label="Designer")
    assert _status(report, "layout") == "fail"
    assert "Designer" in _checks(report)["layout"]["detail"]
    assert report["score"] < ats.check(bom)["score"]


def test_emoji_e_seta_viram_aviso(bom):
    bom["projects"][0]["bullets"][0] = "🚀 Desenvolvi uma API REST com 24 rotas"
    assert _status(ats.check(bom), "caracteres") == "warn"


def test_marcador_padrao_e_travessao_nao_sao_simbolo(bom):
    bom["summary"] += " Entrego • testo — e documento."
    assert _status(ats.check(bom), "caracteres") == "ok"


def test_periodo_sem_ano_e_apontado(bom):
    bom["experience"][0]["period"] = "atual"
    report = ats.check(bom)
    assert _status(report, "datas") == "warn"
    assert "Acme" in _checks(report)["datas"]["detail"]


def test_maioria_sem_ano_reprova(bom):
    bom["experience"][0]["period"] = ""
    bom["education"][0]["period"] = "cursando"
    assert _status(ats.check(bom), "datas") == "fail"


def test_link_quebrado_e_apontado(bom):
    bom["links"].append({"label": "site", "url": "meu portfolio"})
    assert _status(ats.check(bom), "links") == "warn"


# ------------------------------------------------------------------ contato


@pytest.mark.parametrize("email", ["", "ana@", "ana.exemplo.com", "[preencher]", "ana @exemplo.com"])
def test_email_invalido_reprova(bom, email):
    bom["email"] = email
    assert _status(ats.check(bom), "email") == "fail"


@pytest.mark.parametrize("email", ["ana@exemplo.com", "a.b+c@sub.dominio.com.br", "x_y@d-e.io"])
def test_email_valido_passa(bom, email):
    bom["email"] = email
    assert _status(ats.check(bom), "email") == "ok"


def test_telefone_curto_e_ausente_avisam(bom):
    bom["phone"] = "9000"
    assert _status(ats.check(bom), "telefone") == "warn"
    bom["phone"] = ""
    assert _status(ats.check(bom), "telefone") == "warn"


def test_sem_linkedin_e_sem_github_avisam(bom):
    bom["links"] = []
    report = ats.check(bom)
    assert _status(report, "linkedin") == "warn"
    assert _status(report, "codigo") == "warn"


# ---------------------------------------------------------------- estrutura


def test_rascunho_do_app_no_resumo_reprova(bom):
    bom["summary"] = "Profissional com foco em back-end. [preencher]: escreva aqui duas linhas."
    report = ats.check(bom)
    assert _status(report, "resumo") == "fail"
    assert _status(report, "pendencias") == "fail"


def test_resumo_curto_e_longo_avisam(bom):
    bom["summary"] = "Desenvolvedora Python."
    assert _status(ats.check(bom), "resumo") == "warn"
    bom["summary"] = "palavra " * 130
    assert _status(ats.check(bom), "resumo") == "warn"


def test_sem_experiencia_nem_projeto_reprova(bom):
    bom["experience"] = []
    bom["projects"] = []
    assert _status(ats.check(bom), "experiencia") == "fail"


def test_so_projetos_vale_como_experiencia(bom):
    bom["experience"] = []
    assert _status(ats.check(bom), "experiencia") == "ok"


@pytest.mark.parametrize(("quantas", "esperado"), [(2, "fail"), (4, "warn"), (8, "ok"), (31, "warn")])
def test_quantidade_de_competencias(bom, quantas, esperado):
    bom["skills"] = [f"skill{i}" for i in range(quantas)]
    assert _status(ats.check(bom), "competencias") == esperado


def test_curriculo_longo_demais_avisa(bom):
    bom["experience"][0]["bullets"] = ["Desenvolvi " + "muita coisa relevante " * 8 + "em 2025"] * 40
    assert _status(ats.check(bom), "tamanho") in {"warn", "fail"}


# ----------------------------------------------------------------- conteúdo


@pytest.mark.parametrize("marcador", [
    "Desenvolvi a API de pedidos", "Reduzi o tempo de build", "Subi com Docker", "Cobri 80% do código",
    "Built the orders API", "Spearheaded the migration", "Led a team of 3", "Criou o painel de métricas",
    "Otimizei consultas SQL",
])
def test_verbo_de_acao_e_reconhecido(marcador):
    assert ats.is_action_start(marcador)


@pytest.mark.parametrize("marcador", [
    "Responsável por manter a API", "Responsible for the orders API", "Participei de reuniões",
    "API de pedidos em FastAPI", "Ajudei o time com testes", "Worked on the frontend",
    "Conhecimento em Python", "", "80% de cobertura",
])
def test_comeco_fraco_nao_passa_por_verbo(marcador):
    assert not ats.is_action_start(marcador)


def test_marcadores_sem_verbo_reprovam_e_citam_o_trecho(bom):
    for item in bom["experience"] + bom["projects"]:
        item["bullets"] = [f"Responsável por tarefa {i} do time" for i, _ in enumerate(item["bullets"])]
    report = ats.check(bom)
    assert _status(report, "verbos") == "fail"
    assert "Responsável por tarefa" in _checks(report)["verbos"]["detail"]


def test_marcadores_sem_numero_reprovam(bom):
    for item in bom["experience"] + bom["projects"]:
        item["bullets"] = ["Desenvolvi a interface de cadastro", "Escrevi a documentação do módulo"]
    assert _status(ats.check(bom), "numeros") == "fail"


def test_um_terco_com_numero_basta(bom):
    bom["experience"] = []
    bom["projects"][0]["bullets"] = ["Desenvolvi 3 rotas novas", "Escrevi a documentação", "Corrigi o cadastro"]
    bom["projects"][1]["bullets"] = ["Publiquei 2 versões", "Organizei o repositório", "Testei o instalador"]
    assert _status(ats.check(bom), "numeros") == "ok"


def test_cliche_e_apontado_pelo_nome(bom):
    bom["summary"] += " Sou proativa e apaixonada por tecnologia."
    report = ats.check(bom)
    assert _status(report, "cliches") == "warn"
    assert "proativa" in _checks(report)["cliches"]["detail"]


def test_cliche_nao_casa_no_meio_de_palavra(bom):
    bom["summary"] += " Trabalhei com o banco Guruvayur."
    assert _status(ats.check(bom), "cliches") == "ok"


def test_curriculo_em_ingles_com_texto_em_portugues_reprova(bom):
    report = ats.check(bom, lang="en")
    assert _status(report, "idioma") == "fail"
    assert "português" in _checks(report)["idioma"]["detail"]


def test_curriculo_em_ingles_com_texto_em_ingles_passa(bom):
    bom["summary"] = "Back-end developer with two years of projects in Python and FastAPI for the web."
    for item in bom["experience"] + bom["projects"]:
        item["bullets"] = ["Built the orders API with 24 routes and token auth for the team",
                           "Reduced the response time from 800 ms to 200 ms with a cache in Redis"]
    assert _status(ats.check(bom, lang="en"), "idioma") == "ok"


def test_verbo_repetido_avisa(bom):
    for item in bom["experience"] + bom["projects"]:
        item["bullets"] = [f"Desenvolvi a parte {i} do sistema" for i in range(3)]
    assert _status(ats.check(bom), "repeticao") == "warn"


def test_item_com_um_marcador_so_avisa(bom):
    bom["projects"][1]["bullets"] = ["Construí um coletor em Python que lê 6 portais"]
    report = ats.check(bom)
    assert _status(report, "marcadores") == "warn"
    assert "Coletor de vagas" in _checks(report)["marcadores"]["detail"]


# --------------------------------------------------------------------- vaga


def test_aderencia_lista_o_que_casa_e_o_que_falta(bom):
    report = ats.check(bom, job=VAGA)
    assert report["keywords"]["matched"] == ["python", "fastapi", "postgresql", "docker"]
    assert report["keywords"]["missing"] == ["kubernetes", "aws"]
    assert _status(report, "cobertura") == "warn"


def test_sugestao_de_aderencia_nunca_manda_inventar(bom):
    bom["skills"] = ["html", "css", "git", "figma", "react", "sass"]
    for item in bom["experience"] + bom["projects"]:
        item["bullets"] = ["Desenvolvi 3 telas em React", "Publiquei 2 versões do site"]
        item["stack"] = "React"
    bom["summary"] = "Desenvolvedora front-end com projetos em React. " * 4
    cobertura = _checks(ats.check(bom, job=VAGA))["cobertura"]
    assert cobertura["status"] == "fail"
    assert "só o que você já usou" in cobertura["fix"]
    assert "O que você não sabe não entra" in cobertura["fix"]


def test_termo_so_na_lista_de_competencias_pede_contexto(bom):
    bom["summary"] = "Desenvolvedora de software em início de carreira, com projetos publicados e testados. " * 2
    for item in bom["experience"] + bom["projects"]:
        item["bullets"] = ["Desenvolvi 3 rotas novas", "Publiquei 2 versões"]
    assert _status(ats.check(bom, job=VAGA), "contexto") == "warn"


def test_cargo_da_vaga_no_cabecalho(bom):
    assert _status(ats.check(bom, job=VAGA), "titulo") == "ok"
    bom["headline"] = "Analista de suporte"
    bom["summary"] = "Atendo chamados e documento soluções para o time de operações da empresa. " * 2
    assert _status(ats.check(bom, job=VAGA), "titulo") == "warn"


def test_vaga_sem_termo_tecnico_nao_inventa_cobertura(bom):
    vaga = {"title": "Assistente", "company": "X", "description": "Atendimento ao público.", "tags": []}
    report = ats.check(bom, job=vaga)
    assert "cobertura" not in _checks(report)
    assert report["keywords"] == {"matched": [], "missing": []}


def test_tags_da_vaga_gravadas_como_json_sao_lidas(bom):
    vaga = dict(VAGA, tags='["kubernetes"]', description="")
    assert "kubernetes" in ats.check(bom, job=vaga)["keywords"]["missing"]


# ---------------------------------------------------------------------- PDF

PDF_BOM = """Ana Ribeiro
Desenvolvedora Python júnior
ana@exemplo.com | +55 41 90000-0000 | linkedin.com/in/ana | github.com/ana

Resumo
Desenvolvedora back-end com dois anos de projetos em Python e FastAPI, com PostgreSQL e Docker.

Experiência
Estagiária de desenvolvimento — Acme (mar 2025 – atual)
• Reduzi o tempo de resposta da API de pedidos de 800 ms para 200 ms com cache em Redis
• Automatizei o deploy com GitHub Actions, cortando a entrega de 40 para 6 minutos
• Escrevi os testes de integração do módulo de pagamento com pytest

Projetos
API de biblioteca
• Desenvolvi uma API REST em FastAPI com 24 rotas e autenticação por token
• Cobri 80% do código com pytest e publiquei a imagem Docker no registro

Formação
Sistemas de Informação — UFPR (2023 – 2026)

Competências
Python, SQL, Docker, FastAPI, PostgreSQL, Git, pytest, Linux
"""


def test_pdf_bem_formado_tira_nota_alta():
    report = ats.check_text(PDF_BOM)
    assert report["structured"] is False
    assert report["score"] >= 85, report["fixes"]
    assert _status(report, "titulos") == "ok"
    assert _status(report, "email") == "ok"


def test_pdf_sem_texto_tira_zero_e_explica():
    report = ats.check_text("")
    assert report["score"] == 0
    assert [f["key"] for f in report["fixes"]] == ["texto"]


def test_pdf_sem_titulo_de_secao_reprova_no_formato():
    texto = PDF_BOM.replace("Experiência\n", "Minha trajetória\n").replace("Formação\n", "Onde estudei\n") \
                   .replace("Competências\n", "O que eu sei\n").replace("Projetos\n", "Coisas que fiz\n")
    assert _status(ats.check_text(texto), "titulos") == "fail"


def test_pdf_com_vaga_mede_aderencia():
    report = ats.check_text(PDF_BOM, job=VAGA)
    assert report["keywords"]["missing"] == ["kubernetes", "aws"]
