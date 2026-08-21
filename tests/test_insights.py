"""Métricas: contas descritivas sobre o histórico das candidaturas."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from farol import db, insights
from farol.app import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _candidatura(titulo, etapas, inicio_dias_atras=30, passo=3, job_id=None, score=None):
    """Cria uma candidatura com histórico de etapas espaçado no tempo."""
    if score is not None:
        job_id = db.execute(
            "INSERT INTO jobs (source, source_id, fingerprint, title, score) VALUES (?,?,?,?,?)",
            ("teste", titulo, titulo, titulo, score),
        )
    quando = datetime.now() - timedelta(days=inicio_dias_atras)
    app_id = db.execute(
        "INSERT INTO applications (job_id, title, status, applied_at, updated_at) VALUES (?,?,?,?,?)",
        (job_id, titulo, etapas[-1], quando.date().isoformat(),
         quando.isoformat(sep=" ", timespec="seconds")),
    )
    for etapa in etapas:
        db.execute(
            "INSERT INTO events (application_id, kind, note, to_status, created_at) VALUES (?,?,?,?,?)",
            (app_id, "status", f"→ {db.STATUS_LABELS[etapa]}", etapa,
             quando.isoformat(sep=" ", timespec="seconds")),
        )
        quando += timedelta(days=passo)
    return app_id


def test_funil_conta_a_etapa_mais_avancada_e_nao_a_atual():
    """Recusada depois da entrevista chegou à entrevista — é isso que o funil mede."""
    _candidatura("recusada", ["salva", "candidatado", "triagem", "entrevista", "encerrada"])
    _candidatura("parada", ["salva", "candidatado"])

    etapas = {linha["status"]: linha["count"] for linha in insights.funnel()}
    assert etapas["salva"] == 2
    assert etapas["candidatado"] == 2
    assert etapas["triagem"] == 1
    assert etapas["entrevista"] == 1
    assert etapas["oferta"] == 0


def test_funil_traz_a_conversao_de_uma_etapa_para_a_seguinte():
    for i in range(4):
        _candidatura(f"c{i}", ["salva", "candidatado"])
    _candidatura("avancou", ["salva", "candidatado", "triagem"])

    linhas = {linha["status"]: linha for linha in insights.funnel()}
    assert linhas["candidatado"]["step"] == 100
    assert linhas["triagem"]["step"] == 20   # 1 de 5


def test_tempo_entre_etapas_usa_mediana_e_informa_a_amostra():
    _candidatura("a", ["salva", "candidatado"], passo=4)
    _candidatura("b", ["salva", "candidatado"], passo=10)
    _candidatura("c", ["salva", "candidatado"], passo=6)

    primeiro = insights.stage_durations()[0]
    assert primeiro["de"] == "Salvas" and primeiro["para"] == "Candidatado"
    assert primeiro["dias"] == 6
    assert primeiro["amostra"] == 3


def test_etapa_sem_dado_nao_inventa_numero():
    _candidatura("so-salva", ["salva"])
    assert all(passo["dias"] is None for passo in insights.stage_durations())


def test_paradas_lista_candidatura_ativa_esquecida():
    _candidatura("esquecida", ["salva", "candidatado"], inicio_dias_atras=40, passo=0)
    _candidatura("recente", ["salva", "candidatado"], inicio_dias_atras=1, passo=0)
    _candidatura("encerrada", ["salva", "encerrada"], inicio_dias_atras=40, passo=0)

    titulos = [item["title"] for item in insights.stalled(days=10)]
    assert "esquecida" in titulos
    assert "recente" not in titulos
    assert "encerrada" not in titulos     # desfecho não é esquecimento


def test_fit_por_desfecho_exige_os_dois_lados():
    _candidatura("respondeu", ["salva", "candidatado", "triagem"], score=80)
    resultado = insights.fit_by_outcome()
    assert resultado["responderam"] == 80
    assert resultado["confiavel"] is False   # ninguém do outro lado ainda

    for i in range(5):
        _candidatura(f"ignorou{i}", ["salva", "candidatado"], score=50)
    resultado = insights.fit_by_outcome()
    assert resultado["ignoraram"] == 50
    assert resultado["confiavel"] is True


def test_retorno_por_fonte_esconde_percentual_de_amostra_minuscula():
    _candidatura("uma", ["salva", "candidatado", "triagem"], score=70)
    fonte = insights.by_source()[0]
    assert fonte["enviadas"] == 1 and fonte["responderam"] == 1
    assert fonte["taxa"] is None             # 100% de uma candidatura não é taxa


def test_semanas_cobrem_a_janela_inteira_mesmo_sem_movimento():
    semanas = insights.weekly(weeks=6)
    assert len(semanas) == 6
    assert all(linha["enviadas"] == 0 for linha in semanas)


def test_faixa_salarial_ignora_vaga_sem_moeda_reconhecida():
    db.execute("INSERT INTO jobs (source, source_id, fingerprint, title, salary_min, salary_max, "
               "salary_currency) VALUES ('t','1','1','com',50000,90000,'USD')")
    db.execute("INSERT INTO jobs (source, source_id, fingerprint, title, salary_min, salary_max, "
               "salary_currency) VALUES ('t','2','2','sem',10,20,'')")
    linhas = insights.salary_snapshot()
    assert [linha["moeda"] for linha in linhas] == ["USD"]
    assert linhas[0]["max"] == 90000


def test_resumo_sem_candidatura_nenhuma_nao_quebra():
    dados = insights.summary()
    assert dados["total"] == 0
    assert dados["taxa_resposta"] is None
    assert dados["funnel"][0]["count"] == 0


@pytest.mark.parametrize("rota", ["/metricas"])
def test_pagina_de_metricas_responde(client, rota):
    assert client.get(rota).status_code == 200
    _candidatura("uma", ["salva", "candidatado", "triagem"], score=70)
    corpo = client.get(rota).text
    assert "Funil" in corpo and "Tempo entre etapas" in corpo
