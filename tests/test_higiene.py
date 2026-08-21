"""Expiração de vaga e ordem dos cartões — o que impede a base de apodrecer."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from farol import collect, db
from farol.app import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _vaga(source_id, vista_ha_dias, state="novo"):
    quando = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=vista_ha_dias)).isoformat(sep=" ", timespec="seconds")
    return db.execute(
        """INSERT INTO jobs (source, source_id, fingerprint, title, last_seen_at, state, skills)
           VALUES ('t', ?, ?, ?, ?, ?, '["python"]')""",
        (source_id, source_id, f"Vaga {source_id}", quando, state),
    )


def test_vaga_que_sumiu_das_coletas_e_marcada_como_expirada():
    antiga = _vaga("antiga", collect.STALE_AFTER_DAYS + 2)
    recente = _vaga("recente", 3)

    assert collect.expire() == 1
    assert db.one("SELECT state FROM jobs WHERE id = ?", (antiga,))["state"] == "expirada"
    assert db.one("SELECT state FROM jobs WHERE id = ?", (recente,))["state"] == "novo"


def test_expirar_nao_mexe_no_que_o_usuario_descartou():
    descartada = _vaga("descartada", collect.STALE_AFTER_DAYS + 5, state="descartada")
    collect.expire()
    assert db.one("SELECT state FROM jobs WHERE id = ?", (descartada,))["state"] == "descartada"


def test_vaga_expirada_sai_da_lista_mas_continua_no_banco(client):
    _vaga("antiga", collect.STALE_AFTER_DAYS + 2)
    collect.expire()

    ativas = client.get("/vagas?min=0").text
    assert "Vaga antiga" not in ativas
    fora_do_ar = client.get("/vagas?min=0&estado=expirada").text
    assert "Vaga antiga" in fora_do_ar
    assert db.one("SELECT COUNT(*) AS n FROM jobs")["n"] == 1


def test_vaga_expirada_nao_conta_para_o_roadmap():
    from farol import roadmap

    _vaga("antiga", collect.STALE_AFTER_DAYS + 2)
    assert roadmap.demand()["python"] == 1
    collect.expire()
    assert roadmap.demand() == {}


def test_coleta_sem_resultado_nenhum_nao_expira_a_base(monkeypatch):
    """Se todas as fontes caíram, o sumiço é do coletor — não do anúncio."""
    _vaga("antiga", collect.STALE_AFTER_DAYS + 2)
    monkeypatch.setattr(collect, "_fetch_all", lambda source, searches: ([], "rede fora"))
    relatorio = collect.run()

    assert relatorio["expired"] == 0
    assert db.one("SELECT state FROM jobs WHERE source_id = 'antiga'")["state"] == "novo"


def test_ordem_do_cartao_e_persistida(client):
    primeiro = db.execute("INSERT INTO applications (title, status) VALUES ('A', 'salva')")
    segundo = db.execute("INSERT INTO applications (title, status) VALUES ('B', 'salva')")

    resposta = client.post(f"/candidaturas/{segundo}/ordem", json={"ordem": [segundo, primeiro]})
    assert resposta.status_code == 200
    posicoes = {row["id"]: row["position"] for row in db.query("SELECT id, position FROM applications")}
    assert posicoes[segundo] == 0
    assert posicoes[primeiro] == 1

    # o pipeline respeita a ordem gravada
    corpo = client.get("/pipeline").text
    assert corpo.index(f'data-id="{segundo}"') < corpo.index(f'data-id="{primeiro}"')


def test_ordem_com_corpo_invalido_nao_derruba(client):
    app_id = db.execute("INSERT INTO applications (title, status) VALUES ('A', 'salva')")
    assert client.post(f"/candidaturas/{app_id}/ordem", json={"ordem": []}).status_code == 400
    assert client.post(f"/candidaturas/{app_id}/ordem", content=b"",
                       headers={"Content-Type": "application/json"}).status_code == 400


def test_mudar_de_etapa_manda_o_cartao_para_o_fim_da_coluna(client):
    a = db.execute("INSERT INTO applications (title, status, position) VALUES ('A', 'triagem', 0)")
    b = db.execute("INSERT INTO applications (title, status) VALUES ('B', 'salva')")

    client.post(f"/candidaturas/{b}/status", json={"status": "triagem"})
    assert db.one("SELECT position FROM applications WHERE id = ?", (b,))["position"] == 1
    assert db.one("SELECT position FROM applications WHERE id = ?", (a,))["position"] == 0
