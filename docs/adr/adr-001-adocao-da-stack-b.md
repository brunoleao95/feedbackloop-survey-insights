# ADR-001: Adoção da stack B (Streamlit + Python) para o FeedbackLoop

## Status

Aceito em 2026-08-29.

## Contexto

Assumi o FeedbackLoop, sistema de análise em lote de respostas abertas de
pesquisa de clima, depois da saída do Rafael. O que existe é um protótipo em
Python que roda com `streamlit run app.py` na máquina de quem o escreveu: 918
linhas, com a lógica isolada no pacote `feedbackloop/`, interface de LLM
mockável e 7 testes offline passando. Não tem deploy, não tem CI, não tem
observabilidade e não tem tratamento de PII.

A Bia, Head de People Analytics, precisa que isso saia da máquina de uma pessoa
e vire algo que o time de Produto e um cliente-piloto consigam usar. O
orçamento de infraestrutura e IA é de US$ 120 por mês, e a orientação do
projeto é explícita: aceitar e evoluir o protótipo herdado, nunca reescrever do
zero.

Preciso escolher entre três stacks: A (n8n como orquestrador, hospedado em
PaaS), B (aplicação Python com interface, hospedada em PaaS) e C (Make.com com
Airtable, integração SaaS low-code).

A avaliação está em [`docs/matriz-decisao-stack.md`](../matriz-decisao-stack.md),
com os seis critérios e seus pesos definidos antes de qualquer nota.

## Decisão

Adotar e evoluir a **stack B**: manter Python como linguagem, Streamlit como
interface nesta fase, e o pacote `feedbackloop/` como núcleo de domínio, com
hospedagem em PaaS (decidida no ADR-002).

Na matriz, a stack B somou 475 de 500, contra 330 da A e 195 da C.

## Consequências

**Positivas.** Nenhuma linha do protótipo herdado é descartada: o pacote
`feedbackloop/`, os 7 testes offline e a interface mockável de LLM continuam
válidos e viram a base da suíte de smoke tests. Toda a energia desta fase vai
para o que falta (deploy, pipeline, ambientes, observabilidade) em vez de ser
gasta reproduzindo comportamento que já funciona. O tier gratuito ou barato das
plataformas Python autorizadas mantém o custo de hospedagem próximo de zero,
deixando o orçamento inteiro disponível para as chamadas de LLM, que são o custo
dominante deste sistema.

**Negativas, e são quatro.**

Primeira: o Streamlit não sobrevive ao fim do projeto. A fase final exige uma
aplicação que não pareça protótipo, e uma tela de Streamlit continua parecendo
uma. A lógica de domínio sobrevive à migração, a camada de apresentação não.
Estou adiando esse trabalho conscientemente, não evitando.

Segunda: o pipeline é síncrono e processa uma resposta por vez, bloqueando a
interface. Funciona com as 36 respostas de exemplo e não vai funcionar com a
pesquisa de 2.000 pessoas que o briefing menciona. Escolher stack B não resolve
isso, apenas mantém o problema em código que eu controlo.

Terceira: ao ficar em Python puro, sem orquestrador, eu assumo em código o que a
stack A entregaria pronto: retry, agendamento, histórico de execução por item e
visibilidade de falha por etapa. Isso é trabalho real que passa a ser meu.

Quarta: manter a stack não resolve nenhuma das dívidas herdadas. PII crua indo
para o provedor, ausência de cache, falha silenciosa nos parsers e ausência de
taxonomia fixa continuam exatamente onde estavam. Esta decisão reduz risco de
migração, não risco de produto.

## Alternativas consideradas

**Stack A (n8n hospedado em PaaS).** Foi a alternativa que mais me fez hesitar,
porque ela entregaria de graça justamente o que hoje falta: retry por item,
histórico de execução e visibilidade de erro por etapa. Descartada por duas
razões. A primeira é de natureza do problema: o coração do FeedbackLoop não é um
fluxo disparado por evento, é uma transformação de dados sobre um arquivo que
uma pessoa envia, com uma interface no meio. Modelar isso como workflow seria
forçar a ferramenta. A segunda é de custo de migração: recodar a lógica como nós
visuais descartaria os 7 testes offline, que são hoje a única rede de segurança
do projeto. Nota 2 em esforço de migração na matriz.

**Stack C (Make.com com Airtable).** Descartada com a pior pontuação, 195 de
500, e nota 1 em esforço de migração. Além de exigir a reescrita completa da
lógica como cenários low-code, ela agrava o pior problema da herança: as
respostas são dados de funcionários dos nossos clientes, e movê-las para uma
base low-code de terceiros adiciona mais um operador na cadeia de tratamento
antes de eu sequer ter resolvido a anonimização. A stack C faz sentido quando o
cliente já vive dentro de um SaaS corporativo com conectores nativos, o que não
é o caso aqui.
