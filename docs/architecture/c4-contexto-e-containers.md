# Arquitetura: diagramas C4, níveis 1 e 2

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

O que existe dentro do sistema, e como as partes conversam.

```mermaid
flowchart TB
    analista["Analista de RH<br/>[Pessoa]"]

    subgraph render["Render - regiao Oregon"]
        app["Aplicacao Survey Insights<br/>[Container: Python 3.13.2 + Streamlit 1.40]<br/><br/>Processo unico, uma instancia.<br/>Serve a interface e executa a analise<br/>em lote no mesmo processo."]

        subgraph interno["Dentro do processo"]
            ui["app.py<br/>[Modulo: Streamlit]<br/><br/>Entrada de dados, disparo da analise<br/>e exibicao do resultado."]
            pipeline["feedbackloop/pipeline.py<br/>[Modulo: Python puro]<br/><br/>Orquestra a analise. Funcoes puras de<br/>parsing e agregacao, testaveis offline."]
            adaptador["feedbackloop/llm.py<br/>[Modulo: adaptador]<br/><br/>Unico ponto que conhece o provedor.<br/>Expoe apenas .completar."]
        end

        csv[("data/respostas-<br/>pesquisa-exemplo.csv<br/>[Arquivo no repositorio]<br/><br/>36 respostas sinteticas.<br/>Unico dado que acompanha o deploy.")]
    end

    llm["API do provedor de LLM<br/>[Sistema externo]<br/><br/>Modelo gpt-5.4-mini.<br/>Uma chamada por resposta,<br/>mais uma para o resumo."]

    analista -->|"HTTPS"| app
    ui -->|"Le as respostas"| csv
    ui -->|"Chama analisar com a lista de respostas"| pipeline
    pipeline -->|"Chama .completar por resposta<br/>e uma vez para o resumo"| adaptador
    adaptador -->|"HTTPS, chat completions<br/>Chave lida de OPENAI_API_KEY"| llm
    pipeline -->|"Devolve ResultadoAnalise<br/>em memoria"| ui

    style llm stroke-dasharray: 5 5
    style interno fill:none,stroke-dasharray: 3 3
```

### O que este nível revela

**Não existe banco de dados, e isso não é omissão do desenho.** O sistema não
persiste nada: o resultado vive no estado da sessão do Streamlit e desaparece
quando a aba fecha. Não há como comparar a pesquisa deste trimestre com a do
anterior, que é a promessa central de um produto de people analytics, e não há
trilha de auditoria do que foi enviado ao provedor. É a lacuna 2 da auditoria.

**Um processo, uma instância, execução síncrona.** O log do Render mostra
`WEB_CONCURRENCY=1`. A análise roda no mesmo processo que serve a interface, uma
resposta por vez. Com as 36 respostas de exemplo funciona; com as milhares que o
briefing menciona, uma análise longa bloqueia o aplicativo para qualquer outro
visitante. É a consequência negativa que o [ADR-001](../adr/adr-001-adocao-da-stack-b.md)
assume explicitamente.

**O adaptador é a melhor herança do protótipo.** Todo o resto do código conhece
apenas o método `.completar`. É isso que torna os testes possíveis sem chamar a
API, e é o que tornaria uma troca de provedor uma mudança localizada em um
arquivo em vez de uma reescrita.

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
