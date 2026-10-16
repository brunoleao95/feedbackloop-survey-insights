# Métricas e alertas

**Última revisão:** 16/10/2026

Este documento define o que é medido, a partir de que número algo vira problema,
e o que fazer quando vira. Os limites não foram escolhidos de cabeça: cada um
parte de uma **linha de base medida** e diz por que o limite está onde está.

## De onde vêm os números

| Fonte | O que mede | Por que ela |
|---|---|---|
| **Langfuse** | Cada chamada ao LLM: latência, tokens, custo, e as métricas de qualidade de cada análise | É a única fonte que sabe o que é uma chamada ao modelo. Ver [ADR-003](../adr/adr-003-observabilidade-com-langfuse.md) |
| **Render** | Memória e CPU do serviço | O Langfuse não vê a máquina |
| **GitHub Actions** | Se a aplicação publicada responde e funciona | É quem executa o alerta P1 |

## Linha de base

Medida em 16/10/2026 sobre **3 análises completas das 36 respostas de exemplo**,
somando **111 chamadas ao LLM**, duas em desenvolvimento e uma em produção, todas
com o mesmo código. Os números de LLM foram extraídos do Langfuse pelos tempos de
início e fim de cada observação, e não lidos de gráfico.

| Métrica | Valor medido |
|---|---|
| Latência por chamada, p50 | **1,05 s** |
| Latência por chamada, p95 | **2,06 s** |
| Latência por chamada, p99 | **3,38 s** |
| Latência por chamada, máxima | 4,39 s |
| Latência da análise completa | 34 s a 57 s |
| Custo por análise | **US$ 0,0088** (US$ 0,00024 por chamada) |
| Tokens por análise | ~7.270 |
| Taxa de formato válido | **1,00** (nenhuma falha em 111 chamadas) |
| Pulverização de temas | **0,639** (23 temas distintos em 36 respostas) |
| Memória do serviço em produção, pico | **~145 MB** de 512 MB |
| CPU do serviço em produção, pico | 0,02 de 0,5 |

**Duas correções em relação ao que estava escrito antes.** A auditoria do
protótipo estimava US$ 0,027 por análise, extrapolado de uma nota do antecessor.
O custo medido é **cerca de 3 vezes menor**. A mesma auditoria estimava a
pulverização "entre 16 e 23 temas"; o medido ficou no teto da faixa. A estimativa
foi útil como ordem de grandeza, e é exatamente por isso que esta etapa exige
número com evidência.

**Limite honesto da amostra:** três análises sobre o mesmo conjunto de dados são
suficientes para uma primeira linha de base, não para limites definitivos. Os
limites abaixo devem ser recalibrados depois de algumas semanas de uso real.

## As cinco métricas e seus limites

### 1. Latência por chamada ao LLM

| | Valor |
|---|---|
| Linha de base | p50 1,05 s, p95 2,06 s, p99 3,38 s |
| **Aviso (P3)** | **p95 acima de 4 s** |
| **Crítico (P2)** | **p95 acima de 8 s** |
| Onde ver | Langfuse, painel de latência, filtrado por `environment = prod` |

**Por que aí.** A análise faz as chamadas uma depois da outra, então o tempo total
é a soma delas: 37 chamadas a 1 s dão cerca de 40 s, e é isso que o usuário espera
olhando para o indicador de carregamento. Um p95 de 4 s, o dobro da linha de base,
leva a análise para perto de 2 minutos. Acima de 8 s, passa de 4 minutos, e o
usuário desiste antes do resultado.

O limite olha p95 e não média de propósito: a média esconde exatamente as chamadas
lentas que fazem a análise demorar.

**Causa mais provável, segundo a aula 9:** o provedor atualizou o modelo ou está
sob carga. Ação: comparar com o mesmo período da semana anterior e verificar a
página de status do provedor.

### 2. Custo por análise

| | Valor |
|---|---|
| Linha de base | US$ 0,0088 para 36 respostas |
| **Aviso (P2)** | **acima de US$ 0,02 por análise de 36 respostas** |
| **Orçamento (P2)** | **custo de LLM acima de US$ 3,70 por dia** |
| Onde ver | Langfuse, painel de custo |

**Por que aí.** US$ 0,02 é pouco mais que o dobro da linha de base. Como o volume
de entrada é fixo, o custo por análise só dobra se cada chamada passou a mandar
mais tokens, o antipadrão que a aula 9 chama de *token bloat*, ou se o modelo foi
trocado por um mais caro. Nenhuma das duas coisas deveria acontecer sem decisão.

