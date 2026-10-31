# ADR-004: Interface web própria com FastAPI, no lugar do Streamlit

## Status

Aceito em 2026-10-31.

## Contexto

A interface herdada do protótipo era um script Streamlit de 160 linhas. Ela
cumpriu o papel nas etapas 1 e 2, mas tinha quatro problemas que pesam quando o
sistema deixa de ser demonstração e passa a ser usado por clientes:

1. **Parece protótipo.** O layout é o padrão do Streamlit, com pouco controle
   sobre hierarquia visual. O que a liderança precisa ver primeiro, os
   indicadores e o resumo, ficava abaixo da entrada de dados.
2. **Não dá retorno durante a análise.** Uma análise de 36 respostas leva de 30
   a 57 segundos, e o Streamlit mostrava só um indicador girando. Para quem
   espera, meio minuto sem progresso parece travamento.
3. **Não tem API.** A regra de negócio só era alcançável clicando na página.
   Nenhuma integração futura com o produto principal da FeedbackLoop seria
   possível sem reescrever a entrada.
4. **Dependências pesadas e com conflito.** O Streamlit trazia pandas e exigia
   `protobuf<6`, o que já tinha obrigado a fixar transitivas do Langfuse.

O enunciado da etapa final pede que uma aplicação feita somente em Streamlit
migre para um site de verdade.

## Decisão

Substituir o Streamlit por um servidor **FastAPI** em `app.py`, servido por
**uvicorn**, e uma página própria em `static/`, com HTML, CSS e JavaScript sem
framework e sem dependência externa.

A API expõe quatro rotas: `/saude`, `/api/exemplo`, `/api/csv` e
`/api/analisar`. A análise responde em **NDJSON**, uma linha por evento, e cada
resposta classificada vira um evento de progresso. O último evento traz o
resultado ou o erro.

**O pacote `feedbackloop/` não mudou de contrato.** A única alteração foi um
parâmetro opcional, `ao_progredir`, em `analisar()`. Sanitização, cache,
observabilidade e os 40 testes existentes seguiram iguais.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Manter o Streamlit e customizar o tema | Resolve parte do problema 1 e nenhum dos outros três |
| Next.js ou React com backend separado | Dois serviços, dois deploys e um build de Node, para uma página. O orçamento e o tamanho do time não justificam |
| Flask | Funcionaria. O FastAPI dá validação de entrada com Pydantic e resposta em streaming com menos código |
| Server-Sent Events em vez de NDJSON | Exige `GET` ou um cliente específico para `POST`. NDJSON funciona com `fetch` e um leitor de fluxo |

## Consequências

**Positivas.**
- A página mostra o andamento real: "Classificando resposta 12 de 36".
- O resultado ganha indicadores, distribuição de sentimento por tema, filtro
  por tema e sentimento, e download em CSV. O download resolve o "fechou a aba,
  perdeu o resultado" sem o servidor guardar nada.
- Existe uma API que outro sistema pode chamar.
- Saem o Streamlit e o pandas. O CSV passa a ser lido com o módulo `csv` da
  biblioteca padrão, e só a coluna `resposta`.
- A entrada ganhou limites explícitos: até 300 respostas por análise e 2.000
  caracteres por resposta. Sem teto, uma planilha grande prenderia o processo
  por minutos e consumiria o orçamento do mês numa requisição.

**Negativas.**
- Mais código de interface para manter: cerca de 250 linhas de JavaScript que
  antes o Streamlit gerava.
- O texto do modelo é exibido com um conversor de Markdown mínimo, escrito à
  mão, que escapa todo o HTML antes de formatar. Ele cobre parágrafos, listas,
  títulos e negrito, e nada mais.
- O comando de início no Render mudou, e precisa ser trocado no painel de cada
  serviço antes do deploy: `uvicorn app:app --host 0.0.0.0 --port $PORT`.

**O que continua igual.** A análise ainda é síncrona dentro do processo, numa
thread por requisição. O streaming melhora a percepção de espera, mas não muda o
limite de capacidade registrado no ADR-002.
