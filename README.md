# FeedbackLoop — Survey Insights

Análise em lote de respostas abertas de pesquisa de clima. Classifica tema e
sentimento de cada resposta e devolve um resumo executivo com ações recomendadas.

**Aplicação no ar:** https://feedbackloop-prod.onrender.com

[![CI/CD](https://github.com/brunoleao95/feedbackloop-survey-insights/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/brunoleao95/feedbackloop-survey-insights/actions/workflows/ci-cd.yml)

## O problema

Pesquisas de clima têm duas metades. As perguntas fechadas, de nota e múltipla
escolha, qualquer ferramenta agrega. As perguntas abertas, onde a pessoa escreve
o que realmente pensa, ninguém consegue ler.

Uma pesquisa média gera de centenas a milhares de respostas em texto livre. Um
analista de RH passa dias lendo comentário por comentário, e mesmo assim a
leitura sai subjetiva e não escala. O resultado prático é que a parte mais rica
da pesquisa vira a parte que ninguém usa.

## A solução

O sistema recebe as respostas abertas por CSV ou texto colado e devolve, em uma
passada:

1. **Tema** de cada resposta, agregado e contado
2. **Sentimento** de cada resposta: positivo, neutro ou negativo
3. **Resumo executivo** com leitura do cenário e ações recomendadas

Os números do resumo são calculados em código, não pedidos ao modelo. Só o texto
qualitativo vem do LLM. É uma decisão deliberada: modelo de linguagem erra conta,
e contagem de tema é exatamente o que o cliente compra.

Rodando as 36 respostas de exemplo, a saída sai assim:

```
Distribuição de sentimento
  Positivo: 12 (33%)   Neutro: 1 (3%)   Negativo: 23 (64%)

Principais temas
  Liderança: 4      Remuneração: 3        Carga de trabalho: 2
  Ferramentas: 3    Benefícios: 2         Clima organizacional: 2
  Reconhecimento: 3 Home office: 2
```

Custo aproximado por análise das 36 respostas: **US$ 0,03**.

## Como rodar localmente

Requer Python 3.13.2, fixado em `.python-version`.

```bash
git clone https://github.com/brunoleao95/feedbackloop-survey-insights.git
cd feedbackloop-survey-insights
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

A chave do provedor é lida do ambiente. O código **não** carrega `.env`
automaticamente, então exporte a variável antes de subir o app:

```bash
export OPENAI_API_KEY="sua-chave"    # Windows PowerShell: $env:OPENAI_API_KEY="sua-chave"
streamlit run app.py
```

Escolha "Usar dados de exemplo" e clique em Analisar. Sem a chave, o app sobe e a
interface carrega; só a análise falha, com mensagem explícita.

Para rodar a suíte offline, que não chama a API e não consome crédito:

```bash
pytest tests --ignore=tests/smoke -q
```

## Arquitetura

Diagramas C4 completos, nos níveis de contexto, contêineres e componentes, em
[`docs/architecture/`](docs/architecture/c4-contexto-e-containers.md). Em resumo:

```
Analista de RH
      │ HTTPS
      ▼
┌─────────────────────────────────────────┐
│ Render · Oregon                         │
│  ┌───────────────────────────────────┐  │
│  │ app.py            interface       │  │
│  │ feedbackloop/pipeline.py  domínio │  │
│  │ feedbackloop/llm.py       adapter │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
      │ HTTPS
      ▼
Provedor de LLM (fora do Brasil)
```

Um único contêiner, sem banco de dados, execução síncrona em um processo. O
adaptador é o único ponto do código que conhece o provedor: todo o resto usa
apenas `.completar()`, o que torna os testes possíveis sem chamar a API.

**Stack:** Python 3.13.2, Streamlit 1.40, pandas 2.2.3, SDK da OpenAI 1.50, com
`httpx` fixado em 0.27.2. Hospedagem em Render, CI/CD em GitHub Actions.

## Ambientes e publicação

| Ambiente | Branch | URL | Plano |
|---|---|---|---|
| Produção | `main` | https://feedbackloop-prod.onrender.com | pago, não hiberna |
| Desenvolvimento | `dev` | https://feedbackloop-dev.onrender.com | gratuito, hiberna após 15 min |

O auto-deploy nativo da plataforma está **desligado** nos dois serviços. Quem
publica é o pipeline: um push roda os testes, dispara o deploy, aguarda ficar no
ar e então verifica o que foi publicado. O ambiente de destino é escolhido pelo
nome da branch, e cada um usa credenciais próprias. Dev e produção não
compartilham chave.

Tempo do pipeline completo, ponta a ponta: **2m43s**.

Trabalho novo nasce na `dev`, é validado no ambiente de desenvolvimento, e sobe
para a `main` por merge.

## Testes

**Suíte offline**, 7 testes: cobrem parsing, agregação e o fluxo ponta a ponta com
o LLM substituído por um dublê. Rodam em centésimos de segundo e não custam nada.

**Smoke tests**, 4, rodam contra o que foi publicado:

| Teste | O que verifica |
|---|---|
| `test_healthcheck_responde` | o processo está vivo e servindo |
| `test_app_carregou` | a plataforma devolve a página, e não uma tela de erro |
| `test_cadeia_do_llm_construivel` | as dependências do provedor estão íntegras |
| `test_app_importavel_sem_configuracao_extra` | o módulo da interface carrega com o ambiente documentado |

Os dois últimos existem por motivos concretos. O terceiro é regressão de um
defeito de dependência transitiva que atravessou build verde e healthcheck sem
ser detectado. O quarto nasceu de um incidente em que o pipeline reportou sucesso
completo enquanto a aplicação respondia apenas com um traceback. Os dois foram
verificados nos dois sentidos: falham quando o defeito volta, passam quando não.

```bash
SMOKE_URL=https://feedbackloop-prod.onrender.com pytest tests/smoke -v
```

## Limitações conhecidas

Cinco coisas que este sistema ainda não faz, e que você deve saber antes de usá-lo.
O detalhe de cada uma está na [auditoria](docs/auditoria-prototipo.md).

**Dados pessoais vão sem tratamento para o provedor.** As respostas seguem
íntegras para um provedor que processa fora do Brasil, sem anonimização, sem
finalidade declarada e sem base legal registrada. **Não carregue dado real até
que isso seja resolvido.** É a limitação mais séria da lista.

**Nada é persistido.** O resultado vive na sessão do navegador e some quando a
aba fecha. Não há comparação entre trimestres nem trilha de auditoria do que foi
enviado ao provedor.

**Não há cache.** Cada análise faz uma chamada por resposta, mais uma do resumo,
toda vez. Reanalisar a mesma planilha paga de novo. Numa pesquisa de 2.000
respostas, cada execução custa cerca de US$ 1,44.

**Não há observabilidade.** Nenhum log, métrica ou alerta. Pior: os parsers
engolem erro em silêncio e devolvem "neutro" ou "Não classificado", então uma
falha do provedor é indistinguível de um resultado legítimo.

**A agregação se pulveriza.** O prompt pede o tema em aberto, sem taxonomia
fixa. As 36 respostas de exemplo produziram entre 16 e 23 temas distintos, o que
enfraquece justamente a funcionalidade central.

Além disso, a análise roda de forma síncrona em um processo único. Com o volume
de exemplo funciona bem; com milhares de respostas, uma análise longa bloqueia a
aplicação para outros visitantes.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Auditoria do protótipo](docs/auditoria-prototipo.md) | O que foi herdado, com evidência em arquivo e linha |
| [Matriz de decisão de stack](docs/matriz-decisao-stack.md) | Critérios e pesos, definidos antes das notas |
| [ADR-001](docs/adr/adr-001-adocao-da-stack-b.md) | Adoção da stack, com as alternativas descartadas |
| [ADR-002](docs/adr/adr-002-hospedagem-no-render.md) | Escolha de hospedagem e a divisão entre pago e gratuito |
| [Diagramas C4](docs/architecture/c4-contexto-e-containers.md) | Contexto, contêineres e componentes |
| [Post-mortem 29/08](docs/post-mortem-2026-08-29.md) | Indisponibilidade de 4min47s e o rollback |
| [CHANGELOG](CHANGELOG.md) | Histórico de versões |

## Sobre os dados de exemplo

As 36 respostas em `data/respostas-pesquisa-exemplo.csv` são **sintéticas**, e
contêm nomes de pessoas inventados de propósito, para tornar visível o problema
de PII descrito nas limitações. Leia
[`data/AVISO-DADOS-SINTETICOS.md`](data/AVISO-DADOS-SINTETICOS.md) antes de
substituí-las.

## Origem

Este projeto evolui um protótipo herdado, originalmente escrito por Rafael
Crispim (personagem fictício) e distribuído em
[wmonteiro-ai/ai-factory-feedbackloop](https://github.com/wmonteiro-ai/ai-factory-feedbackloop)
como material didático. O commit inicial deste repositório preserva o estado
exato do que foi recebido, antes de qualquer alteração minha, para que o
histórico separe herança de trabalho próprio.

As notas originais de quem saiu estão preservadas em
[`docs/notas-rafael.md`](docs/notas-rafael.md), e a lista de dívidas que ele
deixou foi auditada, verificada e ampliada em
[`docs/auditoria-prototipo.md`](docs/auditoria-prototipo.md).
