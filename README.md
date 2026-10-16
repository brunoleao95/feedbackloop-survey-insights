# FeedbackLoop — Survey Insights

Análise em lote de respostas abertas de pesquisa de clima. Classifica tema e
sentimento de cada resposta e devolve um resumo executivo com ações recomendadas.
Os dados pessoais são mascarados antes de qualquer envio ao provedor de LLM.

**Aplicação no ar:** https://feedbackloop-prod.onrender.com

[![CI/CD](https://github.com/brunoleao95/feedbackloop-survey-insights/actions/workflows/ci-cd.yml/badge.svg?branch=main)](https://github.com/brunoleao95/feedbackloop-survey-insights/actions/workflows/ci-cd.yml)
[![Monitor de produção](https://github.com/brunoleao95/feedbackloop-survey-insights/actions/workflows/monitor.yml/badge.svg)](https://github.com/brunoleao95/feedbackloop-survey-insights/actions/workflows/monitor.yml)

**Observabilidade, sem login:**
[um trace real de produção no Langfuse](https://cloud.langfuse.com/project/cmvazqcvr01hfad0kifd23oag/traces/16aadd310862ab953ccc90815bbdbaf7),
com as 37 chamadas ao modelo, latência, custo e os nomes já substituídos por
`[PESSOA]`.

## Sumário

- [O problema e a solução](#o-problema-e-a-solução)
- [Stack](#stack)
- [Como rodar](#como-rodar)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Deploy](#deploy)
- [Operação](#operação)
- [Otimizações](#otimizações)
- [Troubleshooting](#troubleshooting)
- [LGPD](#lgpd)
- [Limitações conhecidas](#limitações-conhecidas)
- [Documentação](#documentação)
- [Como contribuir](#como-contribuir)
- [Licença](#licença)
- [Autores](#autores)

## O problema e a solução

Pesquisas de clima têm duas metades. As perguntas fechadas qualquer ferramenta
agrega. As abertas, onde a pessoa escreve o que realmente pensa, ninguém consegue
ler: uma pesquisa média gera de centenas a milhares de respostas em texto livre,
e o analista de RH passa dias lendo comentário por comentário.

O sistema recebe as respostas por CSV ou texto colado e devolve, em uma passada:

1. **Tema** de cada resposta, agregado e contado
2. **Sentimento** de cada resposta: positivo, neutro ou negativo
3. **Resumo executivo** com leitura do cenário e ações recomendadas

Os números do resumo são calculados em código, não pedidos ao modelo. Só o texto
qualitativo vem do LLM: modelo de linguagem erra conta, e contagem de tema é
exatamente o que o cliente compra.

Com as 36 respostas de exemplo, uma análise custa **US$ 0,0088** e leva de 30 a
57 segundos. Repetida dentro de 24 horas, custa **zero** e leva **3 milissegundos**.

## Stack

| Camada | Escolha | Por quê |
|---|---|---|
| Linguagem | Python 3.13.2, fixado em `.python-version` | Ver [ADR-001](docs/adr/adr-001-adocao-da-stack-b.md) |
| Interface | Streamlit 1.40 | Herdada do protótipo, suficiente para o uso |
| Dados | pandas 2.2.3 | Leitura do CSV |
| LLM | OpenAI, modelo `gpt-5.4-mini`, SDK 1.50 com `httpx` 0.27.2 fixado | O adaptador em `feedbackloop/llm.py` é o único ponto que conhece o provedor |
| Observabilidade | Langfuse Cloud, região UE, SDK 5.0.2 | Ver [ADR-003](docs/adr/adr-003-observabilidade-com-langfuse.md) |
| Cache | SQLite, da biblioteca padrão | Sem serviço a mais. Ver [a otimização](docs/otimizacao/cache.md) |
| Hospedagem | Render, Oregon | Ver [ADR-002](docs/adr/adr-002-hospedagem-no-render.md) |
| CI/CD e alerta | GitHub Actions | Pipeline de publicação e monitor de produção |

Todas as dependências, inclusive as transitivas que já quebraram o sistema uma
vez, estão fixadas em `requirements.txt` com o motivo ao lado.

```
Analista de RH ──HTTPS──▶ Render: app.py ─▶ pipeline.py ─▶ pii.py (sanitiza)
                                               │      └──▶ cache.py (SQLite, 24 h)
                                               ▼
                                            llm.py ──HTTPS──▶ OpenAI (fora do Brasil)
                                               │
                                               └─ observabilidade.py ──▶ Langfuse (UE, mascarado)
```

Diagramas C4 completos em
[`docs/architecture/`](docs/architecture/c4-contexto-e-containers.md).

## Como rodar

```bash
git clone https://github.com/brunoleao95/feedbackloop-survey-insights.git
cd feedbackloop-survey-insights
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # e preencha OPENAI_API_KEY
streamlit run app.py
```

O `app.py` carrega o `.env` sozinho. Escolha "Usar dados de exemplo" e clique em
Analisar. Sem a chave, a interface carrega e só a análise falha, com mensagem
explícita. Sem as chaves do Langfuse, a telemetria fica desligada e o resto
funciona igual.

**Testes offline**, 40, que não chamam a API e não custam nada:

```bash
pytest tests --ignore=tests/smoke -q
```

Cobrem o pipeline, a sanitização (incluindo um cliente espião que falha se
qualquer nome chegar ao provedor), a máscara da telemetria e o cache, com um
relógio falso que avança 24 horas para provar que a exclusão apaga de fato.

**Smoke tests**, 4, contra o que está publicado:

```bash
SMOKE_URL=https://feedbackloop-prod.onrender.com pytest tests/smoke -v
```

## Variáveis de ambiente

| Nome | Obrigatória | Exemplo | Descrição |
|---|---|---|---|
| `OPENAI_API_KEY` | **Sim**, para analisar | `sk-...` | Chave da OpenAI. **Segredo.** Uma por ambiente |
| `LANGFUSE_PUBLIC_KEY` | Não | `pk-lf-...` | Chave pública do projeto no Langfuse. Sem o par, a telemetria fica desligada |
| `LANGFUSE_SECRET_KEY` | Não | `sk-lf-...` | Chave secreta do Langfuse. **Segredo** |
| `LANGFUSE_BASE_URL` | Não | `https://cloud.langfuse.com` | Região do projeto no Langfuse. Este projeto está na UE |
| `LANGFUSE_TRACING_ENVIRONMENT` | Não | `prod` | Rótulo do ambiente nos traces: `local`, `dev` ou `prod`. Padrão `local` |
| `CACHE_PATH` | Não | `/tmp/feedbackloop-cache.sqlite3` | Arquivo do cache. Padrão: diretório temporário do sistema |
| `CACHE_TTL_SEGUNDOS` | Não | `86400` | Prazo de retenção do cache. Padrão 24 horas. Não aumente sem revisar a [política de retenção](docs/lgpd/retencao-e-exclusao.md) |
| `SMOKE_URL` | Só nos smoke tests | `https://feedbackloop-dev.onrender.com` | Alvo dos smoke tests. Não é lida pela aplicação |

Localmente, os valores ficam no `.env`, que está no `.gitignore`. O
[`.env.example`](.env.example) documenta todas, sem nenhum valor real. Em dev e
produção, ficam no painel de cada serviço no Render, com valores diferentes por
ambiente: **dev e produção não compartilham nenhuma chave**. Inventário,
procedimento de rotação e auditoria do histórico do Git com `gitleaks` em
[`docs/seguranca/rotacao-de-credenciais.md`](docs/seguranca/rotacao-de-credenciais.md).

## Deploy

| Ambiente | Branch | URL | Plano |
|---|---|---|---|
| Produção | `main` | https://feedbackloop-prod.onrender.com | pago, não hiberna |
| Desenvolvimento | `dev` | https://feedbackloop-dev.onrender.com | gratuito, hiberna após 15 min |

O auto-deploy da plataforma está **desligado**. Quem publica é o pipeline em
`.github/workflows/ci-cd.yml`: um push roda os testes, dispara o deploy pela API
do Render, aguarda o serviço ficar no ar e roda os smoke tests contra o que foi
publicado. O ambiente de destino sai do nome da branch. Leva cerca de 3 minutos.

Trabalho novo nasce na `dev`, é validado no ambiente de desenvolvimento e sobe
para a `main` por merge.

**Rollback:** pelo painel do Render, em *Deploys*, escolher o último deploy bom e
*Rollback*. No incidente de 29/08 levou 26 segundos. Depois, `git revert` do
commit que causou o problema, porque o rollback da plataforma não desfaz o commit.
Ver o [post-mortem](docs/post-mortem-2026-08-29.md).

## Operação

Cinco métricas, cada uma com linha de base medida e limite justificado. O
detalhe, com o porquê de cada número, está em
[`docs/operacao/metricas-e-alertas.md`](docs/operacao/metricas-e-alertas.md).

| Métrica | Linha de base | Limite |
|---|---|---|
| Latência por chamada | p50 1,05 s · p95 2,06 s · p99 3,38 s | p95 > 4 s (P3), > 8 s (P2) |
| Custo por análise | US$ 0,0088 | > US$ 0,02 por análise ou > US$ 3,70 por dia (P2) |
| Erro | 0 em 111 chamadas | qualquer smoke test falhando (P1) · > 2% das chamadas ou > 5% fora do formato (P2) |
| Volume | 77 unidades do Langfuse por análise | 30 mil no mês, 60% da cota (P3) |
| Qualidade | formato válido 1,00 · pulverização 0,639 | < 0,95 (P2) · > 0,75 (P3) |

**Alerta configurado (P1).** O workflow
[`monitor.yml`](.github/workflows/monitor.yml) roda os 4 smoke tests contra
produção a cada 30 minutos. Se algum falha, abre uma issue com o rótulo
`alerta-p1`, notificada por e-mail. Se a falha persiste, comenta na mesma issue.
A primeira verificação que passa fecha a issue. Testado em 16/10/2026: apontado
para um endereço que não é a aplicação, abriu a issue #1; na execução seguinte,
contra produção, fechou.

**Painéis.**

| Painel | Onde |
|---|---|
| Latência, custo e uso | Langfuse, projeto FeedbackLoop, filtro `environment = prod` |
| Trace público de exemplo | [análise de 36 respostas em produção](https://cloud.langfuse.com/project/cmvazqcvr01hfad0kifd23oag/traces/16aadd310862ab953ccc90815bbdbaf7) |
| Memória e CPU | Render, serviço `feedbackloop-prod`, aba Metrics |
| Disponibilidade | [Actions, workflow *Monitor de producao*](https://github.com/brunoleao95/feedbackloop-survey-insights/actions/workflows/monitor.yml) |

Cada análise gera um trace com a árvore completa: a sanitização, cada
classificação e o resumo, e nos metadados as contagens de PII mascarada, a taxa
de formato válido, a pulverização de temas e a taxa de acerto do cache.

## Otimizações

**Cache das respostas do LLM**, com prazo de 24 horas.
Detalhe em [`docs/otimizacao/cache.md`](docs/otimizacao/cache.md).

Medido em produção, nas mesmas 36 respostas, pelos traces do Langfuse:

| | Antes: sem cache | Depois: 1ª análise | **Depois: análise repetida** |
|---|---|---|---|
| Latência da análise | 37,5 s | 29,6 s | **0,003 s** |
| Chamadas ao provedor | 37 | 37 | **0** |
| Custo | US$ 0,0089 | US$ 0,0087 | **US$ 0** |
| Observações no Langfuse | 76 | 76 | **2** |

**O que estes números não dizem.** A primeira análise não ficou mais rápida por
causa do cache: a diferença é variação do provedor, que já oscilava de 34 s a
57 s. O ganho só existe quando a mesma planilha é analisada de novo.

**O trade-off.** O cache escolhe latência e custo, e paga em qualidade: o
resultado fica congelado por até 24 horas e o resumo deixa de variar entre
execuções. Uma falha de formato nunca é guardada, para não ser repetida. A chave
inclui o modelo e o prompt, então trocar qualquer um invalida o cache sozinho.

## Troubleshooting

**1. A análise falha com erro de autenticação do provedor.**
`OPENAI_API_KEY` ausente, errada ou revogada. Localmente, confira o `.env`. No
Render, troque o valor no serviço e veja o item 2.

**2. Mudei uma variável no Render e nada mudou.**
Salvar variável no painel **não reinicia o processo**. É preciso disparar um
deploy: pelo painel, em *Manual Deploy*, ou por um novo push na branch.

**3. Nenhum trace aparece no Langfuse.**
Os nomes são exatos: `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY`. Uma variável
chamada `LANGFUSE_API_KEY`, por exemplo, é ignorada sem erro. Confira também se
`LANGFUSE_BASE_URL` aponta para a região do projeto, e o item 2.

**4. Traces de produção aparecem com o ambiente `dev`.**
`LANGFUSE_TRACING_ENVIRONMENT` foi copiado de um serviço para o outro. É a única
variável que precisa ter valor diferente sem ser segredo. Corrija e faça o deploy.

**5. O ambiente de desenvolvimento demora quase um minuto para abrir.**
Esperado. O plano gratuito hiberna depois de 15 minutos sem acesso, e o primeiro
acesso acorda o serviço. Produção não hiberna.

**6. A análise fica lenta ou começa a falhar no meio.**
Provável limite de requisições por minuto do provedor (erro 429). Uma análise de
36 respostas faz cerca de 55 chamadas por minuto, e umas 9 análises simultâneas
esbarram no limite. Veja a métrica de erro nos traces e a página de status da
OpenAI.

**7. Reanalisei a planilha e o resultado veio idêntico, instantâneo.**
É o cache funcionando. A interface avisa quantas etapas vieram dele. Para forçar
uma análise nova, apague o arquivo em `CACHE_PATH` e reinicie o app. Em produção,
qualquer deploy esvazia o cache, porque o disco do serviço é efêmero.

**8. O `pip install` avisa conflito de `protobuf`.**
O Langfuse puxa `protobuf` 7, e o Streamlit 1.40 exige menos que 6. Use o
`requirements.txt` como está: a versão 5.29.6 e as do OpenTelemetry estão fixadas
por isso. Ao atualizar o Langfuse, confira essa compatibilidade antes.

**9. O primeiro pipeline depois de mudar dependências demora uns 6 minutos.**
O build instala tudo sem cache de pacotes. Os seguintes voltam para cerca de 3
minutos. Não é falha, e o smoke test espera o serviço subir.

**10. Uma issue `alerta-p1` foi aberta.**
Siga o
[procedimento de resposta](docs/operacao/metricas-e-alertas.md#procedimento-de-resposta-ao-p1):
o nome do teste que falhou diz a camada do problema, e se a falha começou logo
depois de um deploy, o caminho mais rápido é o rollback.

## LGPD

**A FeedbackLoop é operadora.** A empresa cliente é a controladora dos dados dos
seus colaboradores. O tratamento se apoia no legítimo interesse, Art. 7º, IX, e
cada análise é uma transferência internacional, Art. 33, porque o provedor de LLM
processa fora do Brasil.

**O que o sistema faz para proteger o titular:**

- **Sanitização antes do LLM.** Nomes, e-mail, CPF e telefone são substituídos
  por `[PESSOA]`, `[EMAIL]`, `[CPF]` e `[TELEFONE]` em `feedbackloop/pii.py`,
  antes de qualquer chamada. Nas respostas de exemplo, os 4 nomes plantados são
  mascarados, sem falso positivo. A interface mostra ao analista exatamente o que
  foi enviado
- **Telemetria mascarada.** O cliente do Langfuse aplica a mesma sanitização, e
  mais um filtro de chaves de API, a tudo que exporta
- **Minimização.** Só a coluna `resposta` é lida. Nenhuma resposta é gravada em
  disco. O cache guarda só tema, sentimento e resumo, sob uma chave em hash
- **Retenção com mecanismo real.** O cache expira em 24 horas por um `DELETE` em
  SQL executado pelo próprio sistema, testado com relógio falso

**Documentos:** [mapa de dados pessoais](docs/lgpd/mapa-de-dados.md), com os 7
pontos de tratamento e a base legal de cada um, e
[política de retenção e exclusão](docs/lgpd/retencao-e-exclusao.md), com os 6
lugares onde algum dado existe, por quanto tempo e quem apaga.

**Riscos abertos, registrados nos documentos acima:** relato de saúde numa
resposta é dado sensível, Art. 11, que o legítimo interesse não cobre; e o
registro de acesso exigido pelo Marco Civil, Art. 15, é de 6 meses, enquanto o
plano atual do Render guarda 7 dias.

## Limitações conhecidas

O que a versão 1.0 apontava e esta versão resolveu: dado pessoal indo sem
tratamento ao provedor, ausência de observabilidade e ausência de cache. O que
continua aberto:

- **A agregação se pulveriza.** Sem taxonomia fixa, as 36 respostas de exemplo
  produzem 23 temas distintos. A métrica de pulverização mede isso, mas não
  resolve
- **A sanitização é por regra, não por modelo.** Nome escrito só em minúsculas,
  ou apelido, passa. O teste cobre os casos de exemplo, não todos os possíveis
- **Só o alerta P1 é automático.** Os limites de latência, custo e qualidade
  são verificados nos painéis
- **A análise é síncrona.** Com milhares de respostas, uma análise longa bloqueia
  a aplicação para outros visitantes
- **Nada é histórico.** O resultado some quando a aba fecha, e o cache não
  substitui um histórico: ele expira e é esvaziado a cada deploy

As 36 respostas em `data/respostas-pesquisa-exemplo.csv` são **sintéticas**, com
nomes inventados de propósito. Leia
[`data/AVISO-DADOS-SINTETICOS.md`](data/AVISO-DADOS-SINTETICOS.md) antes de
substituí-las.

## Documentação

| Documento | Conteúdo |
|---|---|
| [Auditoria do protótipo](docs/auditoria-prototipo.md) | O que foi herdado, com evidência em arquivo e linha |
| [Matriz de decisão de stack](docs/matriz-decisao-stack.md) | Critérios e pesos, definidos antes das notas |
| [ADR-001](docs/adr/adr-001-adocao-da-stack-b.md) | Adoção da stack |
| [ADR-002](docs/adr/adr-002-hospedagem-no-render.md) | Hospedagem e a divisão entre pago e gratuito |
| [ADR-003](docs/adr/adr-003-observabilidade-com-langfuse.md) | Observabilidade com Langfuse |
| [Diagramas C4](docs/architecture/c4-contexto-e-containers.md) | Contexto, contêineres e componentes |
| [Mapa de dados pessoais](docs/lgpd/mapa-de-dados.md) | Pontos de tratamento e base legal |
| [Retenção e exclusão](docs/lgpd/retencao-e-exclusao.md) | Onde cada dado existe e quem apaga |
| [Rotação de credenciais](docs/seguranca/rotacao-de-credenciais.md) | Inventário, procedimento e auditoria do histórico |
| [Métricas e alertas](docs/operacao/metricas-e-alertas.md) | Linha de base, limites, alerta P1 e painéis |
| [Otimização com cache](docs/otimizacao/cache.md) | Antes e depois, trade-off e como reproduzir |
| [Post-mortem 29/08](docs/post-mortem-2026-08-29.md) | Indisponibilidade de 4min47s e o rollback |
| [CHANGELOG](CHANGELOG.md) | Histórico de versões |

## Como contribuir

1. Crie a branch a partir da `dev`
2. Rode `pytest tests --ignore=tests/smoke -q` antes de abrir o PR
3. Abra o PR para a `dev`. O pipeline publica no ambiente de desenvolvimento
4. Depois de validar em dev, a `dev` sobe para a `main` por merge
5. Nunca commite `.env` nem valor de chave. Variável nova entra no `.env.example`
   e na tabela de variáveis acima
6. Mudança que passe a guardar qualquer dado, ou que altere o que vai para o
   provedor, atualiza também o [mapa de dados](docs/lgpd/mapa-de-dados.md) e a
   [política de retenção](docs/lgpd/retencao-e-exclusao.md)

O histórico segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## Licença

[MIT](LICENSE), a mesma do protótipo de origem.

## Autores

**Bruno Leão** — evolução do protótipo em produto, desde a versão 1.0.0.

O protótipo herdado foi escrito por Rafael Crispim (personagem fictício) e
distribuído em
[wmonteiro-ai/ai-factory-feedbackloop](https://github.com/wmonteiro-ai/ai-factory-feedbackloop)
como material didático da disciplina AI Factory, da PUCPR. O commit inicial deste
repositório preserva o estado exato do que foi recebido, para que o histórico
separe herança de trabalho próprio. As notas originais estão em
[`docs/notas-rafael.md`](docs/notas-rafael.md).
