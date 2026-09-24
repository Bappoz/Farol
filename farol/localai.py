"""Assistente por modelo de IA rodando na sua máquina.

O Farol **não instala, não baixa e não sobe** modelo nenhum. Quem faz a integração
é você: sobe o servidor que preferir (Ollama, LM Studio, llama.cpp `server`, Jan) e
diz aqui o endereço. O app só conversa com o que já está no ar.

Três decisões que valem a pena estarem escritas:

1. **Endereço privado, e ponto.** O que sai daqui é o seu currículo e a descrição
   da vaga. Um endereço digitado errado que aponte para fora da sua rede vazaria o
   currículo inteiro sem um aviso sequer. Por isso `resolve_endpoint` resolve o
   nome e recusa qualquer coisa que não caia em loopback ou rede privada — e
   recusa antes de **cada** requisição, não só quando você salva o ajuste.

2. **A API é a compatível com a da OpenAI** (`/v1/chat/completions`). É o menor
   denominador comum entre os quatro servidores citados; falar o dialeto nativo de
   cada um significaria quatro integrações para o mesmo resultado.

3. **Catálogo com número medido, não estimado.** Os tamanhos em `CATALOG` são os
   dos manifestos publicados pela biblioteca do Ollama, e a memória da máquina é
   lida do sistema. Quando a leitura falha, a tela diz que não sabe — recomendar
   um modelo de 8 GB para quem tem 8 GB de RAM é o tipo de palpite que termina em
   swap e num app que parece travado.
"""

from __future__ import annotations

import ctypes
import functools
import ipaddress
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"

# Um modelo de 3B numa CPU modesta leva dezenas de segundos para escrever meia
# página. O tempo é generoso de propósito: cortar em 30s transformaria "lento"
# em "quebrado".
TIMEOUT_SECONDS = float(os.environ.get("FAROL_LOCAL_AI_TIMEOUT", "300"))


class LocalAIError(RuntimeError):
    """Falha ao falar com o servidor local. A mensagem vai crua para a tela."""


# ------------------------------------------------------------------ endereço


