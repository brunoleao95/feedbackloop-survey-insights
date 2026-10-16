# Mapa de dados pessoais

**Última revisão:** 16/10/2026
**Sistema:** FeedbackLoop Survey Insights, versão em produção em `https://feedbackloop-prod.onrender.com`

Este documento descreve cada ponto em que o sistema toca dado pessoal, a base
legal de cada um e o risco que sobra depois do tratamento. Ele descreve o
sistema como está no ar, inclusive onde ele ainda falha.

## Papéis

Antes das bases legais, uma definição que muda tudo o que vem depois.

**A FeedbackLoop é operadora, não controladora.** As respostas de pesquisa de
clima pertencem aos funcionários das empresas clientes, e quem decide coletá-las,
para quê e por quanto tempo é o RH do cliente. A FeedbackLoop processa esses
dados em nome dele (LGPD, Art. 5º, VII) e segue as instruções do controlador
(Art. 39).

Consequência prática: a base legal da coleta é do cliente, não nossa. O que nos
cabe é não tratar além do que foi instruído, garantir segurança, minimizar o que
sai do processo e registrar o que fazemos. Este documento cobre a nossa parte e
indica onde a parte do cliente é pré-requisito.

## Titulares

O sistema afeta dois grupos de pessoas, e só um deles respondeu à pesquisa.

| Titular | Como aparece | Sabe que está no sistema? |
|---|---|---|
| **Respondente** | Autor da resposta aberta. Funcionário da empresa cliente | Sim: escolheu responder a pesquisa |
| **Terceiro citado** | Gestor, colega ou ex-colega mencionado pelo nome dentro da resposta | **Não.** Não respondeu nada e não foi consultado |

O segundo grupo é o que exige mais cuidado. É a pessoa que aparece em "o gerente
Marcos muda as prioridades toda semana" sem ter participado de nada.

## Pontos de tratamento

| # | Ponto | Dado | Base legal | Justificativa |
|---|---|---|---|---|
| 1 | **Entrada das respostas** (upload de CSV ou texto colado) | Texto livre das respostas abertas. Pode conter nome de terceiros e relatos identificáveis | Legítimo interesse do controlador, Art. 7º, IX | Pesquisa de clima é ferramenta usual de gestão de pessoas, e o respondente participou sabendo da finalidade. Exige teste de balanceamento a cargo do cliente |
| 2 | **Processamento em memória** | O mesmo texto, durante a execução da análise | Mesma base do ponto 1 | Necessário para executar a finalidade. Não há gravação em disco nem em banco |
| 3 | **Envio ao provedor de LLM** | Texto **já sanitizado**: nomes, e-mail, CPF e telefone substituídos por marcadores | Mesma base do ponto 1, mais Art. 33 para a transferência | Ver a seção de transferência internacional abaixo |
| 4 | **Exibição do resultado** | Respostas originais, tema, sentimento e resumo, na tela do analista | Mesma base do ponto 1 | O analista é quem enviou a planilha. Não há compartilhamento com terceiros |
| 5 | **Logs de acesso da plataforma** | IP, agente do navegador e horário de quem acessa o app (o analista de RH, não o respondente) | Cumprimento de obrigação legal, Art. 7º, II, combinado com o Marco Civil da Internet, Art. 15 | Provedor de aplicação com fins econômicos é obrigado a guardar registro de acesso |
| 6 | **Telemetria de observabilidade** (Langfuse) | Prompt sanitizado de cada chamada, resposta do modelo, tokens, latência e contagens agregadas. **Nunca** a resposta original | Legítimo interesse do operador, Art. 7º, IX, mais Art. 33 para a transferência | Sem telemetria não há como detectar falha silenciosa, custo fora do padrão ou queda de qualidade. Ver a seção de observabilidade abaixo |
| 7 | **Cache de resultados** (SQLite no disco efêmero do serviço) | Hash SHA-256 da chave, tema, sentimento e texto do resumo, gerado de agregados. **Sem resposta, nem sanitizada, e sem nome** | Legítimo interesse do operador, Art. 7º, IX | Evita pagar e esperar de novo pela mesma análise. Expira em 24 horas com exclusão em SQL. Ver [docs/otimizacao/cache.md](../otimizacao/cache.md) |

### Minimização, que vem antes da base legal

A base legal autoriza o tratamento, mas o Art. 6º, III, exige que ele se limite
ao mínimo necessário. Três decisões do sistema existem por causa disso:

**A coluna `setor` não é lida.** Ela existe no CSV de exemplo e provavelmente
existiria numa planilha real. O código lê apenas a coluna `resposta`. Setor,
combinado com uma queixa específica, é um dos caminhos mais curtos para
reidentificar alguém num time pequeno.

