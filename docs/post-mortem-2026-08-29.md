# Post-mortem: produção indisponível por variável de ambiente ausente

**Data do incidente:** 29/08/2026
**Duração:** 4 minutos e 47 segundos de indisponibilidade total
**Severidade:** alta. A aplicação respondia apenas com um traceback
**Ambiente afetado:** produção (`feedbackloop-prod`)
**Natureza:** exercício controlado de falha, com rollback executado de verdade

Este documento analisa causa, não culpado. As decisões descritas aqui foram
tomadas com a informação disponível no momento, e o objetivo é entender por que
o sistema permitiu que isso chegasse ao usuário.

## Resumo

Uma mudança que resolvia uma dívida técnica conhecida introduziu a leitura de uma
variável de ambiente no nível de módulo de `app.py`. A variável existia na
máquina de desenvolvimento e não foi configurada nas plataformas. Produção passou
a responder apenas com `KeyError: 'COLUNA_RESPOSTA'`.

O que torna o caso relevante não é o defeito, que é banal. É que **todas as
verificações automatizadas passaram**: sete testes unitários, três smoke tests e
o healthcheck. O pipeline reportou sucesso completo enquanto a aplicação estava
inutilizável.

## Linha do tempo

Horários em UTC.

| Horário | Evento |
|---|---|
| 16:32:04 | Deploy `dep-da9gidmk1f9s73fc6gt0` fica `live`. Estado bom, commit `5185afa4`, versão v1.0.0 |
| 16:33 | Commit `abd7bed` na `dev`: coluna de resposta passa a vir de variável de ambiente |
| 16:33 | Promoção para `main`, commit de merge `53646d5e` |
| 16:35:15 | Deploy `dep-da9gk0m7bikc73997gb0` fica `live`. **Produção quebra neste instante** |
| 16:35 | Pipeline conclui com **sucesso em todos os três jobs** |
| 16:37:04 | Verificação manual: `GET /` responde HTTP 200, healthcheck responde `ok`, e a página exibe apenas o traceback |
| 16:37:05 | Rollback disparado: `POST /v1/services/.../rollback` para o deploy `dep-da9gidmk1f9s73fc6gt0` |
| 16:37:31 | Deploy `dep-da9glggn74is7382m4tg` fica `live`, com `trigger: rollback`. **Serviço restaurado** |
| 16:40 | `git revert` do commit defeituoso, porque o rollback de plataforma não desfaz o commit |

**Tempo de detecção:** 1 minuto e 49 segundos, e apenas porque havia uma pessoa
olhando. Nenhum sinal automatizado indicou o problema.
**Tempo de recuperação após a decisão:** 26 segundos.

## Evidência de execução do rollback

Resposta da API do Render ao disparar o rollback:

```json
{
  "id": "dep-da9glggn74is7382m4tg",
  "commit": {
    "id": "5185afa4c3724af23ab1ae5f4552fb4eba72871b",
    "message": "chore: promove dev para main\n\nPrepara o CHANGELOG da v1.0.0."
  },
  "status": "update_in_progress",
  "trigger": "rollback",
  "createdAt": "2026-08-29T16:37:22.738312Z"
}
```

Estado dos deploys logo após a conclusão:

```
dep-da9glggn74is7382m4tg  live         trigger=rollback   commit 5185afa4
dep-da9gk0m7bikc73997gb0  deactivated  trigger=api        commit 53646d5e
dep-da9gidmk1f9s73fc6gt0  deactivated  trigger=api        commit 5185afa4
```

Verificação da aplicação antes e depois:

```
antes  16:37:04   GET /  -> HTTP 200, pagina exibe KeyError: 'COLUNA_RESPOSTA'
depois 16:37:35   GET /  -> HTTP 200 em 0.284s, aplicacao completa carregada
```

Note que **o código HTTP é 200 nos dois momentos**. Esse detalhe é o centro deste
post-mortem.

## Causa raiz

