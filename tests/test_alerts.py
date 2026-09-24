"""Alertas de vaga nova: casamento, deduplicação, opt-out e resumo (issue #12)."""

import pytest
from fastapi.testclient import TestClient

from farol import alerts, collect, db
from farol.app import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _vaga(source_id, title, *, score=80, description="", region="brasil",
          work_mode="remoto", state="novo", company="Acme"):
    return db.execute(
        """INSERT INTO jobs (source, source_id, fingerprint, title, company, description,
                             score, region, work_mode, state, skills)
           VALUES ('t', ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]')""",
        (source_id, source_id, title, company, description, score, region, work_mode, state),
    )


def _alerta(**campos):
    base = {"label": "Teste", "keywords": "", "min_score": 70, "notify": 1}
    return alerts.create({**base, **campos})


def test_casa_por_termo_nivel_regiao_e_fit():
    alvo = _vaga("alvo", "Desenvolvedor Python Júnior", score=85,
                 description="vaga junior para quem gosta de python")
    _vaga("fit-baixo", "Desenvolvedor Python Júnior", score=40, description="junior python")
    _vaga("sem-termo", "Analista de Dados Júnior", score=90, description="junior sql")
    _vaga("senior", "Python Staff Engineer", score=90, description="python sênior")
    _vaga("fora-da-regiao", "Python Júnior", score=90, description="junior python", region="outros")

    _alerta(keywords="python", level="entrada", region="brasil", min_score=70)
    novos = alerts.evaluate()

    assert [hit["job_id"] for hit in novos] == [alvo]


def test_mesma_vaga_nunca_avisa_duas_vezes():
    _vaga("alvo", "Python Júnior", description="junior python")
    _alerta(keywords="python")

    assert len(alerts.evaluate()) == 1
    assert alerts.evaluate() == []  # a chave (alerta, vaga) é a deduplicação


def test_alerta_pausado_para_de_casar():
    _vaga("alvo", "Python Júnior", description="junior python")
    alert_id = _alerta(keywords="python")
    alerts.toggle(alert_id)

    assert alerts.evaluate() == []


def test_opt_out_do_desktop_mantem_o_resumo_na_tela(monkeypatch):
    """`notify = 0` cala o aviso do sistema e preserva o casamento no app."""
    enviados = []
    monkeypatch.setattr(collect, "notify", lambda jobs: enviados.append(jobs) or True)

    _vaga("alvo", "Python Júnior", description="junior python")
    _alerta(keywords="python", notify=0)
    resultado = alerts.run()

    assert len(resultado["hits"]) == 1
    assert resultado["notified"] is False
    assert enviados == []
    assert alerts.pending_count() == 1


def test_aviso_do_desktop_sai_quando_ligado(monkeypatch):
    enviados = []
    monkeypatch.setattr(collect, "notify", lambda jobs: enviados.append(jobs) or True)

    _vaga("alvo", "Python Júnior", description="junior python")
    _alerta(keywords="python", notify=1)
    resultado = alerts.run()

    assert resultado["notified"] is True
    assert enviados and enviados[0][0]["title"] == "Python Júnior"


def test_falha_na_notificacao_nao_derruba_a_rodada(monkeypatch):
    """Sem `notify-send`, `collect.notify` devolve False — e o resumo continua de pé."""
    monkeypatch.setattr(collect, "notify", lambda jobs: False)

    _vaga("alvo", "Python Júnior", description="junior python")
    _alerta(keywords="python")
    resultado = alerts.run()

    assert resultado["error"] == ""
    assert len(resultado["hits"]) == 1
    assert alerts.pending_count() == 1


def test_erro_inesperado_no_alerta_nao_derruba_a_coleta(monkeypatch):
    monkeypatch.setattr(alerts, "evaluate", lambda *a, **k: 1 / 0)
    resultado = alerts.run()

    assert resultado["hits"] == []
    assert "ZeroDivisionError" in resultado["error"]


def test_vaga_expirada_sai_do_resumo():
    job_id = _vaga("alvo", "Python Júnior", description="junior python")
    _alerta(keywords="python")
    alerts.evaluate()
    assert alerts.pending_count() == 1

    db.execute("UPDATE jobs SET state = 'expirada' WHERE id = ?", (job_id,))
    assert alerts.pending_count() == 0
    assert alerts.digest() == []


def test_marcar_como_lido_esvazia_a_fila():
    _vaga("a", "Python Júnior", description="junior python")
    _vaga("b", "Python Júnior Pleno", description="junior python", company="Outra")
    _alerta(keywords="python")
    alerts.evaluate()

    assert alerts.mark_seen() == 2
    assert alerts.pending_count() == 0
    assert alerts.mark_seen() == 0


