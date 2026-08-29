# Changelog

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semantico](https://semver.org/lang/pt-BR/).

## [Nao publicado]

### Corrigido
- Cliente do LLM quebrava em tempo de execucao com
  `TypeError: Client.__init__() got an unexpected keyword argument 'proxies'`.
  O `httpx` era dependencia transitiva nao fixada, e a versao 0.28 removeu o
  argumento `proxies` que o `openai 1.50.0` ainda passa. Fixado `httpx==0.27.2`.

### Adicionado
- `.python-version` fixando Python 3.13.2. O ambiente de producao havia
  resolvido para 3.14 enquanto o local usava 3.13.2.

## [v0.2]
- Pipeline movido pro pacote `feedbackloop/` (separação UI x lógica)
- Interface de LLM mockável (`feedbackloop/llm.py`) + testes offline em `tests/`
- Resumo executivo agora junta números calculados em código + texto do modelo
- 36 respostas sintéticas de exemplo em `data/` (com nomes fake pra lição de LGPD)

## [v0.1]
- Versão inicial do protótipo FeedbackLoop Survey Insights
- Streamlit + um modelo GPT pequeno da OpenAI
- Classificação de tema + sentimento por resposta e resumo executivo (Rafael)
