"""Backup e restauração — e o calendário das próximas ações."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from farol import agenda, backup, db
from farol.app import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def dados_do_usuario():
    db.save_profile({"name": "Ana Ribeiro", "headline": "Back-end júnior", "email": "ana@ex.com",
                     "phone": "", "city": "Curitiba", "area": "backend", "seniority": "junior",
                     "summary": "", "links": [{"label": "GitHub", "url": "https://gh/ana"}],
                     "skills": ["python", "sql"], "languages": [], "education": [],
                     "experience": [], "projects": []})
    app_id = db.execute(
        "INSERT INTO applications (title, company, status, next_action, next_action_at) "
        "VALUES ('Dev Python', 'Acme', 'triagem', 'Enviar follow-up', '2026-09-01')")
    db.execute("INSERT INTO events (application_id, kind, note, to_status) "
               "VALUES (?, 'status', 'Salvas → Triagem', 'triagem')", (app_id,))
    db.execute("INSERT INTO resumes (name, data) VALUES ('Currículo base', '{}')")
    db.execute("INSERT INTO learning (kind, ref, title) VALUES ('skill', 'css', 'Estudar CSS')")
    db.set_setting("weekly_goal", "9")
    db.set_setting("anthropic_api_key", "sk-segredo-que-nao-pode-vazar")
    return app_id


def test_backup_leva_o_trabalho_e_deixa_as_vagas_para_tras(dados_do_usuario):
    db.execute("INSERT INTO jobs (source, source_id, fingerprint, title) VALUES ('t','1','1','X')")
    dados = backup.payload()
    assert dados["profile"]["name"] == "Ana Ribeiro"
    assert len(dados["applications"]) == 1
    assert len(dados["events"]) == 1
    assert "jobs" not in dados            # vaga se refaz sozinha na próxima coleta


def test_backup_nunca_carrega_a_chave_da_api(dados_do_usuario):
    bruto = json.dumps(backup.payload())
    assert "sk-segredo-que-nao-pode-vazar" not in bruto
    assert backup.payload()["settings"]["weekly_goal"] == "9"


def test_arquivo_zip_traz_o_manifesto_e_os_pdfs(dados_do_usuario):
    from farol import pdfs
    resume_id = db.execute("INSERT INTO resumes (name, kind, file) VALUES ('PDF meu', 'arquivo', '')")
    relativo = pdfs.save(resume_id, "PDF meu", b"%PDF-1.4 conteudo")
    db.execute("UPDATE resumes SET file = ? WHERE id = ?", (relativo, resume_id))

    with zipfile.ZipFile(io.BytesIO(backup.archive())) as zf:
        nomes = zf.namelist()
        assert backup.MANIFEST in nomes
        assert relativo in nomes
        assert zf.read(relativo) == b"%PDF-1.4 conteudo"


def test_restaurar_devolve_tudo_num_banco_vazio(dados_do_usuario):
    arquivo = backup.archive()
    db.execute("DELETE FROM applications")
    db.execute("DELETE FROM learning")
    db.save_profile({"name": "", "headline": "", "email": "", "phone": "", "city": "",
                     "area": "backend", "seniority": "junior", "summary": "", "links": [],
                     "skills": [], "languages": [], "education": [], "experience": [],
                     "projects": []})

    dados, arquivos = backup.read(arquivo)
    resumo = backup.restore(dados, arquivos)

    assert db.get_profile()["name"] == "Ana Ribeiro"
    assert db.get_profile()["skills"] == ["python", "sql"]
    assert db.one("SELECT COUNT(*) AS n FROM applications")["n"] == 1
    assert db.one("SELECT COUNT(*) AS n FROM events")["n"] == 1
    assert db.one("SELECT COUNT(*) AS n FROM learning")["n"] == 1
    assert db.get_settings()["weekly_goal"] == "9"
    assert resumo["tabelas"]["applications"] == 1


def test_restaurar_nao_apaga_as_vagas_coletadas(dados_do_usuario):
    db.execute("INSERT INTO jobs (source, source_id, fingerprint, title) VALUES ('t','1','1','X')")
    dados, arquivos = backup.read(backup.archive())
    backup.restore(dados, arquivos)
    assert db.one("SELECT COUNT(*) AS n FROM jobs")["n"] == 1


def test_restaurar_aceita_json_solto_e_avisa_do_pdf_ausente(dados_do_usuario):
    db.execute("INSERT INTO resumes (name, kind, file) VALUES ('PDF meu', 'arquivo', 'curriculos/x.pdf')")
    dados = backup.payload()
    resumo = backup.restore(*backup.read(json.dumps(dados).encode("utf-8")))
    assert resumo["arquivos"] == 0
    assert "PDF meu" in resumo["pdfs_ausentes"]


def test_arquivo_que_nao_e_backup_e_recusado():
    with pytest.raises(ValueError):
        backup.restore(*backup.read(b'{"qualquer": "coisa"}'))


def test_restauracao_pela_tela_exige_confirmacao_escrita(client, dados_do_usuario):
    arquivo = backup.archive()
    db.execute("DELETE FROM applications")

    sem_confirmar = client.post("/ajustes/restaurar", files={"arquivo": ("b.zip", arquivo)},
                                data={"confirmar": "sim"}, follow_redirects=False)
    assert "SUBSTITUIR" in sem_confirmar.headers["location"]
    assert db.one("SELECT COUNT(*) AS n FROM applications")["n"] == 0

    com_confirmacao = client.post("/ajustes/restaurar", files={"arquivo": ("b.zip", arquivo)},
                                  data={"confirmar": "SUBSTITUIR"}, follow_redirects=False)
    assert "restaurado" in com_confirmacao.headers["location"]
    assert db.one("SELECT COUNT(*) AS n FROM applications")["n"] == 1


def test_backup_pela_tela_devolve_um_zip(client, dados_do_usuario):
    resposta = client.post("/ajustes/backup")
    assert resposta.headers["content-type"] == "application/zip"
    assert resposta.content[:2] == b"PK"


# ------------------------------------------------------------------ agenda


def test_calendario_traz_a_proxima_acao_como_dia_inteiro(client, dados_do_usuario):
    corpo = client.get("/agenda.ics").text
    assert corpo.startswith("BEGIN:VCALENDAR")
    assert "DTSTART;VALUE=DATE:20260901" in corpo
    assert "DTEND;VALUE=DATE:20260902" in corpo      # DTEND é exclusivo
    assert "SUMMARY:Enviar follow-up · Acme" in corpo
    assert corpo.endswith("END:VCALENDAR\r\n")
    assert "\r\n" in corpo                            # a RFC exige CRLF


def test_calendario_ignora_candidatura_sem_data_ou_encerrada(client):
    db.execute("INSERT INTO applications (title, status, next_action) VALUES ('sem data','salva','x')")
    db.execute("INSERT INTO applications (title, status, next_action, next_action_at) "
               "VALUES ('encerrada','encerrada','x','2026-09-01')")
    assert client.get("/agenda.ics").text.count("BEGIN:VEVENT") == 0


def test_texto_do_calendario_e_escapado_como_a_rfc_manda():
    assert agenda._escape("a, b; c") == "a\\, b\\; c"
    assert agenda._escape("linha\nquebrada") == "linha\\nquebrada"
    assert agenda._escape("barra\\invertida") == "barra\\\\invertida"


def test_linha_longa_e_dobrada_em_75_octetos():
    dobrada = agenda._fold("SUMMARY:" + "a" * 200)
    assert all(len(parte.encode()) <= 75 for parte in dobrada.split("\r\n "))
    assert dobrada.replace("\r\n ", "") == "SUMMARY:" + "a" * 200