def _private(host: str) -> bool:
    """O nome resolve **inteiramente** para loopback ou rede privada?

    Um nome pode resolver para vários endereços; basta um público para o pedido
    poder sair da rede, então a checagem exige que todos sejam privados.
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise LocalAIError(f"não consegui resolver o endereço “{host}”: {exc}") from exc
    if not infos:
        raise LocalAIError(f"o endereço “{host}” não resolveu para nenhum IP.")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not (address.is_loopback or address.is_private or address.is_link_local):
            return False
    return True


def resolve_endpoint(raw: str | None) -> str:
    """Valida e normaliza a URL base do servidor local. Erra alto quando não serve.

    Devolve a base sem barra final (`http://127.0.0.1:11434`), pronta para
    concatenar com o caminho da API.
    """
    text = (raw or "").strip()
    if not text:
        raise LocalAIError("nenhum endereço de servidor local configurado em Ajustes.")
    if "//" not in text:
        text = "http://" + text  # digitar só "localhost:11434" é o caso comum
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise LocalAIError(f"esquema “{parsed.scheme}” não serve: use http ou https.")
    if not parsed.hostname:
        raise LocalAIError("endereço sem host.")
    if not _private(parsed.hostname):
        raise LocalAIError(
            f"“{parsed.hostname}” está fora da sua rede. O assistente local só aceita "
            "loopback (127.0.0.1, ::1) ou rede privada — o que sai daqui é o seu "
            "currículo, e um endereço público o mandaria para fora sem aviso."
        )
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}{parsed.path.rstrip('/')}"


def configured_endpoint() -> str:
    from . import db  # local: o módulo é importado por db-adjacentes nos testes

    return resolve_endpoint(db.get_settings().get("local_ai_url") or DEFAULT_ENDPOINT)


# ------------------------------------------------------------------ servidor


def _client(endpoint: str) -> httpx.Client:
    # `trust_env=False`: um proxy herdado do ambiente mandaria para fora da máquina
    # exatamente o que a validação de endereço acabou de impedir.
    return httpx.Client(timeout=TIMEOUT_SECONDS, trust_env=False, base_url=endpoint)


def _ollama_models(http: httpx.Client) -> list[dict[str, Any]] | None:
    """Catálogo no dialeto do Ollama, que é o único que informa o tamanho em disco."""
    response = http.get("/api/tags")
    if response.status_code != 200:
        return None
    data = response.json()
    if not isinstance(data.get("models"), list):
        return None
    modelos = []
    for item in data["models"]:
        detalhes = item.get("details") or {}
        modelos.append(
            {
                "name": item.get("name") or item.get("model") or "",
                "size_gb": round((item.get("size") or 0) / 1e9, 1) or None,
                "params": detalhes.get("parameter_size") or "",
                "quant": detalhes.get("quantization_level") or "",
            }
        )
    return [m for m in modelos if m["name"]]


def _openai_models(http: httpx.Client) -> list[dict[str, Any]]:
    response = http.get("/v1/models")
    if response.status_code != 200:
        raise LocalAIError(f"o servidor respondeu {response.status_code} ao listar modelos.")
    data = response.json()
    itens = data.get("data") if isinstance(data, dict) else None
    if not isinstance(itens, list):
        raise LocalAIError("resposta de /v1/models em formato inesperado.")
    return [
        {"name": str(item.get("id") or ""), "size_gb": None, "params": "", "quant": ""}
        for item in itens
        if item.get("id")
    ]


def models(endpoint: str | None = None) -> list[dict[str, Any]]:
    """Modelos que o servidor local diz ter. Ordenados por nome."""
    base = resolve_endpoint(endpoint) if endpoint else configured_endpoint()
    try:
        with _client(base) as http:
            encontrados = _ollama_models(http) or _openai_models(http)
    except httpx.HTTPError as exc:
        raise LocalAIError(
            f"não achei um servidor em {base} ({type(exc).__name__}). "
            "Confira se ele está no ar — no Ollama, `ollama serve`."
        ) from exc
    except ValueError as exc:  # JSON inválido: o endereço aponta para outra coisa
        raise LocalAIError(f"{base} respondeu algo que não é JSON — é mesmo o servidor?") from exc
    return sorted(encontrados, key=lambda m: m["name"])


def probe(endpoint: str | None = None) -> dict[str, Any]:
    """Diagnóstico para a tela de Ajustes: está no ar? com quais modelos?"""
    try:
        base = resolve_endpoint(endpoint) if endpoint else configured_endpoint()
    except LocalAIError as exc:
        return {"ok": False, "endpoint": (endpoint or "").strip(), "erro": str(exc), "models": []}
    try:
        return {"ok": True, "endpoint": base, "erro": "", "models": models(base)}
    except LocalAIError as exc:
        return {"ok": False, "endpoint": base, "erro": str(exc), "models": []}


def complete(prompt: str, system: str, *, model: str | None = None,
             endpoint: str | None = None, max_tokens: int = 1200,
             temperature: float = 0.2) -> str:
    """Uma rodada de conversa com o modelo local. Devolve só o texto."""
    from . import db

    settings = db.get_settings()
    base = resolve_endpoint(endpoint) if endpoint else configured_endpoint()
    nome = (model or settings.get("local_ai_model") or "").strip()
    if not nome:
        raise LocalAIError("nenhum modelo local escolhido em Ajustes.")
    payload = {
        "model": nome,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    try:
        with _client(base) as http:
            response = http.post("/v1/chat/completions", json=payload)
    except httpx.HTTPError as exc:
        raise LocalAIError(
            f"não consegui falar com {base} ({type(exc).__name__}). O servidor caiu?"
        ) from exc
    if response.status_code >= 400:
        raise LocalAIError(f"o servidor respondeu {response.status_code}: {response.text[:300]}")
    try:
        escolhas = response.json()["choices"]
        texto = escolhas[0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LocalAIError("resposta do servidor em formato inesperado.") from exc
    return _sem_raciocinio(str(texto or "")).strip()


def _sem_raciocinio(texto: str) -> str:
    """Tira o bloco <think>…</think> dos modelos de raciocínio (Qwen3, DeepSeek-R1).

    Sem isto o rascunho do currículo viria com o monólogo do modelo dentro —
    conteúdo que ele escreveu para si mesmo, não para o recrutador.
    """
    while "<think>" in texto:
        inicio = texto.index("<think>")
        fim = texto.find("</think>", inicio)
        if fim == -1:
            return texto[:inicio]  # raciocínio sem fechar: o resto é rascunho interno
        texto = texto[:inicio] + texto[fim + len("</think>"):]
    return texto


# ------------------------------------------------------------------ hardware


def _ram_bytes() -> int | None:
    if os.name == "nt":
        class _Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = _Status()
        status.dwLength = ctypes.sizeof(_Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return int(status.ullTotalPhys)
        return None
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return None


def _vram_bytes() -> tuple[int | None, str]:
    """VRAM da GPU, quando há uma que saiba se apresentar. Devolve (bytes, de onde)."""
    try:
        saida = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        linhas = [linha.strip() for linha in saida.stdout.splitlines() if linha.strip().isdigit()]
        if linhas:
            return max(int(linha) for linha in linhas) * 1024 * 1024, "nvidia-smi"
    except (FileNotFoundError, OSError, subprocess.SubprocessError, ValueError):
        pass  # sem driver NVIDIA: segue para o caminho do kernel

    # AMD e Intel discretas expõem o total em sysfs, sem precisar de ferramenta
    if sys.platform.startswith("linux"):
        maior = 0
        for arquivo in Path("/sys/class/drm").glob("card*/device/mem_info_vram_total"):
            try:
                maior = max(maior, int(arquivo.read_text().strip()))
            except (OSError, ValueError):
                continue
        if maior:
            return maior, "sysfs"
    return None, ""


@functools.lru_cache(maxsize=1)
def hardware() -> dict[str, Any]:
    """O que a máquina tem, em GB. `None` quando não deu para medir — nunca um chute.

    Medido uma vez por processo: a RAM não muda enquanto o app está aberto, e
    `nvidia-smi` é um processo novo a cada chamada — caro demais para rodar a
    cada abertura da tela de Ajustes.
    """
    ram = _ram_bytes()
    vram, origem = _vram_bytes()
    return {
        "ram_gb": round(ram / 1e9, 1) if ram else None,
        "vram_gb": round(vram / 1e9, 1) if vram else None,
        "vram_source": origem,
        # o modelo roda inteiro na GPU quando cabe nela; senão, na RAM
        "budget_gb": round(max(vram or 0, ram or 0) / 1e9, 1) if (ram or vram) else None,
    }


# Tamanhos em GB do arquivo que o `ollama pull` baixa (quantização Q4_K_M padrão
# da biblioteca), lidos dos manifestos publicados. `min_gb` é a memória livre a
# partir da qual o modelo roda sem escorrer para swap: o peso do arquivo mais a
# folga do contexto e do próprio sistema.
CATALOG: list[dict[str, Any]] = [
    {
        "name": "qwen2.5:3b", "size_gb": 1.9, "min_gb": 6,
        "nota": "O mais leve que ainda escreve português aceitável. Notebook sem GPU dedicada.",
    },
    {
        "name": "llama3.2:3b", "size_gb": 2.0, "min_gb": 6,
        "nota": "Alternativa ao Qwen de 3B; texto um pouco mais solto, menos obediente ao formato.",
    },
    {
        "name": "qwen3:4b", "size_gb": 2.5, "min_gb": 8,
        "nota": "Raciocina antes de responder — melhor para a carta, mais lento para tudo.",
    },
    {
        "name": "phi4-mini", "size_gb": 2.5, "min_gb": 8,
        "nota": "Bom em seguir instrução curta. Português correto, porém seco.",
    },
    {
        "name": "gemma3:4b", "size_gb": 3.3, "min_gb": 8,
        "nota": "Português do Brasil mais natural que o dos outros modelos pequenos.",
    },
    {
        "name": "mistral:7b", "size_gb": 4.4, "min_gb": 12,
        "nota": "Veterano estável. Menos afiado que os 7B recentes, mas raro de falhar.",
    },
    {
        "name": "qwen2.5:7b", "size_gb": 4.7, "min_gb": 12,
        "nota": "O melhor equilíbrio para esta tarefa em máquina de 16 GB.",
    },
    {
        "name": "llama3.1:8b", "size_gb": 4.9, "min_gb": 12,
        "nota": "Texto longo com boa coesão; pede mais folga de memória que o Qwen de 7B.",
    },
    {
        "name": "qwen3:8b", "size_gb": 5.2, "min_gb": 16,
        "nota": "Raciocínio e 8B juntos: a melhor escrita da lista, e a mais lenta.",
    },
    {
        "name": "gemma3:12b", "size_gb": 8.1, "min_gb": 24,
        "nota": "Só vale com GPU de 12 GB ou mais. Em CPU, a espera é de minutos.",
    },
]


def recommendations(budget_gb: float | None) -> list[dict[str, Any]]:
    """O catálogo marcado com o que cabe na máquina. O orçamento vem de `hardware()`.

    `None` quer dizer **não medido**, e não "meça agora": sem medida, nada é
    marcado como "cabe" e a tela diz que não conseguiu medir, em vez de
    recomendar no escuro. O argumento é obrigatório justamente para que esse
    caso seja uma escolha de quem chama, e não um efeito colateral.
    """
    itens = []
    for entrada in CATALOG:
        cabe = None if budget_gb is None else budget_gb >= entrada["min_gb"]
        itens.append({**entrada, "fits": cabe, "pull": f"ollama pull {entrada['name']}"})
    return itens


def suggested(budget_gb: float | None) -> dict[str, Any] | None:
    """O maior modelo que cabe — o palpite único, quando a memória é conhecida."""
    if budget_gb is None:
        return None
    cabem = [e for e in CATALOG if budget_gb >= e["min_gb"]]
    return max(cabem, key=lambda e: e["size_gb"]) if cabem else None
