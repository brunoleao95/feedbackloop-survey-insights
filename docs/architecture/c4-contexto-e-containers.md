# Arquitetura: diagramas C4

Estes diagramas descrevem o sistema **como ele está publicado hoje**, e não como
eu gostaria que estivesse. Onde falta alguma coisa, a falta aparece desenhada.

Última verificação contra o ambiente real: 29/08/2026, produção rodando o commit
`45f6624` em `https://feedbackloop-prod.onrender.com`.

Notação em Mermaid, usando `flowchart` em vez da sintaxe C4 experimental do
Mermaid, porque o `flowchart` renderiza de forma confiável direto no GitHub. Os
níveis, os elementos e os rótulos seguem o modelo C4: cada caixa traz o nome, o
tipo, a tecnologia e a responsabilidade.

---

## Nível 1: Contexto

Quem usa o sistema, e com quem ele conversa.

```mermaid
flowchart TB
    analista["Analista de RH<br/>[Pessoa]<br/><br/>Trabalha no RH de uma empresa cliente.<br/>Recebe de centenas a milhares de respostas<br/>abertas por pesquisa e nao tem como ler tudo."]

    sistema["FeedbackLoop Survey Insights<br/>[Sistema de software]<br/><br/>Classifica tema e sentimento de cada<br/>resposta aberta e gera um resumo<br/>executivo com acoes recomendadas."]

    llm["Provedor de LLM<br/>[Sistema externo - OpenAI]<br/><br/>Classifica o texto e redige o resumo.<br/>Processa os dados FORA DO BRASIL."]

    analista -->|"Envia as respostas da pesquisa<br/>CSV ou texto colado, via HTTPS"| sistema
    sistema -->|"Devolve distribuicao de sentimento,<br/>temas agregados e resumo executivo"| analista
    sistema -->|"Envia o texto integral de cada resposta<br/>HTTPS, API REST"| llm
    llm -->|"Devolve JSON com tema e sentimento,<br/>e depois o texto do resumo"| sistema

    style llm stroke-dasharray: 5 5
```

**A fronteira que mais importa neste diagrama** é a seta que vai do sistema para
o provedor de LLM. As respostas de pesquisa de clima são dados de funcionários
das empresas clientes, contêm nomes de gestores e queixas identificáveis, e hoje
atravessam essa seta **sem nenhuma anonimização**. Como o provedor processa fora
do Brasil, cada análise é também uma transferência internacional de dados
pessoais, feita sem finalidade declarada e sem base legal registrada.

Está desenhado assim de propósito. É a lacuna 1 da
[auditoria](../auditoria-prototipo.md) e é o que impede o sistema de receber dado
real. Um diagrama que escondesse isso seria mais bonito e menos verdadeiro.

---

## Nível 2: Contêineres

As unidades que rodam separadamente e que precisam ser implantadas, escaladas ou
substituídas de forma independente.

```mermaid
flowchart TB
    analista["Analista de RH<br/>[Pessoa]"]

    subgraph render["Render - regiao Oregon"]
        app["Aplicacao Survey Insights<br/>[Container: Python 3.13.2 + Streamlit 1.40]<br/><br/>Processo unico, uma instancia.<br/>Serve a interface e executa a analise<br/>em lote no mesmo processo.<br/>Nao mantem estado entre sessoes."]
    end

    llm["API do provedor de LLM<br/>[Container externo]<br/><br/>Modelo gpt-5.4-mini.<br/>Uma chamada por resposta,<br/>mais uma para o resumo."]

    analista -->|"HTTPS, porta 443"| app
    app -->|"HTTPS, chat completions<br/>Chave lida de OPENAI_API_KEY"| llm

    style llm stroke-dasharray: 5 5
```

### Por que este diagrama é tão pequeno

Ele tem um contêiner só, e isso é o retrato fiel do sistema, não falta de
detalhe. Não existe banco de dados, não existe fila, não existe serviço de
fundo. Tudo vive dentro de um único processo Python.

As consequências disso são concretas e estão documentadas nos outros artefatos:
o resultado da análise não sobrevive ao fechamento da aba, não há trilha de
auditoria do que foi enviado ao provedor, e o log do Render mostra
`WEB_CONCURRENCY=1`, então uma análise longa bloqueia o aplicativo para qualquer
outro visitante.

Um protótipo que nunca foi separado em contêineres é exatamente o que se espera
de código que nasceu para rodar na máquina de uma pessoa. Separar é trabalho das
etapas seguintes, e o desenho de hoje precisa mostrar o ponto de partida.

---

## Nível 3 (complementar): componentes dentro do contêiner

