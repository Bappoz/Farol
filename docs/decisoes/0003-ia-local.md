# 3. Assistente de IA local: endereço privado, API compatível, nada instalado

- **Estado:** implementado
- **Data:** 2026-09-23
- **Issue:** [#15 — Gerar currículo por vaga com modelo de IA local](https://github.com/Bappoz/Farol/issues/15)

## Contexto

Até aqui o assistente só existia com uma chave da API Anthropic. Isso deixava de
fora quem não quer pagar por token e, pior, contradizia a premissa do aplicativo:
o Farol roda em `127.0.0.1`, guarda tudo num SQLite do usuário e não manda dado
para lugar nenhum — exceto, justamente, quando o assistente estava ligado.

Rodar modelo na própria máquina deixou de ser exótico: Ollama, LM Studio,
`llama-server` (llama.cpp) e Jan sobem um servidor HTTP local em um comando.

## Decisões

### 1. O app não instala, não baixa e não sobe nada

A integração é do usuário. O Farol pergunta um endereço e conversa com o que já
está no ar. Isso não é preguiça: um aplicativo que baixa binário e modelo de
vários gigabytes por conta própria vira um vetor de instalação silenciosa, e o
usuário perde a noção do que está rodando na máquina dele. O que o app faz é
medir a memória disponível e dizer qual modelo cabe, com o comando para copiar.

### 2. Só endereço de loopback ou de rede privada

`localai.resolve_endpoint` resolve o host e recusa se **qualquer** um dos
endereços resolvidos for público. A validação roda ao salvar o ajuste **e** antes
de cada requisição — um DNS que muda entre uma coisa e outra não deve virar um
vazamento.

O que sai daqui é o currículo inteiro e a descrição da vaga. Um endereço digitado
errado que aponte para fora seria um vazamento de dado pessoal sem nenhum aviso
na tela. Rede privada (e não só loopback) é aceita porque rodar o modelo no
desktop e usar o app no notebook é um caso real.

O cliente HTTP usa `trust_env=False`: um `HTTP_PROXY` herdado do ambiente
mandaria para fora exatamente o que a validação acabou de impedir.

### 3. API compatível com a da OpenAI, e só ela

`POST /v1/chat/completions` é o menor denominador comum entre Ollama, LM Studio,
llama.cpp, Jan e vLLM. Falar o dialeto nativo de cada um seria manter quatro
integrações para o mesmo resultado. A única concessão é na **listagem** de
modelos: `/api/tags` do Ollama é tentado primeiro porque é o único que informa o
tamanho em disco; sem ele, cai em `/v1/models`.

### 4. Três chamadas curtas, não uma pedindo JSON

`ai.tailor_for_job` roda resumo, marcadores e carta em três idas e voltas. A
alternativa — uma chamada só devolvendo JSON estruturado — erra muito mais em
modelo de 3B, que é exatamente o tamanho que roda em notebook sem GPU. Além
disso, uma etapa que falha não leva as outras junto: o retorno traz a lista do
que falhou, e o currículo fica com o que deu certo.

O rascunho de base continua vindo de `resume.build` e `resume.cover_letter`, que
não usam IA. O modelo reescreve **por cima** de um documento já completo, então
uma falha total do servidor local devolve o currículo de sempre, nunca uma página
em branco.

### 5. A instrução de sistema é a mesma dos dois provedores

`ai.SYSTEM` proíbe inventar experiência, empresa, número, diploma ou tecnologia
que não esteja nos dados recebidos. Trocar o provedor não pode afrouxar a única
regra que separa um currículo direcionado de uma mentira.

### 6. Texto de raciocínio não entra no documento

Modelos de raciocínio (Qwen3, DeepSeek-R1) devolvem `<think>…</think>` antes da
resposta. `localai._sem_raciocinio` remove esse bloco: é conteúdo que o modelo
escreveu para si mesmo, e ele apareceria dentro do currículo.

## Catálogo de modelos

Os tamanhos em `localai.CATALOG` são os dos manifestos publicados na biblioteca
do Ollama (quantização Q4_K_M padrão), lidos em 2026-09-23 — não são estimativa.
`min_gb` é a memória a partir da qual o modelo roda sem escorrer para swap: o
peso do arquivo mais a folga do contexto e do sistema.

Quando a leitura de memória falha, **nada** é marcado como "cabe" e a tela diz
que não conseguiu medir. Recomendar um modelo de 8 GB para uma máquina de 8 GB é
o tipo de palpite que termina em swap e num app que parece travado.

## Consequências

- Quem usa o provedor local não manda uma linha do currículo para fora da rede.
- A geração é bem mais lenta que a da nuvem: em CPU, com modelo de 3B, as três
  etapas levam minutos. O tempo limite é generoso (`FAROL_LOCAL_AI_TIMEOUT`,
  padrão 300s) porque cortar cedo transformaria "lento" em "quebrado".
- Quem já tinha a chave da Anthropic configurada não perde nada: `ai.provider()`
  trata ajuste vazio com chave gravada como `anthropic`.