O limite diário vem do briefing: US$ 120 por mês para infraestrutura e IA juntas.
Tirando os US$ 7 da hospedagem de produção, sobram cerca de US$ 113 para o LLM,
ou US$ 3,70 por dia. Passar disso em um dia é gastar o orçamento mais rápido do
que o mês.

### 3. Erro

| Sinal | Limite | Prioridade |
|---|---|---|
| **Aplicação indisponível ou quebrada** | qualquer smoke test falhando em produção | **P1, alerta automático** |
| Respostas fora do formato numa análise | acima de 5% das respostas | P2 |
| Chamadas ao LLM com erro | acima de 2% das chamadas | P2 |

**Linha de base:** zero falhas de formato e zero erros em 111 chamadas.

**Por que a falha de formato é métrica de erro.** É o erro silencioso que a
auditoria apontou: quando o modelo responde fora do formato, o parser cai em
"Não classificado" e "neutro" sem levantar exceção. Desde esta etapa, esse caso
marca o span como `WARNING` no Langfuse, e a contagem vai para a metadata de cada
análise como `falhas_formato`. Acima de 5%, a agregação já está distorcida o
suficiente para o resumo executivo deixar de ser confiável.

**Por que 2% de erro de chamada.** Na Etapa 1 o sistema bateu no limite de 500
requisições por minuto do provedor. Erro de chamada acima de 2% costuma ser isso,
e se repete enquanto o volume não cair.

### 4. Volume

| | Valor |
|---|---|
| Linha de base | 77 unidades do Langfuse por análise de 36 respostas |
| **Aviso (P3)** | **30 mil unidades no mês, 60% da cota gratuita** |
| Limite do provedor de LLM | 500 requisições por minuto |
| Onde ver | Langfuse, painel de uso |

**Por que aí.** A cota do plano gratuito do Langfuse é de 50 mil unidades por mês,
cerca de 650 análises de 36 respostas. Chegar a 60% no meio do mês dá tempo de
decidir entre reduzir a instrumentação e contratar o plano pago antes de perder
visibilidade.

O limite do provedor importa porque a análise de 36 respostas faz cerca de 55
chamadas por minuto. Umas 9 análises simultâneas já esbarram nas 500 por minuto,
e isso aparece como erro na métrica 3.

### 5. Qualidade

| Sinal | Linha de base | Limite | Prioridade |
|---|---|---|---|
| Taxa de formato válido | 1,00 | **abaixo de 0,95** | P2 |
| Pulverização de temas | 0,639 | **acima de 0,75** | P3 |

**O que é pulverização.** Temas distintos divididos pelo número de respostas. Uma
pulverização de 1,0 significa um tema diferente para cada resposta, o que torna a
agregação inútil, e a agregação é justamente o que o cliente compra.

**Limite honesto desta métrica:** o sistema não tem gabarito, então não sabe se um
tema está certo. Estas são medidas indiretas. Elas detectam degradação, não
acerto. E a linha de base já é ruim: 23 temas em 36 respostas é a pulverização que
a auditoria apontou, causada pela ausência de taxonomia fixa. O limite de 0,75
avisa se piorar; não diz que 0,639 está bom.

### Complementar: infraestrutura

| | Linha de base | Limite | Onde ver |
|---|---|---|---|
| Memória | ~145 MB de 512 MB (28%) | **acima de 80%, cerca de 410 MB** | Render, métricas do serviço |
| CPU | 0,02 de 0,5 | acima de 0,4 por mais de 5 minutos | Render, métricas do serviço |

O [ADR-002](../adr/adr-002-hospedagem-no-render.md) registrou a dúvida se 512 MB
caberiam. Com o volume de exemplo, sobra memória. O limite de 80% existe para o
caso que o ADR temia: uma planilha de milhares de linhas, carregada inteira em
memória pelo pandas.

## Alertas

### Prioridades

| Prioridade | Significado | Tempo de resposta esperado |
|---|---|---|
| **P1** | Usuário sem acesso ao sistema, ou sistema respondendo errado para todos | Imediato |
| **P2** | Sistema funcionando, mas com custo, erro ou qualidade fora do aceitável | No mesmo dia útil |
| **P3** | Tendência que precisa de decisão antes de virar problema | Na revisão semanal |

### Alerta P1: produção indisponível ou quebrada

| | |
|---|---|
| **Prioridade** | P1 |
| **Público** | Responsável técnico pelo serviço, dono do repositório |
| **Canal** | Issue no repositório com o rótulo `alerta-p1`, notificada por e-mail pelo GitHub |
| **Gatilho** | Qualquer um dos 4 smoke tests falhando contra produção |
| **Frequência** | A cada 30 minutos, em `.github/workflows/monitor.yml` |
| **Recuperação** | A primeira verificação que passa fecha a issue sozinha |

