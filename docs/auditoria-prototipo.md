# Auditoria do protótipo herdado

**Data:** 29/08/2026
**Objeto:** FeedbackLoop Survey Insights, versão v0.2, recebida de Rafael Crispim
**Autor:** Bruno Leão

## Método

Auditei o protótipo antes de alterar qualquer linha. O commit `9671d2b` deste
repositório é o estado exato do que recebi, para que todo diff a partir daqui
separe o que era herança do que é trabalho meu.

O que fiz: li os 15 arquivos versionados, criei o ambiente virtual, instalei as
dependências fixadas em `requirements.txt`, rodei a suíte de testes e subi a
aplicação localmente com o conjunto de dados de exemplo.

## Estado verificado

O protótipo **funciona**. Isto não é um projeto quebrado, é um projeto
inacabado, e a distinção importa para o plano de evolução.

- A aplicação sobe com `streamlit run app.py` e carrega as 36 respostas
  sintéticas de `data/respostas-pesquisa-exemplo.csv`
- Os 7 testes em `tests/test_pipeline.py` passam em 0,03s
- Os testes rodam **offline**, com um dublê de LLM, porque o Rafael isolou a
  chamada ao provedor atrás de um único método (`ClienteLLM.completar`)

Essa separação entre lógica pura e chamada ao provedor é a melhor decisão da
herança e é o que torna a evolução viável sem reescrita. Registro isso porque
uma auditoria que só lista defeitos não ajuda a decidir o que preservar.

## Lacunas

### 1. Dados pessoais vão crus para o provedor de IA

**Evidência:** `feedbackloop/pipeline.py:162` monta o prompt interpolando o texto
da resposta sem nenhum tratamento. O único controle existente é um aviso visual
em `app.py:40`, que informa o usuário e não impede nada.

**O que acontece na prática:** respostas de pesquisa de clima contêm nome de
gestor, nome de colega e queixas identificáveis. Todo esse conteúdo sai da
aplicação em texto claro. Como os provedores autorizados processam fora do
Brasil, cada análise é também uma transferência internacional de dados de
funcionários de empresas clientes, feita hoje sem finalidade declarada, sem base
legal registrada e sem prazo de retenção.

**Impacto:** é a lacuna mais grave da herança, e a única que impede o sistema de
receber dado real. As demais degradam qualidade ou custo; esta cria exposição
jurídica. Bloqueia o piloto com cliente.

### 2. Nenhum resultado é persistido

**Evidência:** `app.py:101`. A análise existe apenas no estado da sessão do
Streamlit. Fechou a aba, perdeu.

**O que acontece na prática:** não há como comparar a pesquisa deste trimestre
com a do anterior, que é justamente a promessa de um produto de people
analytics. Também não há histórico para auditar o que foi enviado ao provedor,
o que agrava o item 1: hoje é impossível responder o que foi processado, quando
e a pedido de quem.

**Impacto:** limita o valor de produto e remove a trilha de auditoria.

### 3. Nenhum cache, e o custo cresce linearmente com o uso

**Evidência:** `feedbackloop/pipeline.py:206` itera resposta a resposta, uma
chamada por item, mais uma do resumo. `app.py:89` confirma que cada clique em
"Analisar" refaz tudo. Reanalisar a mesma planilha paga duas vezes.

**Baseline de custo.** A única medição existente é a nota do Rafael: 36
respostas, 15 execuções, US$ 0,40 no total. Extrapolando:

| Cenário | Chamadas | Custo por execução | Execuções possíveis em US$ 120/mês |
|---|---|---|---|
| 36 respostas (exemplo) | 37 | US$ 0,03 | 4.494 |
| 500 respostas | 501 | US$ 0,36 | 332 |
| 2.000 respostas | 2.001 | US$ 1,44 | 83 |

**Impacto:** o briefing cita pesquisas de "centenas a milhares" de respostas. No
cenário de 2.000, o orçamento inteiro do mês comporta 83 execuções. Como não há
cache, cada reprocessamento da mesma planilha consome uma dessas 83. O teto real
é bem menor do que parece, e o gargalo de custo do projeto é este, não a
hospedagem.

