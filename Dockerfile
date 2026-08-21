# Farol em contêiner — para rodar num servidor de casa (NAS, mini-PC, VPS pessoal)
# e acessar pelo navegador de qualquer máquina da rede.
#
#   docker build -t farol .
#   docker run -d --name farol -p 7788:7788 -v farol-dados:/dados farol
#
# O volume é obrigatório na prática: sem ele o banco vai embora com o contêiner.

FROM python:3.12-slim AS build

WORKDIR /app
COPY pyproject.toml README.md ./
COPY farol ./farol
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim

# poppler-utils dá o `pdftotext`, alternativa de leitura quando o pypdf não
# consegue extrair a camada de texto de um currículo enviado
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /install /usr/local

# usuário sem privilégio: o app não precisa de root para nada
RUN useradd --create-home --uid 10001 farol \
 && mkdir -p /dados \
 && chown -R farol:farol /dados
USER farol

ENV FAROL_HOME=/dados \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
VOLUME ["/dados"]
EXPOSE 7788

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if 'farol' in urllib.request.urlopen('http://127.0.0.1:7788/saude', timeout=3).read().decode() else 1)"

# 0.0.0.0 dentro do contêiner: quem restringe o acesso é o -p do docker
CMD ["farol", "servir", "--host", "0.0.0.0", "--port", "7788"]
