# ADR-002: Hospedagem no Render, com produção em plano pago e desenvolvimento no tier gratuito

## Status

Aceito em 2026-08-29.

## Contexto

O [ADR-001](adr-001-adocao-da-stack-b.md) fixou a stack B, mantendo o protótipo
em Python com interface Streamlit. Falta decidir onde ele vai rodar.

O briefing autoriza quatro plataformas: Streamlit Cloud, Hugging Face Spaces,
Render e Vercel, com orçamento total de US$ 120 por mês para infraestrutura e
IA somadas.

Três requisitos operacionais desta fase restringem a escolha. A URL precisa ser
pública e estável, sem depender da minha máquina. O deploy precisa ser disparado
pelo pipeline de CI/CD a cada push na branch principal, com o pipeline inteiro
abaixo de 5 minutos. E os ambientes de desenvolvimento e produção precisam ser
realmente separados, com secrets distintos em cada um.

A avaliação das quatro opções está em
[`docs/matriz-decisao-stack.md`](../matriz-decisao-stack.md), usando os mesmos
seis critérios e pesos do ADR-001.

## Decisão

Hospedar no **Render**, com dois serviços web separados:

| Ambiente | Branch | Plano | Custo |
|---|---|---|---|
| Produção | `main` | `0.5c-512mb`, 512 MB RAM | US$ 7/mês |
| Desenvolvimento | `dev` | Free, 512 MB RAM | US$ 0 |

O workspace fica no plano Hobby, que custa US$ 0 e cobra apenas o compute. Cada
serviço recebe seu próprio conjunto de variáveis de ambiente, e o deploy de cada
um é disparado pelo GitHub Actions, não pela integração nativa da plataforma
com o Git.

Na matriz, o Render somou 470 de 500, contra 440 do Hugging Face Spaces, 395 do
Vercel e 330 do Streamlit Cloud.

Dados de preço e de política de hibernação consultados em `render.com` em
29/08/2026.

## Consequências

**Positivas.** A produção não hiberna, então a URL responde imediatamente para
quem abrir, e os smoke tests do pipeline não pagam tempo de acordar o serviço.
Isso protege dois requisitos ao mesmo tempo: a estabilidade da URL e o teto de 5
minutos do pipeline. Dois serviços independentes dão isolamento real, com
secrets configurados por serviço, e não apenas branches diferentes apontando
para o mesmo lugar. Como o Render executa qualquer serviço web definido por um
start command ou container, a substituição da interface Streamlit prevista para
a fase final acontece sem trocar de plataforma: muda o processo, não a
hospedagem. O custo de US$ 7 representa 5,8% do orçamento mensal, deixando o
restante para o consumo de LLM, que a auditoria mostrou ser o gasto dominante
deste sistema.

**Negativas, e são cinco.**

Primeira: o ambiente de desenvolvimento hiberna após 15 minutos sem tráfego e
leva cerca de um minuto para responder de novo. Aceito isso conscientemente,
porque em dev ninguém está sendo avaliado. Mas significa que qualquer verificação
automatizada apontada para o dev precisa tolerar esse primeiro acesso lento, com
timeout generoso ou uma tentativa de aquecimento antes da asserção.

Segunda: o tier gratuito concede 750 horas de instância por mês **por
workspace**, e ao estourar essa cota o Render suspende todos os serviços
gratuitos até o mês seguinte. Isso inviabiliza a solução preguiçosa para o
problema anterior: manter o dev acordado com um ping periódico consumiria cerca
de 730 horas sozinho e me deixaria sem ambiente de desenvolvimento na virada do
mês. O cold start em dev é para ser tolerado, não contornado.

Terceira: passa a existir um custo recorrente onde antes havia zero. É pequeno,
mas é uma assinatura que continua cobrando se o projeto for esquecido.

Quarta: 512 MB de RAM no plano de produção. O protótipo carrega o CSV inteiro em
memória com pandas antes de processar, e isso funciona com as 36 respostas do
exemplo. Não tenho medição para uma planilha de milhares de linhas, que é
exatamente o volume que o briefing menciona. Preciso medir o consumo real antes
de prometer esse cenário, e é possível que este plano precise subir.

Quinta: preço e política de hibernação foram consultados numa data específica e
mudam sem aviso. Este ADR registra a data justamente para que a decisão possa
ser reavaliada contra as condições vigentes.

## Alternativas consideradas

**Streamlit Cloud.** Descartada apesar de ser a opção de menor atrito para um
app Streamlit já pronto. Ela recebeu nota 2 no critério de maior peso porque
publica através da própria integração com o Git, e não através do pipeline. Eu
até poderia manter um GitHub Actions rodando os testes, mas o deploy não seria
disparado por ele. Isso é integração contínua com publicação automática da
plataforma, e não o CI/CD que esta fase exige. A distinção é sutil e é
justamente onde a escolha cômoda custaria caro.

**Hugging Face Spaces.** Foi a alternativa mais próxima e merece registro
honesto: antes de eu pontuar o critério de domínio próprio, ela estava empatada
com o Render em 450 pontos. Perdeu por dois motivos. É a plataforma que eu menos
conheço entre as quatro, e é mais orientada a demonstração de modelos do que a
aplicação web, o que tornaria a migração de interface da fase final mais
custosa. Verifiquei que a decisão não depende dessa nota subjetiva: mesmo
elevando o domínio do HF Spaces de 2 para 4, ele chegaria a 460 e ainda perderia.

**Vercel.** Descartada nesta fase com nota 1 em esforço de migração, porque
Streamlit não roda bem em ambiente serverless e adotá-la agora exigiria
reescrever a interface antes de publicar a primeira URL. Ela volta a ser
candidata natural na fase final, quando a interface for reconstruída como
aplicação web de verdade. Se isso acontecer, será registrado em um novo ADR que
substitui este.
