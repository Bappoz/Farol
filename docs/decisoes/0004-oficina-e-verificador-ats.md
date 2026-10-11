# 4. Oficina de currículo: folha desenhada no servidor, nota ATS por regra e IA só como segunda leitura

- **Estado:** implementado
- **Data:** 2026-10-11
- **Issue:** [#17 — Oficina de currículo](https://github.com/Bappoz/Farol/issues/17)

## Contexto

O editor de currículo era um ciclo cego — editar, salvar, só então ver — e a
"checagem antes de enviar" era uma lista de nove itens sem nota, sem peso e sem
olhar para o formato. Os serviços que dão "nota ATS" cobram por isso ou exigem
subir o currículo para um servidor de terceiros, o que contraria a premissa do
aplicativo.

## Decisões

### 1. A nota é determinística; a IA não dá nota

`farol.ats` é um módulo puro: recebe o currículo (ou o texto de um PDF) e devolve
nota, categorias e correções. Sem rede, sem modelo, sem data de hoje, sem
aleatório. Os testes seguram três propriedades: mesma entrada, mesma nota; a
entrada não é alterada; dado malformado não derruba.

Uma nota dada por modelo de linguagem não serviria ao propósito. Ela muda entre
duas execuções sobre o mesmo texto, então não dá para saber se uma correção
melhorou o currículo ou se o modelo só respondeu diferente; custa dinheiro para
quem usa API; e não roda em máquina fraca. A verificação com IA existe, mas como
segunda leitura: o modelo recebe o que as regras já apontaram, para não repetir,
e a instrução o proíbe de atribuir nota.

### 2. O verificador não finge ser um ATS específico

Nenhum ATS publica a pontuação que atribui. O que é público e estável são as
causas de um currículo ser mal lido ou mal ranqueado: layout de duas colunas que
o parser embaralha, PDF sem camada de texto, seção com título que ele não
reconhece, período sem ano, termo da vaga ausente do texto, marcador sem verbo
nem número. A nota mede isso, e a tela diz isso — prometer "compatível com o
Gupy" seria inventar.

Os pesos estão em `ats.CATEGORIES` e em cada verificação. São uma escolha
editorial, não uma medição: conteúdo pesa mais (40) porque é o que decide a
triagem depois que o parser leu, e formato pesa 25 porque é o que impede a
leitura. Mudar um peso é mudar a nota de todo mundo; fica registrado aqui para
que isso seja feito de propósito.

### 3. Falha grave trava a nota

Na primeira versão da régua, um rascunho recém-montado, de setenta palavras e com
`[preencher]` no resumo, tirava 85 e saía como "Pronto para enviar" — as muitas
verificações triviais que ele passava compensavam as poucas, graves, em que
falhava. Média ponderada não expressa "isto não pode ser enviado".

Cinco falhas (`ats.BLOCKERS`) limitam a nota a 64: `[preencher]` esquecido,
e-mail ausente ou inválido, currículo sem experiência nem projeto, texto em
idioma diferente do declarado e PDF sem camada de texto. A tela mostra qual delas
está travando. Pelo mesmo motivo, verificações que passam por ausência ("nenhum
clichê encontrado") não contam num currículo quase vazio.

### 4. O verificador nunca manda inventar

A regra da casa — o app não inventa experiência — vale para a sugestão também.
Termo da vaga ausente do currículo vira "inclua só o que você já usou, e diga
onde", com o caminho para o Roadmap. Um verificador que premiasse a lista de
palavras-chave ensinaria a pessoa a mentir para o robô e a ser desmentida na
entrevista. Há teste para o texto dessa sugestão.

### 5. A folha ao vivo é desenhada no servidor

A oficina envia o formulário para `POST /curriculos/{id}/ao-vivo` a cada pausa na
digitação e recebe o HTML da folha e do painel ATS. O servidor usa
`_resume_sheet.html`, o mesmo parcial da impressão, e não grava nada.

A alternativa — montar a folha em JavaScript — duplicaria o template em duas
linguagens, e as duas versões divergiriam na primeira mudança de modelo: a
pré-visualização mostraria uma coisa e o PDF sairia outra. Como o app roda em
`127.0.0.1`, a ida e volta custa poucos milissegundos.

Salvar continua explícito. Salvamento automático tornaria irreversível desmarcar
um item por engano, e o currículo não tem histórico de versões.

### 6. O PDF continua saindo da impressão do navegador

Gerar o arquivo no servidor exigiria WeasyPrint ou equivalente: dependência com
bibliotecas nativas, difícil de empacotar no executável único de três sistemas. A
impressão do navegador já entrega PDF com texto selecionável, que é exatamente o
que um ATS precisa ler.

### 7. Duas colunas existem, com aviso

O modelo Designer é o único de duas colunas. Ele não foi deixado de fora porque
há caso de uso real — currículo entregue na mão, portfólio —, mas o seletor o
marca como "risco no ATS" e o verificador o reprova no formato, dizendo por quê.
No HTML, a coluna principal vem antes da barra lateral, para que a ordem de
leitura do texto seja a do conteúdo.

## O que ficou de fora

- **Competências agrupadas por categoria no modelo FAANG.** A taxonomia de
  `farol.skills` não tem categoria por skill; criar o mapa só para um modelo
  seria dado novo para manter. O modelo lista as competências em linha.
- **Histórico de versões do currículo.** Derivar um currículo cobre o caso de
  uso (guardar o estado anterior antes de mexer) sem criar outra tabela.
- **Nota por IA.** Ver a decisão 1.