**Por que esse alerta, e não outro.** Ele fecha a pendência aberta no
[post-mortem de 29/08](../post-mortem-2026-08-29.md): a produção ficou quase 5
minutos inutilizável com o healthcheck respondendo "ok", e a queda foi descoberta
porque havia alguém olhando a tela. O quarto smoke test, que importa o módulo da
interface, foi escrito por causa daquele incidente e teria disparado este alerta.

**Uma issue por incidente.** Se a falha persiste, cada nova verificação comenta na
issue já aberta, em vez de abrir outra. Isso evita que um incidente de uma hora
gere duas issues e duas notificações por hora.

**Testado em 16/10/2026.** O monitor foi executado manualmente contra
`https://example.com`, que não é a aplicação: falhou e abriu a issue #1 com o alvo
e os testes que falharam. Na execução seguinte, contra produção, passou e fechou a
issue com o comentário de recuperação. As duas execuções estão no histórico do
GitHub Actions.

### Procedimento de resposta ao P1

1. **Abrir a issue** e ler quais testes falharam. O nome do teste já diz em que
   camada está o problema: o healthcheck é o processo, a página é a plataforma, a
   cadeia do LLM é dependência, a importação é código de nível de módulo
2. **Olhar o último deploy** no painel do Render. Se a falha começou logo depois
   de um deploy, o caminho mais rápido é o **rollback pela plataforma**, que no
   incidente de 29/08 levou 26 segundos
3. **Depois do rollback, `git revert`** do commit que causou o problema.
   Rollback de plataforma não desfaz commit, e sem o revert o defeito volta no
   próximo deploy
4. **Se não houve deploy**, olhar os logs do serviço no Render e a página de
   status do provedor de LLM
5. **Registrar** a causa na issue antes de ela se fechar sozinha

### Sinais P2 e P3: sem alerta automático, por enquanto

**Os limites das métricas 1 a 5 não disparam alerta automático hoje.** Eles são
verificados nos painéis do Langfuse e do Render. Digo isso explicitamente porque a
diferença entre "tem limite definido" e "tem alerta" é exatamente a que a dica 3
do enunciado aponta: alerta sem ação é ruído, e limite sem alerta é uma decisão
que alguém precisa lembrar de olhar.

O Langfuse oferece alertas nativos, dois no plano gratuito, mas só os entrega por
Slack, webhook ou GitHub Actions, e qualquer um deles exige uma credencial a mais
para criar e gerenciar. A evolução natural é ligar os alertas de custo e de
latência ao mesmo canal de issues do P1, pela integração com GitHub Actions.

## Painéis

| Painel | Endereço | O que mostra |
|---|---|---|
| Latência | Langfuse, *Langfuse Latency Dashboard* | Latência por chamada e por análise, por percentil |
| Custo | Langfuse, *Langfuse Cost Dashboard* | Custo por modelo, por dia e total |
| Uso | Langfuse, *Langfuse Usage Management* | Unidades consumidas da cota |
| Infraestrutura | Render, serviço `feedbackloop-prod`, aba Metrics | Memória, CPU e requisições HTTP |
| Disponibilidade | GitHub, aba Actions, workflow *Monitor de producao* | Histórico de verificações do P1 |

Os painéis do Langfuse e do Render exigem acesso às respectivas contas. Para quem
não tem, há duas evidências públicas, que dispensam login.

**Um trace real de produção, aberto para leitura:**
[análise completa das 36 respostas, em produção, 16/10/2026](https://cloud.langfuse.com/project/cmvazqcvr01hfad0kifd23oag/traces/16aadd310862ab953ccc90815bbdbaf7).
Mostra a árvore inteira, com a sanitização acontecendo antes da primeira chamada
ao provedor, a latência e o custo de cada uma das 37 chamadas, e o `[PESSOA]` no
lugar dos nomes nos prompts guardados. É o trace de onde saíram os números da
linha de base de produção: 37,5 s e US$ 0,0089.

Só este trace foi tornado público. Os demais seguem restritos à conta: conferido
em 16/10 que este abre sem login e que outro trace do mesmo projeto, consultado
da mesma forma, é recusado com "this trace is not public".

**O histórico do alerta P1**, na aba Actions do repositório, workflow *Monitor de
producao*, e a issue #1, aberta e fechada no teste de disparo.