**Nenhuma resposta é persistida.** O sistema não grava resposta nem histórico. O
texto existe enquanto a análise roda e enquanto a página está aberta. O único
dado armazenado é o cache, que guarda só tema, sentimento e o texto do resumo,
sob uma chave em hash, por até 24 horas. Ver
[a política de retenção](retencao-e-exclusao.md) e
[a otimização com cache](../otimizacao/cache.md).

**Só o texto sanitizado sai do processo.** A sanitização acontece em
`feedbackloop/pipeline.py`, dentro de `analisar()`, que é o único caminho até o
provedor. O original nunca é enviado. Um teste
(`tests/test_pii.py::test_nenhum_nome_de_exemplo_chega_ao_provedor`) roda o
pipeline completo com um cliente espião e falha se qualquer um dos nomes das
respostas de exemplo aparecer em qualquer mensagem enviada.

## Transferência internacional

**Toda análise é uma transferência internacional de dados pessoais.** O provedor
processa fora do Brasil, e isso não é contornável por configuração: entre as
regiões de residência de dados que a OpenAI oferece para a API (Estados Unidos,
Europa, Reino Unido, Canadá, Japão, Índia, Singapura, Coreia do Sul, Austrália e
Emirados Árabes), **o Brasil não está**. Usar o provedor é transferir.

**Base:** Art. 33, II, alínea "b", da LGPD, por meio de cláusulas-padrão
contratuais, regulamentadas pela Resolução CD/ANPD nº 19/2024. A adoção dessas
cláusulas no contrato com o provedor é um pré-requisito jurídico que precisa ser
confirmado com o jurídico antes de operar com dado real. Este documento registra
a necessidade; ele não substitui o contrato.

**O que o provedor faz com o que recebe**, segundo a política de dados da API
consultada em 16/10/2026:

- Os dados enviados à API **não são usados para treinar modelos** por padrão
- Ficam retidos **por até 30 dias** em logs de monitoramento de abuso
- Retenção zero existe, mas exige aprovação prévia do provedor via contrato
  comercial, e não está disponível para esta conta

**Mitigação que já está em produção:** só texto sanitizado cruza a fronteira. O
que a transferência leva é "o gerente [PESSOA] muda as prioridades toda semana",
e não o nome de quem foi citado.

## Observabilidade: um segundo destino internacional

Instrumentar o sistema criou um segundo lugar para onde dado sai do processo: o
Langfuse, hospedado na **União Europeia** (`cloud.langfuse.com`, sobre AWS). É uma
segunda transferência internacional, com a mesma base do Art. 33, II, "b", e com
o mesmo pré-requisito de cláusulas-padrão contratuais.

O que vale para o provedor de LLM vale para ele: **nada identificável sai**. Três
camadas, em `feedbackloop/observabilidade.py`:

**1. Captura desligada onde há texto cru.** A função `analisar`, único ponto que
recebe as respostas originais, e a etapa de sanitização não registram entrada nem
saída. Elas exportam só contagens: quantas respostas, quantas alteradas, quantos
dados mascarados por tipo. O único componente que registra o prompt é o adaptador
do LLM, e ele já recebe o texto sanitizado.

**2. Máscara no próprio cliente do Langfuse.** Tudo o que é exportado passa pela
mesma sanitização de PII antes de sair. Se alguém um dia instrumentar a função
errada, o nome ainda é mascarado no caminho.

**3. Máscara de credenciais.** Funções que recebem o objeto `cliente` carregam,
dentro dele, a chave da OpenAI. A captura de entrada está desligada nelas, e a
máscara também substitui qualquer padrão de chave de API por `[SEGREDO]`. A
sanitização de PII sozinha não pegaria isso: ela procura nomes, não credenciais.

As três camadas têm testes em `tests/test_observabilidade.py`, inclusive um que
simula um objeto cliente serializado por engano e confirma que a chave não sai.

**Um defeito encontrado e corrigido no mesmo dia, 16/10.** Na primeira versão
desta instrumentação, as camadas 2 e 3 estavam desligadas sem que nada indicasse
isso. O cliente com a máscara só era criado na primeira chamada ao LLM, mas o
`@observe` de `analisar` roda antes, e o SDK atendia essa primeira observação com
um cliente padrão, sem máscara.

Foi encontrado com um servidor local que imita o Langfuse e decodifica o que o SDK
exporta: uma função observada, com captura ligada e texto cru, exportou o nome e
a chave em claro. **Nenhum dado pessoal vazou em produção**, porque a camada 1
segurou sozinha: todo texto que chegava a uma função com captura ligada já estava
sanitizado. A correção cria o cliente com máscara na importação do módulo, e um
teste de regressão, executado num interpretador separado e com chaves falsas,
falha se a máscara não estiver ativa.

