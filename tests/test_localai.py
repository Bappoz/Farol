"""Assistente por modelo local: endereço, listagem, geração e falha (issue #15).

Nenhum teste aqui sobe modelo nem fala com a rede: o servidor local é simulado
por `httpx.MockTransport`, e a resolução de nomes é substituída quando o caso em
teste depende de um endereço público.
"""

import socket

import httpx
import pytest
from fastapi.testclient import TestClient

from farol import ai, db, localai
from farol import resume as resume_mod
from farol.app import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def memoria_nao_memorizada():
    """`localai.hardware` é medido uma vez por processo; aqui, uma vez por teste."""
    localai.hardware.cache_clear()
    yield
    localai.hardware.cache_clear()


def _servidor(monkeypatch, handler):
    """Troca o cliente HTTP do módulo por um que responde pelo `handler`."""
    def fabrica(endpoint: str) -> httpx.Client:
        return httpx.Client(base_url=endpoint, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(localai, "_client", fabrica)


def _publico(monkeypatch):
    """Faz qualquer nome resolver para um IP público."""
    monkeypatch.setattr(
        localai.socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )


# ------------------------------------------------------------------ endereço


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
        ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
        ("127.0.0.1:11434", "http://127.0.0.1:11434"),  # sem esquema é o que se digita
        ("http://localhost:1234/v1/", "http://localhost:1234/v1"),
    ],
)
def test_endereco_privado_e_normalizado(entrada, esperado):
    assert localai.resolve_endpoint(entrada) == esperado


def test_endereco_publico_e_recusado(monkeypatch):
    _publico(monkeypatch)
    with pytest.raises(localai.LocalAIError, match="fora da sua rede"):
        localai.resolve_endpoint("http://exemplo.invalido:11434")


def test_esquema_estranho_e_recusado():
    with pytest.raises(localai.LocalAIError, match="esquema"):
        localai.resolve_endpoint("ftp://127.0.0.1:11434")


def test_endereco_vazio_e_recusado():
    with pytest.raises(localai.LocalAIError, match="nenhum endereço"):
        localai.resolve_endpoint("")


def test_nome_que_nao_resolve_diz_isso(monkeypatch):
    monkeypatch.setattr(
        localai.socket, "getaddrinfo",
        lambda *a, **k: (_ for _ in ()).throw(socket.gaierror("Name or service not known")),
    )
    with pytest.raises(localai.LocalAIError, match="não consegui resolver"):
        localai.resolve_endpoint("http://maquina-que-nao-existe:11434")


def test_endereco_e_revalidado_a_cada_geracao(monkeypatch):
    """Validar só ao salvar deixaria um DNS que muda depois virar vazamento."""
    db.set_setting("ai_provider", "local")
    db.set_setting("local_ai_url", "http://servidor-da-casa:11434")
    db.set_setting("local_ai_model", "qwen2.5:7b")
    _servidor(monkeypatch, lambda request: httpx.Response(200, json={}))
    _publico(monkeypatch)  # o nome passou a resolver para fora

    with pytest.raises(localai.LocalAIError, match="fora da sua rede"):
        localai.complete("oi", "sistema")


# ------------------------------------------------------------------ listagem


def test_lista_modelos_pelo_dialeto_do_ollama(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [
            {"name": "qwen2.5:7b", "size": 4_700_000_000,
             "details": {"parameter_size": "7.6B", "quantization_level": "Q4_K_M"}},
            {"name": "llama3.2:3b", "size": 2_000_000_000, "details": {}},
        ]})

    _servidor(monkeypatch, handler)
    modelos = localai.models("http://127.0.0.1:11434")

    assert [m["name"] for m in modelos] == ["llama3.2:3b", "qwen2.5:7b"]
    assert modelos[1]["size_gb"] == 4.7
    assert modelos[1]["params"] == "7.6B"


