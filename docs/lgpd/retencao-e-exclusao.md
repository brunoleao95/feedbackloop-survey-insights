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

Isso não é a mesma coisa que "não há o que fazer". Existem quatro lugares onde
dado relacionado ao sistema existe por algum tempo, e só dois deles estão sob
controle direto deste código. A tabela abaixo diz qual é qual.

## O que existe, onde e por quanto tempo

| # | Dado | Onde vive | Retenção | Mecanismo de exclusão | Quem controla |
|---|---|---|---|---|---|
| 1 | Respostas originais e resultado da análise | Memória do processo, durante a execução | **Até o fim da execução** | Descarte automático pelo runtime | Este código |
| 2 | Texto sanitizado das respostas | Logs de monitoramento de abuso do provedor de LLM | **Até 30 dias** | Expiração automática pelo provedor | Provedor, por contrato |
| 3 | Registro de acesso (IP, horário, navegador do analista) | Logs do Render | **7 dias** | Expiração automática pela plataforma | Plataforma |
| 4 | Logs de execução do pipeline | GitHub Actions | 90 dias | Expiração automática pelo GitHub | GitHub |

### 1. Respostas e resultado: retenção zero, por construção

**Mecanismo:** o resultado de `analisar()` é atribuído a uma variável local de
`main()` em `app.py`. O Streamlit reexecuta o script do início a cada interação,
então a variável deixa de existir ao fim de cada execução. Ela não é colocada em
`st.session_state`, não passa por cache, não é escrita em arquivo e não vai para
banco.

**Evidência:** a busca por `session_state`, `st.cache`, escrita em arquivo,
`to_csv` e `sqlite` em `app.py` e `feedbackloop/` não encontra nenhuma ocorrência.
Os únicos `st.write` do arquivo exibem conteúdo na tela.

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

- **Introduzir cache.** Cache é dado armazenado. No momento em que existir, ele
  passa a ser a linha 5 desta tabela, com retenção definida e mecanismo de
  exclusão próprio
- Introduzir histórico de análises ou comparação entre pesquisas
- Passar a ler outra coluna do CSV além de `resposta`
- Mudar o provedor de LLM, ou o provedor mudar a sua política de retenção
