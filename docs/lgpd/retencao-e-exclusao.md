# Política de retenção e exclusão

**Última revisão:** 16/10/2026
**Base:** LGPD, Art. 6º, III (necessidade), Art. 15 (término do tratamento) e
Art. 16 (eliminação), e Marco Civil da Internet, Art. 15

## Princípio

**O melhor dado para proteger é o que não foi guardado.** A decisão central desta
política não é por quanto tempo reter, é o que não reter. O sistema foi mantido
sem persistência de propósito: cada dia a mais em que uma resposta de pesquisa
existe em disco é um dia a mais em que ela pode vazar, e o sistema não precisa
dela depois que a análise termina.

Isso não é a mesma coisa que "não há o que fazer". Existem seis lugares onde
dado relacionado ao sistema existe por algum tempo, e dois deles estão sob
controle direto deste código. A tabela abaixo diz qual é qual.

## O que existe, onde e por quanto tempo

| # | Dado | Onde vive | Retenção | Mecanismo de exclusão | Quem controla |
|---|---|---|---|---|---|
| 1 | Respostas originais e resultado da análise | Memória do processo, durante a execução | **Até o fim da execução** | Descarte automático pelo runtime | Este código |
| 2 | Texto sanitizado das respostas | Logs de monitoramento de abuso do provedor de LLM | **Até 30 dias** | Expiração automática pelo provedor | Provedor, por contrato |
| 3 | Registro de acesso (IP, horário, navegador do analista) | Logs do Render | **7 dias** | Expiração automática pela plataforma | Plataforma |
| 4 | Logs de execução do pipeline | GitHub Actions | 90 dias | Expiração automática pelo GitHub | GitHub |
| 5 | Telemetria: prompt sanitizado, resposta do modelo, tokens, latência | Langfuse, União Europeia | **30 dias de acesso** | Fora do nosso controle no plano gratuito. Ver abaixo | Langfuse |
| 6 | Cache: hash da chave, tema, sentimento e texto do resumo. **Sem resposta, sem nome** | Arquivo SQLite no disco efêmero do serviço | **24 horas** | `DELETE` em SQL na abertura e a cada gravação, e esvaziamento a cada deploy | **Este código** |

### 1. Respostas e resultado: retenção zero, por construção

**Mecanismo:** o resultado de `analisar()` é atribuído a uma variável local de
`main()` em `app.py`. O Streamlit reexecuta o script do início a cada interação,
então a variável deixa de existir ao fim de cada execução. Ela não é colocada em
`st.session_state`, não é escrita em arquivo e não vai para banco.

Desde a introdução do cache, uma parte do resultado é guardada: tema e sentimento
de cada resposta, e o texto do resumo. **As respostas, originais ou sanitizadas,
continuam não sendo guardadas em lugar nenhum.** O item 6 descreve o cache.

**Evidência:** a busca por `session_state`, escrita em arquivo e `to_csv` em
`app.py` e `feedbackloop/` não encontra ocorrência. O único uso de `sqlite` é o
cache, em `feedbackloop/cache.py`, e o teste
`test_o_cache_nao_guarda_texto_nem_nome` confirma que o arquivo dele não contém
nenhum nome nem trecho de resposta.

**Reforço:** a cada deploy o processo é substituído por um novo. Como o pipeline
publica a cada push, mesmo um defeito futuro que fizesse algo persistir em memória
teria a vida útil limitada ao intervalo entre dois deploys.

**Limite honesto:** o conteúdo continua visível na aba do navegador do analista
até ele fechá-la. Isso está fora do alcance do servidor e é responsabilidade de
quem opera a estação de trabalho.

### 2. Logs do provedor: até 30 dias, fora do nosso controle

Segundo a política de dados da API da OpenAI consultada em 16/10/2026, o conteúdo
enviado fica em logs de monitoramento de abuso por até 30 dias e não é usado para
treinar modelos. A retenção zero existe, mas exige aprovação do provedor por
contrato comercial, e não está disponível para esta conta.

**Por que isso é aceitável aqui:** o que fica nesses logs é o texto já
sanitizado. O risco residual é o descrito no mapa de dados: nome que escapa da
regra e identificação indireta.