def test_remover_alerta_leva_o_historico_junto():
    _vaga("alvo", "Python Júnior", description="junior python")
    alert_id = _alerta(keywords="python")
    alerts.evaluate()

    alerts.delete(alert_id)
    assert db.one("SELECT COUNT(*) AS n FROM alert_hits")["n"] == 0


def test_coleta_avalia_so_o_que_ela_tocou(fixtures, monkeypatch, com_alerta_amplo):
    """A rodada devolve os casamentos junto com o relatório das fontes."""
    relatorio = collect.run()

    assert relatorio["alerts_error"] == ""
    assert relatorio["alerts"], "a coleta trouxe vagas e nenhuma casou com um alerta sem filtro"
    assert all(hit["alert"] == "Tudo" for hit in relatorio["alerts"])


@pytest.fixture
def com_alerta_amplo(fixtures, monkeypatch):
    """Alerta sem filtro nenhum, com as fontes respondendo pelas amostras gravadas."""
    import test_app

    test_app._fontes_gravadas(fixtures, monkeypatch)
    _alerta(label="Tudo", keywords="", min_score=0)
    return True


# ------------------------------------------------------------------ rotas


def test_criar_alerta_pela_tela_marca_o_acervo_como_lido(client):
    _vaga("antiga", "Python Júnior", description="junior python")

    resposta = client.post(
        "/alertas",
        data={"label": "Back júnior", "keywords": "python", "min_score": "50", "notify": "1"},
        follow_redirects=True,
    )
    assert resposta.status_code == 200
    # a vaga já estava na base: ela casa, mas entra como lida para não virar aviso
    assert alerts.pending_count() == 0
    assert db.one("SELECT COUNT(*) AS n FROM alert_hits")["n"] == 1


def test_alerta_sem_nome_nem_termo_e_recusado(client):
    resposta = client.post("/alertas", data={"label": " ", "keywords": " "}, follow_redirects=True)
    assert "Dê um nome ou um termo" in resposta.text
    assert alerts.all_alerts() == []


def test_tela_de_alertas_lista_o_resumo(client):
    _vaga("alvo", "Python Júnior", description="junior python")
    _alerta(label="Back júnior", keywords="python")
    alerts.evaluate()

    corpo = client.get("/alertas").text
    assert "Python Júnior" in corpo
    assert "Back júnior" in corpo


def test_valor_fora_da_lista_nao_entra_no_alerta(client):
    client.post(
        "/alertas",
        data={"label": "X", "keywords": "python", "level": "inventado",
              "region": "marte", "work_mode": "teletransporte", "min_score": "900"},
        follow_redirects=True,
    )
    alerta = alerts.all_alerts()[0]
    assert (alerta["level"], alerta["region"], alerta["work_mode"]) == ("", "", "")
    assert alerta["min_score"] == 100


def test_min_score_invalido_cai_no_padrao(client):
    client.post("/alertas", data={"label": "X", "keywords": "py", "min_score": "abc"},
                follow_redirects=True)
    assert alerts.all_alerts()[0]["min_score"] == 70


def test_fit_minimo_zero_e_respeitado(client):
    """Zero é falso em Python e é um valor legítimo: "qualquer vaga que case nos termos"."""
    client.post("/alertas", data={"label": "Tudo", "keywords": "", "min_score": "0"},
                follow_redirects=True)
    assert alerts.all_alerts()[0]["min_score"] == 0

    _vaga("fraca", "Estágio em Python", score=5)
    assert len(alerts.evaluate()) == 1


def test_avaliacao_em_blocos_aguenta_base_grande():
    """Um `IN (...)` com milhares de ids estoura o teto de parâmetros do SQLite."""
    total = alerts.CHUNK * 3 + 7
    conn = db.connect()
    with conn:
        conn.executemany(
            """INSERT INTO jobs (source, source_id, fingerprint, title, description,
                                 score, region, work_mode, skills)
               VALUES ('t', ?, ?, 'Python Júnior', 'junior python', 90, 'brasil', 'remoto', '[]')""",
            [(str(i), f"fp{i}") for i in range(total)],
        )
    ids = [row["id"] for row in db.query("SELECT id FROM jobs")]
    _alerta(keywords="python")

    assert len(alerts.evaluate(ids)) == total
    assert len(alerts.evaluate()) == 0  # tudo já casou; a varredura completa também passa