Fora do que a entrega pede, mas é aqui que se vê a melhor decisão da herança.

```mermaid
flowchart TB
    analista2["Analista de RH<br/>[Pessoa]"]

    subgraph appc["Aplicacao Survey Insights [Container]"]
        ui["app.py<br/>[Componente: Streamlit]<br/><br/>Entrada de dados, disparo da<br/>analise e exibicao do resultado."]
        pipeline["feedbackloop/pipeline.py<br/>[Componente: Python puro]<br/><br/>Orquestra a analise. Funcoes puras<br/>de parsing e agregacao,<br/>testaveis offline."]
        adaptador["feedbackloop/llm.py<br/>[Componente: adaptador]<br/><br/>Unico ponto do codigo que conhece<br/>o provedor. Expoe apenas .completar."]
        csv[("data/respostas-pesquisa-exemplo.csv<br/>[Arquivo empacotado no deploy]<br/><br/>36 respostas sinteticas.")]
    end

    llm2["API do provedor de LLM<br/>[Container externo]"]

    analista2 -->|"HTTPS"| ui
    ui -->|"Le as respostas de exemplo"| csv
    ui -->|"Chama analisar<br/>com a lista de respostas"| pipeline
    pipeline -->|"Chama .completar por resposta<br/>e uma vez para o resumo"| adaptador
    pipeline -->|"Devolve ResultadoAnalise<br/>em memoria"| ui
    adaptador -->|"HTTPS"| llm2

    style llm2 stroke-dasharray: 5 5
```

**O adaptador é a melhor herança do protótipo.** Todo o resto do código conhece
apenas o método `.completar`. É isso que torna os 7 testes offline possíveis sem
chamar a API, e é o que tornaria uma troca de provedor uma mudança localizada em
um arquivo em vez de uma reescrita. O
[ADR-001](../adr/adr-001-adocao-da-stack-b.md) apoia a decisão de manter a stack
justamente nessa separação.

**A fronteira de PII fica visível aqui.** O texto integral de cada resposta
percorre `app.py` para `pipeline.py` para `llm.py` e sai para fora do Brasil, sem
passar por nenhuma etapa de anonimização. Não existe componente entre o pipeline
e o adaptador, e é exatamente esse componente ausente que a lacuna 1 da
[auditoria](../auditoria-prototipo.md) descreve.

---

## Complementar: implantação e fluxo de publicação

Não faz parte dos níveis 1 e 2 do C4, mas sem ele o desenho não é fiel ao que
está no ar: existem **dois** ambientes, e a separação entre eles é o que sustenta
a operação.

```mermaid
flowchart LR
    dev_push(["push em dev"])
    main_push(["merge em main"])

    subgraph gh["GitHub"]
        repo["Repositorio<br/>feedbackloop-survey-insights"]
        actions["GitHub Actions<br/>[Workflow ci-cd.yml]<br/><br/>Testes, deploy e smoke tests.<br/>Escolhe o Environment pela branch."]
        env_dev["Environment: dev<br/>RENDER_SERVICE_ID<br/>SMOKE_URL"]
        env_prod["Environment: prod<br/>RENDER_SERVICE_ID<br/>SMOKE_URL"]
    end

    subgraph render2["Render"]
        svc_dev["feedbackloop-dev<br/>[Plano free]<br/><br/>Hiberna apos 15 min.<br/>OPENAI_API_KEY de dev."]
        svc_prod["feedbackloop-prod<br/>[Plano starter, 7 USD/mes]<br/><br/>Nao hiberna.<br/>OPENAI_API_KEY de producao."]
    end

    dev_push --> repo
    main_push --> repo
    repo --> actions
    actions -->|"branch dev"| env_dev
    actions -->|"branch main"| env_prod
    env_dev -->|"POST /v1/services/.../deploys<br/>e aguarda ficar live"| svc_dev
    env_prod -->|"POST /v1/services/.../deploys<br/>e aguarda ficar live"| svc_prod
    svc_dev -.->|"smoke tests"| actions
    svc_prod -.->|"smoke tests"| actions
```

O auto-deploy nativo do Render está **desligado** nos dois serviços. Quem publica
é o pipeline, e essa escolha está registrada no
[ADR-002](../adr/adr-002-hospedagem-no-render.md): uma plataforma que observa o
repositório não é integração contínua com entrega controlada, é publicação
automática, e as duas coisas falham de formas diferentes.

O mesmo arquivo de workflow atende os dois ambientes. O que muda é o GitHub
Environment escolhido pelo nome da branch, e com ele o serviço de destino e a
chave do provedor. Dev e prod nunca compartilham credencial.
