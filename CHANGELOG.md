# Changelog

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não publicado]

## [1.0.1] - 2026-08-29

Endurecimento após o incidente de indisponibilidade do mesmo dia. Nenhuma
mudança de comportamento para quem usa a aplicação: o que muda é a capacidade de
detectar defeito antes do usuário.

### Adicionado

- Quarto smoke test, que importa o módulo da interface e executa todo o código de
  nível superior. Verificado nos dois sentidos: falha com o defeito
  reintroduzido, passa sem ele.
- [Post-mortem do incidente](docs/post-mortem-2026-08-29.md), com linha do tempo,
  evidência de execução do rollback e a análise de por que todas as verificações
  automatizadas passaram enquanto a aplicação estava fora.
- README reescrito como entregável: problema, solução, como rodar, arquitetura,
  ambientes, testes e limitações conhecidas.

### Corrigido

- Revertida a leitura de `COLUNA_RESPOSTA` no nível de módulo de `app.py`. A
  variável existia na máquina de desenvolvimento e não nas plataformas, o que
  deixou produção respondendo apenas com `KeyError` por 4 minutos e 47 segundos.
  A dívida original que a mudança tentava resolver segue aberta.

## [1.0.0] - 2026-08-29

Primeira versão do sistema publicada e operável. O protótipo herdado deixa de
depender da máquina de uma pessoa e passa a ter URL pública, publicação
automatizada e verificação do que foi publicado.

### Por que 1.0.0 e não 0.3.0

O salto de MAJOR é deliberado. A mudança de "roda com `streamlit run` na máquina
de quem escreveu" para "está no ar, publica sozinho e é verificável" quebra a
forma de operar o sistema: quem dependia do procedimento anterior não consegue
mais usá-lo daquele jeito, e o contrato de entrega passa a ser outro. Pela regra
do SemVer, quebra de compatibilidade é MAJOR, e a compatibilidade quebrada aqui é
a de operação, não a de API.

### Adicionado

- Publicação em dois ambientes no Render, com serviços, planos e credenciais
  independentes: `feedbackloop-prod` em plano pago, que não hiberna, e
  `feedbackloop-dev` em plano gratuito.
- Pipeline de CI/CD em GitHub Actions (`.github/workflows/ci-cd.yml`). Um push
  na branch dispara testes, publicação e verificação, sem passo manual. O
  ambiente de destino é escolhido pelo nome da branch.
- Três smoke tests em `tests/smoke/`, cobrindo camadas distintas: saúde do
  processo, carregamento da aplicação e integridade da cadeia de dependências do
  provedor de LLM.
- `.python-version` fixando Python 3.13.2.
- `pytest.ini` declarando `pythonpath`, para que os testes importem o pacote
  independentemente de como o pytest é invocado.
- Documentação de decisões: auditoria do protótipo herdado, matriz de decisão de
  stack, ADR-001 (adoção da stack), ADR-002 (hospedagem) e diagramas C4.

### Corrigido

- Cliente do LLM quebrava em tempo de execução com
  `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'`.
  O `httpx` era dependência transitiva não fixada, e a versão 0.28 removeu o
  argumento `proxies` que o `openai 1.50.0` ainda passa. Fixado `httpx==0.27.2`.
  O defeito atravessou build bem-sucedido, serviço marcado como `live` e sete
  testes verdes sem ser detectado.
- Passo de publicação do pipeline tratava resposta vazia da API do Render como
  falha. A API responde assim quando enfileira um deploy atrás de outro em
  andamento, então o pipeline ficava vermelho enquanto a publicação corria
  normalmente. Agora ele localiza o deploy pelo commit do run.

### Segurança

- Auto-deploy nativo da plataforma desligado nos dois serviços. A publicação
  passa pelo pipeline, que roda os testes antes.
- Credenciais separadas por ambiente: cada serviço tem a sua `OPENAI_API_KEY` e
  cada GitHub Environment tem o seu `RENDER_SERVICE_ID`. Dev e produção não
  compartilham chave.
- Histórico do repositório verificado quanto a segredos antes da publicação.

### Conhecido e não resolvido

Registrado aqui porque omitir seria pior do que admitir. Ver
[a auditoria](docs/auditoria-prototipo.md) para o detalhe de cada item.

- Respostas de pesquisa vão para o provedor de LLM sem anonimização, e o
  provedor processa fora do Brasil. O sistema não deve receber dado real até que
  isso seja tratado.
- Nenhum resultado é persistido. Fechou a aba, perdeu a análise.
- Nenhum cache. Reanalisar a mesma planilha paga de novo.
- Sem logs, métricas ou rastreio. Falhas de parsing são engolidas em silêncio.
- Sem taxonomia fixa de temas, o que pulveriza a agregação: as 36 respostas de
  exemplo produziram entre 16 e 23 temas distintos.

## [0.2.0] - protótipo herdado

- Pipeline movido pro pacote `feedbackloop/` (separação UI x lógica)
- Interface de LLM mockável (`feedbackloop/llm.py`) + testes offline em `tests/`
- Resumo executivo agora junta números calculados em código + texto do modelo
- 36 respostas sintéticas de exemplo em `data/` (com nomes fake pra lição de LGPD)

## [0.1.0] - protótipo herdado

- Versão inicial do protótipo FeedbackLoop Survey Insights
- Streamlit + um modelo GPT pequeno da OpenAI
- Classificação de tema + sentimento por resposta e resumo executivo (Rafael)

[Não publicado]: https://github.com/brunoleao95/feedbackloop-survey-insights/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/brunoleao95/feedbackloop-survey-insights/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/brunoleao95/feedbackloop-survey-insights/releases/tag/v1.0.0