Ressalva: a medição do Rafael é uma estimativa dele, sem instrumentação, e
depende do modelo em uso. O número precisa ser refeito com medição própria assim
que houver observabilidade. Uso-o aqui como ordem de grandeza, não como fato.

### 4. Sem deploy e sem automação

**Evidência:** verificado por inspeção da raiz do repositório. Não existe
`.github/`, não existe `Dockerfile`, não existe `Procfile`. Não há pipeline
declarado em lugar nenhum.

**O que acontece na prática:** o sistema só existe enquanto alguém roda um
comando na própria máquina. Foi assim que ele morreu quando o Rafael saiu, e é
literalmente a situação que a Bia pediu para resolver.

**Impacto:** é a lacuna que define o objetivo desta fase.

### 5. Nenhum log, nenhuma métrica, nenhum rastro

**Evidência:** busca por `logging`, `logger` e `logging.` em todo o código
Python retorna **zero ocorrências**.

**O que acontece na prática:** não existe registro de quanto custou uma análise,
quanto tempo levou, quantas chamadas falharam ou o que foi enviado ao provedor.
E o problema é pior do que ausência de log, porque o código **mascara falha
ativamente**: `feedbackloop/pipeline.py:78` captura a exceção de parsing e segue
com `pass`, e `parse_sentimento` devolve `"neutro"` em três caminhos distintos
(linhas 51, 59 e 60), incluindo o caso em que não reconheceu nada. Quando o
modelo devolve algo inesperado, o resultado é indistinguível de uma resposta
genuinamente neutra.

**Impacto:** não há como saber se o sistema está saudável. Um provedor
degradado produziria uma análise inteira de temas "Não classificado" e
sentimento "neutro", e ninguém perceberia. Isto também invalida qualquer métrica
de qualidade construída sobre a saída atual.

### 6. Qualidade não é medida, e a agregação se pulveriza

**Evidência:** `feedbackloop/pipeline.py:24` pede ao modelo que identifique o
tema em aberto, oferecendo exemplos mas nenhuma lista fechada. Os 7 testes
existentes cobrem parsing, contagem e montagem do resumo, e nenhum avalia
conteúdo gerado.

**O que acontece na prática:** sem taxonomia fixa, o modelo cria um rótulo novo
a cada resposta. O Rafael relata 30 respostas gerando 25 temas. Como a
funcionalidade que o cliente compra é justamente a agregação, uma contagem
pulverizada destrói o valor da entrega, mesmo com cada classificação individual
parecendo razoável.

**Impacto:** compromete o produto no seu ponto central. E, sem conjunto de
validação, não há como provar melhora depois de corrigir.

## Leitura geral

As seis lacunas não são independentes. Três delas (2, 5 e 6) se reforçam: sem
persistência não há histórico, sem log não há rastro, e sem nenhum dos dois não
existe base para medir qualidade. Atacar a 6 antes da 5 seria construir uma
métrica sobre um sistema que engole os próprios erros.

Por isso a ordem de ataque que proponho não segue a numeração:

| Ordem | Lacuna | Razão |
|---|---|---|
| 1º | 4, deploy e automação | É o objetivo desta fase e desbloqueia todo o resto |
| 2º | 1, dados pessoais | Bloqueia o piloto com dado real, e o risco é jurídico |
| 3º | 5, observabilidade | Pré-requisito para medir qualquer coisa, inclusive custo |
| 4º | 3, cache e custo | Só faz sentido otimizar depois de medir |
| 5º | 6, taxonomia e qualidade | Depende de 5 para provar que melhorou |
| 6º | 2, persistência | O de maior valor de produto e o menos urgente para operar |

Uma observação sobre a lacuna 1: ela é a mais grave, mas fica em segundo lugar
porque o sistema opera hoje com dados sintéticos. A ordem inverte no instante em
que a primeira planilha real for carregada, e isso precisa estar acordado com a
Bia antes de qualquer piloto.