Registro isto porque este documento afirmava três camadas enquanto só uma
funcionava. A lição é a mesma do post-mortem de 29/08: proteção que não é testada
contra o caso real é uma afirmação, não uma garantia.

## Riscos que sobram

Esta é a parte mais importante do documento. O tratamento acima reduz o risco,
não o elimina, e cada item abaixo é específico deste sistema.

### 1. Dado sensível escrito pelo próprio respondente

**Este é o maior risco jurídico do sistema, e ele não está resolvido.**

O Art. 11 da LGPD trata dado de saúde, opinião política, filiação sindical e
religião como dado sensível, e **não admite legítimo interesse como base** para
ele. Ou seja: a base do ponto 1 não cobre uma resposta como "estou em burnout e
tomando remédio para ansiedade". Esse é dado de saúde do respondente, escrito por
ele, e numa pesquisa de clima real ele vai aparecer.

O sanitizador não detecta isso. E a detecção por palavra-chave não é trivial: ao
testar uma lista de termos nas 36 respostas de exemplo, três casaram, e as três
eram falso alarme. A resposta 14 fala de *plano* de saúde, a 25 da *política* de
saúde mental da empresa, e a 29 da *política* de promoção. Nenhuma revela dado
sensível de uma pessoa. Um bloqueio por palavra-chave teria barrado as três e
deixado passar quem escrevesse "tô no meu limite, comecei terapia".

**Controles necessários antes de dado real**, nenhum deles automatizável por
este sistema hoje:

- O questionário do cliente deve orientar o respondente a não incluir informação
  de saúde própria ou de terceiros
- O cliente precisa de base do Art. 11 para o caso de esse dado aparecer mesmo
  assim
- Revisão humana de uma amostra antes do primeiro uso real

### 2. Nome que escapa da sanitização

A sanitização reconhece nome e sobrenome em sequência e nome logo depois de um
cargo. Ela falha em nome isolado fora desse contexto ("falei com a Fernanda
ontem") e em apelido ("o juninho do financeiro"). Esses casos vão para o
provedor com o nome.

A escolha consciente aqui foi não usar um modelo de reconhecimento de entidades
nesta versão: ele pegaria mais casos, mas pesa na memória de um serviço que roda
com 512 MB. As limitações estão listadas em `feedbackloop/pii.py`.

### 3. Identificação indireta

Nenhuma regra de texto resolve isto: "a única mulher do time de dados" ou "quem
voltou de licença em março" identificam uma pessoa sem nome nenhum. Num time
pequeno, o próprio teor da queixa identifica.

Esse risco é o motivo de a política exigir revisão antes de dado real, e de o
sistema não persistir nada: o dano de uma reidentificação é limitado por quanto
tempo o dado existe.

### 4. Registro de acesso guardado por menos tempo que a lei exige

**Esta obrigação não está sendo cumprida hoje.**

O Marco Civil da Internet (Art. 15) obriga o provedor de aplicação a guardar o
registro de acesso, data, hora e IP, por **6 meses**. Esses registros hoje são os
logs do Render, e o Render retém logs por **7 dias** no plano Hobby, que é o deste
workspace. Consultado na documentação da plataforma em 16/10/2026.

Trocar de plano não resolve: o maior período oferecido, nos planos Scale e
Enterprise, é de 30 dias. A correção exige enviar os logs para um serviço externo
com retenção configurável, o que o Render suporta como *log stream*. Está
registrado como pendência em [`retencao-e-exclusao.md`](retencao-e-exclusao.md).

Registro aqui o achado em vez de omiti-lo porque ele é o tipo de coisa que só
aparece quando se confere: a plataforma guarda logs, então parece resolvido, e o
prazo legal é mais de 25 vezes maior que o real.

## Direitos do titular

Pedidos de acesso, correção ou eliminação (Art. 18) **devem ser dirigidos ao
controlador**, a empresa cliente. Se chegarem à FeedbackLoop, são encaminhados ao
controlador em até 2 dias úteis, para que ele cumpra o prazo de 15 dias do
Art. 19, II.

Na prática, a FeedbackLoop tem pouco a eliminar: o sistema não persiste
resposta. O que pode existir é o texto sanitizado nos logs do provedor, por até
30 dias, os traces mascarados no Langfuse, por até 30 dias, o cache de
resultados, que expira sozinho em 24 horas, e o registro de acesso na
plataforma.

## Quando revisar este documento

Revisar sempre que uma destas coisas mudar:

- O sistema passar a persistir qualquer dado além do cache, ou o cache passar a
  guardar texto de resposta
- Trocar o provedor de LLM ou a forma de chamá-lo
- O CSV aceito passar a ler outra coluna além de `resposta`
- A política de dados do provedor mudar