def test_cai_para_a_api_compativel_quando_nao_e_ollama(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(404)
        return httpx.Response(200, json={"data": [{"id": "modelo-local"}]})

    _servidor(monkeypatch, handler)
    assert [m["name"] for m in localai.models("http://127.0.0.1:1234")] == ["modelo-local"]


def test_servidor_fora_do_ar_vira_mensagem_legivel(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("conexão recusada")

    _servidor(monkeypatch, handler)
    with pytest.raises(localai.LocalAIError, match="não achei um servidor"):
        localai.models("http://127.0.0.1:11434")


def test_endereco_que_aponta_para_outra_coisa_nao_estoura(monkeypatch):
    _servidor(monkeypatch, lambda request: httpx.Response(200, content=b"<html>"))
    with pytest.raises(localai.LocalAIError, match="não é JSON"):
        localai.models("http://127.0.0.1:8080")


def test_probe_devolve_diagnostico_em_vez_de_excecao(monkeypatch):
    _publico(monkeypatch)
    resultado = localai.probe("http://exemplo.invalido")

    assert resultado["ok"] is False
    assert "fora da sua rede" in resultado["erro"]
    assert resultado["models"] == []


# ------------------------------------------------------------------ geração


def _responde(texto: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": texto}}]})
    return handler


def test_gera_texto_pela_api_compativel(monkeypatch):
    enviado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        enviado["path"] = request.url.path
        enviado["json"] = httpx.Request("POST", "http://x", content=request.content).content
        return httpx.Response(200, json={"choices": [{"message": {"content": " resposta "}}]})

    _servidor(monkeypatch, handler)
    texto = localai.complete("prompt", "sistema", model="m", endpoint="http://127.0.0.1:11434")

    assert texto == "resposta"
    assert enviado["path"] == "/v1/chat/completions"
    assert b'"sistema"' in enviado["json"]


def test_sem_modelo_escolhido_a_falha_e_explicita(monkeypatch):
    _servidor(monkeypatch, _responde("x"))
    db.set_setting("local_ai_model", "")
    with pytest.raises(localai.LocalAIError, match="nenhum modelo local escolhido"):
        localai.complete("p", "s", endpoint="http://127.0.0.1:11434")


def test_erro_do_servidor_vira_mensagem_com_o_codigo(monkeypatch):
    _servidor(monkeypatch, lambda request: httpx.Response(500, text="modelo não carregado"))
    with pytest.raises(localai.LocalAIError, match="respondeu 500"):
        localai.complete("p", "s", model="m", endpoint="http://127.0.0.1:11434")


def test_raciocinio_do_modelo_nao_entra_no_documento(monkeypatch):
    _servidor(monkeypatch, _responde("<think>vou começar pelo resumo</think>\nResumo final."))
    texto = localai.complete("p", "s", model="m", endpoint="http://127.0.0.1:11434")

    assert texto == "Resumo final."


def test_raciocinio_sem_fechamento_nao_vaza(monkeypatch):
    """Resposta cortada no meio do raciocínio é rascunho interno inteiro."""
    _servidor(monkeypatch, _responde("Começo.<think>ainda pensando e a resposta"))
    assert localai.complete("p", "s", model="m", endpoint="http://127.0.0.1:11434") == "Começo."


# ------------------------------------------------------------------ hardware


def test_recomendacao_marca_o_que_cabe():
    itens = localai.recommendations(budget_gb=8)
    por_nome = {i["name"]: i for i in itens}

    assert por_nome["qwen2.5:3b"]["fits"] is True
    assert por_nome["gemma3:12b"]["fits"] is False
    assert por_nome["qwen2.5:3b"]["pull"] == "ollama pull qwen2.5:3b"


def test_sem_medida_de_memoria_nada_e_recomendado():
    """Chutar aqui termina em swap e num app que parece travado."""
    assert all(item["fits"] is None for item in localai.recommendations(budget_gb=None))
    assert localai.suggested(budget_gb=None) is None


def test_sugestao_e_o_maior_que_cabe():
    assert localai.suggested(budget_gb=16)["name"] == "qwen3:8b"
    assert localai.suggested(budget_gb=1) is None


def test_hardware_nunca_inventa_numero(monkeypatch):
    monkeypatch.setattr(localai, "_ram_bytes", lambda: None)
    monkeypatch.setattr(localai, "_vram_bytes", lambda: (None, ""))
    maquina = localai.hardware()

    assert maquina == {"ram_gb": None, "vram_gb": None, "vram_source": "", "budget_gb": None}


# ------------------------------------------------------------------ provedor


def test_sem_provedor_o_assistente_nao_existe():
    assert ai.provider() == ""
    assert ai.available() is False
    with pytest.raises(RuntimeError, match="Nenhum assistente"):
        ai.complete("oi")


def test_chave_antiga_sem_seletor_continua_valendo():
    """Quem configurou a chave antes deste ajuste existir não perde o assistente."""
    db.set_setting("anthropic_api_key", "sk-ant-teste")
    assert ai.provider() == "anthropic"
    assert ai.describe()["ready"] is True


def test_provedor_local_descrito_com_o_que_falta():
    db.set_setting("ai_provider", "local")
    db.set_setting("local_ai_model", "")
    descricao = ai.describe()

    assert descricao["provider"] == "local"
    assert descricao["ready"] is False
    assert "modelo" in descricao["pending"]


def test_etapa_que_falha_nao_leva_as_outras(monkeypatch):
    """Com modelo local, tempo esgotado numa etapa é rotina — e não pode zerar o resto."""
    chamadas = []

    def falso(prompt, max_tokens=1200):
        chamadas.append(max_tokens)
        if len(chamadas) == 2:
            raise localai.LocalAIError("tempo esgotado")
        return "texto do modelo"

    monkeypatch.setattr(ai, "complete", falso)
    dados, carta, falhas = ai.tailor_for_job({"summary": "antigo"}, "carta original", None)

    assert dados["summary"] == "texto do modelo"
    assert "ai_bullets" not in dados
    assert carta == "texto do modelo"
    assert len(falhas) == 1 and falhas[0].startswith("marcadores")


# ------------------------------------------------------------------ rotas


def test_rota_de_sondagem_recusa_endereco_publico(client, monkeypatch):
    _publico(monkeypatch)
    resposta = client.post("/ajustes/ia/modelos", json={"endpoint": "http://exemplo.invalido"})

    assert resposta.status_code == 200  # diagnóstico, não erro de servidor
    assert resposta.json()["ok"] is False
    assert "fora da sua rede" in resposta.json()["erro"]


def test_ajustes_nao_grava_endereco_publico(client, monkeypatch):
    _publico(monkeypatch)
    resposta = client.post(
        "/ajustes",
        data={"ai_provider": "local", "local_ai_url": "http://exemplo.invalido:11434"},
        follow_redirects=True,
    )

    assert "recusado" in resposta.text
    assert db.get_settings()["local_ai_url"] == localai.DEFAULT_ENDPOINT


def test_ajustes_normaliza_endereco_ao_gravar(client):
    client.post(
        "/ajustes",
        data={"ai_provider": "local", "local_ai_url": "localhost:1234/", "local_ai_model": "m"},
        follow_redirects=True,
    )
    assert db.get_settings()["local_ai_url"] == "http://localhost:1234"


def test_curriculo_por_vaga_sem_ia_continua_funcionando(client, com_vaga):
    resposta = client.post(f"/vagas/{com_vaga}/curriculo", data={"lang": "pt"},
                           follow_redirects=True)

    assert resposta.status_code == 200
    linha = db.one("SELECT data, job_id FROM resumes ORDER BY id DESC LIMIT 1")
    dados = db.loads(linha["data"], {})
    assert linha["job_id"] == com_vaga
    assert dados["target"]["title"] == "Desenvolvedor Back-end Júnior"
    assert "ai_bullets" not in dados


def test_curriculo_por_vaga_com_modelo_local(client, com_vaga, monkeypatch):
    db.set_setting("ai_provider", "local")
    db.set_setting("local_ai_model", "qwen2.5:7b")
    _servidor(monkeypatch, _responde("Texto vindo do modelo local."))

    resposta = client.post(f"/vagas/{com_vaga}/curriculo", data={"lang": "pt", "ia": "1"},
                           follow_redirects=True)

    assert resposta.status_code == 200
    linha = db.one("SELECT data, letter FROM resumes ORDER BY id DESC LIMIT 1")
    dados = db.loads(linha["data"], {})
    assert dados["summary"] == "Texto vindo do modelo local."
    assert dados["ai_bullets"] == "Texto vindo do modelo local."
    assert linha["letter"] == "Texto vindo do modelo local."


def test_servidor_local_fora_do_ar_devolve_curriculo_completo(client, com_vaga, monkeypatch):
    """O rascunho do `resume.build` já está pronto antes de o modelo ser chamado."""
    db.set_setting("ai_provider", "local")
    db.set_setting("local_ai_model", "qwen2.5:7b")

    def handler(request):
        raise httpx.ConnectError("conexão recusada")

    _servidor(monkeypatch, handler)
    resposta = client.post(f"/vagas/{com_vaga}/curriculo", data={"lang": "pt", "ia": "1"},
                           follow_redirects=True)

    assert "parte da IA falhou" in resposta.text
    dados = db.loads(db.one("SELECT data FROM resumes ORDER BY id DESC LIMIT 1")["data"], {})
    assert dados["name"] and dados["skills"]  # o currículo não veio vazio
    assert dados["summary"] != ""


@pytest.fixture
def com_vaga():
    db.save_profile({
        "name": "Ana Ribeiro", "headline": "Dev back-end júnior", "email": "ana@exemplo.com",
        "phone": "", "city": "", "area": "backend", "seniority": "junior", "summary": "",
        "links": [], "skills": ["python", "fastapi"], "languages": [], "education": [],
        "experience": [], "projects": [],
    })
    return db.execute(
        """INSERT INTO jobs (source, source_id, fingerprint, title, company, description, skills)
           VALUES ('t', '1', 'fp', 'Desenvolvedor Back-end Júnior', 'Acme',
                   'Python e FastAPI para pessoa júnior.', '[]')"""
    )


def test_instrucao_de_sistema_e_a_mesma_nos_dois_provedores():
    """Trocar de provedor não pode afrouxar a regra de não inventar experiência."""
    assert "Nunca invente experiência" in ai.SYSTEM
    assert resume_mod.PLACEHOLDER in ai.SYSTEM


def test_modelo_que_repete_o_contexto_nao_suja_o_curriculo(client, com_vaga, monkeypatch):
    """Modelo pequeno às vezes devolve o JSON recebido; isso é falha, não resposta."""
    db.set_setting("ai_provider", "local")
    db.set_setting("local_ai_model", "modelo-pequeno")
    _servidor(monkeypatch, _responde('{\n  "curriculo": {\n    "name": "Ana Ribeiro"\n  }\n}'))

    resposta = client.post(f"/vagas/{com_vaga}/curriculo", data={"lang": "pt", "ia": "1"},
                           follow_redirects=True)

    assert "repetiu os dados" in resposta.text
    linha = db.one("SELECT data, letter FROM resumes ORDER BY id DESC LIMIT 1")
    dados = db.loads(linha["data"], {})
    assert "ai_bullets" not in dados
    assert '"curriculo"' not in dados["summary"]
    assert '"curriculo"' not in linha["letter"]