### 3. Registro de acesso: 7 dias, quando a lei exige 6 meses

**Este item não está conforme, e está registrado como pendência aberta.**

O Marco Civil (Art. 15) exige guardar registro de acesso por 6 meses. O Render
retém logs por 7 dias no plano Hobby, e 30 dias é o máximo em qualquer plano. A
plataforma apaga antes do prazo em que a lei exige que o dado exista.

Repare que aqui o problema é o oposto do habitual: não é reter demais, é reter de
menos. Retenção mínima obrigatória também é retenção, e a política precisa
cobrir os dois limites.

**Correção prevista:** configurar um *log stream* do Render para um serviço
externo com retenção de 6 meses, guardando apenas o registro de acesso e não o
conteúdo das requisições. Fica fora desta etapa porque exige um provedor a mais
para contratar e gerenciar.

### 4. Logs do pipeline

O GitHub Actions retém os logs de execução por 90 dias por padrão. Eles contêm
saída de testes e dos passos de deploy, e **não contêm dado pessoal**: os testes
offline usam respostas sintéticas, os smoke tests verificam apenas que a
aplicação responde, e os secrets aparecem mascarados como `***`.

### 5. Telemetria no Langfuse

No plano Hobby os traces ficam acessíveis por 30 dias. A configuração de
retenção, que permitiria definir quando o dado é apagado, só existe nos planos
pagos. Na prática, isso significa que o prazo de acesso é conhecido, mas o
momento da exclusão não é controlável por nós.

**Por que isso é aceitável aqui:** o que chega ao Langfuse passou por duas
camadas de mascaramento e não contém a resposta original. O mapa de dados
descreve as camadas. Se o sistema passar a operar com dado real, contratar o
plano com retenção configurável vira requisito.

### 6. Cache: 24 horas, com exclusão executada pelo próprio sistema

Este é o primeiro dado que o sistema realmente armazena, e é o item em que a
exclusão é um mecanismo deste código, e não uma promessa de terceiro.

**O que fica guardado:** o hash SHA-256 de cada chave, o tema e o sentimento de
cada classificação, o texto de cada resumo, e a hora da gravação. A chave é
calculada a partir do texto **já sanitizado** e não é reversível para ele. O texto
do resumo é gerado a partir de temas e contagens, nunca de uma resposta individual.

**Mecanismo de exclusão:**

```sql
DELETE FROM cache WHERE criado_em < :agora - 86400
```

Executado na abertura do cache e a cada gravação, em `Cache.expurgar()`. A leitura
filtra pelo mesmo prazo, então uma entrada vencida nunca é devolvida, mesmo que
ainda não tenha sido apagada.

**Reforço:** o disco do serviço é efêmero. Cada deploy começa com o cache vazio,
o que, com o pipeline publicando a cada mudança, encurta o prazo real na prática.

**Evidência:** o teste `test_expurgo_apaga_de_fato_o_que_venceu` grava uma entrada,
avança um relógio falso em mais de 24 horas e confere, consultando o próprio
banco, que a linha deixou de existir. O teste `test_gravar_tambem_dispara_o_expurgo`
confirma que a exclusão acontece sem depender de tarefa agendada.

## Pedido de eliminação

Pedido de eliminação feito por um titular (Art. 18, VI) vai para o controlador,
a empresa cliente, e não para a FeedbackLoop. Se chegar aqui, é encaminhado ao
controlador em até 2 dias úteis.

Do lado da FeedbackLoop, a eliminação é cumprida por construção no item 1, porque
não há nada guardado. Nos itens 2 e 3 ela é cumprida pela expiração automática,
em até 30 dias e em até 7 dias respectivamente.

## Quando esta política precisa mudar

Qualquer uma destas mudanças obriga a revisar esta política **antes** de entrar
em produção, e não depois:

- **Mudar o que o cache guarda.** Hoje ele não guarda resposta nem nome. Passar
  a guardar qualquer texto de resposta, mesmo sanitizado, muda a natureza do
  item 6
- Introduzir histórico de análises ou comparação entre pesquisas
- Passar a ler outra coluna do CSV além de `resposta`
- Mudar o provedor de LLM, ou o provedor mudar a sua política de retenção