A causa imediata é uma variável de ambiente lida sem valor padrão em código de
nível de módulo, configurada em um ambiente e não nos outros.

A causa raiz é outra: **a aplicação não tinha nenhuma verificação que executasse
o próprio `app.py`**.

As três camadas de verificação existentes olhavam para lugares onde o defeito não
estava:

| Verificação | O que ela realmente testa | Por que passou |
|---|---|---|
| 7 testes unitários | pacote `feedbackloop/` | Nunca importam `app.py` |
| Smoke: healthcheck | processo do Streamlit vivo | O servidor sobe mesmo com o script quebrado |
| Smoke: página carregou | presença de marcadores no HTML | O HTML de casca é servido antes de o script rodar |
| Smoke: cadeia do LLM | construção do `ClienteLLM` | Não passa por `app.py` |

O smoke test da página é o mais instrutivo dos erros. Ele foi escrito com a
intenção de responder "a aplicação está funcionando?", e na prática respondia "o
Streamlit está servindo?". São perguntas diferentes, e a diferença só aparece
exatamente no caso em que a resposta importa.

## O padrão por trás deste e dos outros incidentes da etapa

Este foi o sexto defeito da etapa, e todos têm a mesma forma: **uma suposição não
verificada sobre uma fronteira**.

| # | Incidente | Fronteira, e a suposição errada |
|---|---|---|
| 1 | Python 3.14 em produção, 3.13.2 local | Ambiente: "a mesma `requirements.txt` produz o mesmo ambiente" |
| 2 | `httpx` transitivo não fixado | Dependência: "fixar as diretas basta" |
| 3 | Variável salva no painel sem reinício | Processo: "salvar aplica" |
| 4 | `pytest` vs `python -m pytest` | Invocação: "rodar o teste é rodar o teste" |
| 5 | Resposta vazia da API do Render | Terceiro: "a API sempre responde do mesmo jeito" |
| 6 | Este | Verificação: "verde significa funcionando" |

Nenhum foi erro de lógica de negócio. Todos foram erros na costura entre partes,
onde ninguém tinha escrito o contrato.

## O que mudou

**Feito.** Um quarto smoke test que importa `app.py` e executa todo o código de
nível superior. Foi verificado nos dois sentidos: com o defeito reintroduzido,
ele falha com `KeyError` enquanto os três antigos passam; sem o defeito, os
quatro passam. Um teste que não sabe falhar não protege nada.

**A fazer, com prioridade.** Nenhum alerta existe. A indisponibilidade foi
descoberta por uma pessoa que por acaso abriu a página. Um sistema em produção
precisa avisar sozinho, e isso é trabalho da próxima etapa.

**A fazer.** Toda variável de ambiente que o código exigir precisa estar em
`.env.example` e ter valor padrão, ou falhar na inicialização com mensagem clara
em vez de traceback. A dívida original que a mudança tentava resolver segue
aberta: a coluna continua fixa em `"resposta"`. Ela volta quando houver padrão e
configuração nos dois ambientes, não antes.

## O que funcionou bem

Vale registrar, porque post-mortem que só lista falhas ensina menos do que
poderia.

**O rollback levou 26 segundos** e foi um redeploy de imagem já construída, sem
rebuild. A separação entre publicar e construir pagou dividendos exatamente
quando precisava.

**Havia uma versão anterior boa, etiquetada e identificável.** A tag `v1.0.0`
tornou óbvio para onde voltar. Sem ela, a decisão sob pressão seria escolher
entre commits parecidos.

**O deploy defeituoso não destruiu o anterior.** O Render mantém os deploys
anteriores desativados em vez de removê-los, o que transformou a recuperação em
uma escolha em vez de uma reconstrução.

**O `git revert` foi feito.** O rollback de plataforma não desfaz commit, e sem o
revert o código defeituoso voltaria ao ar no próximo deploy, provavelmente sem
ninguém entender por quê.
