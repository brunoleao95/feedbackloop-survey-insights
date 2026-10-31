# Qualidade: taxonomia fixa de temas

**Data da medição:** 31/10/2026, em desenvolvimento, com o modelo real
**Código:** `TEMAS` e `normalizar_tema()` em `feedbackloop/pipeline.py`

## O problema

O briefing pediu, para a semana 3, a definição de uma taxonomia de temas, porque
"hoje o modelo inventa tema a cada resposta". A auditoria registrou o efeito como
lacuna 6, e a linha de base de métricas o mediu: **36 respostas viravam 23 temas
distintos**, uma pulverização de 0,639.

Isso esvazia a funcionalidade central. A agregação é o que o cliente compra: um
painel que diz "Liderança: 4, Gestão: 2, Chefia: 1" está dizendo "Liderança: 7"
de um jeito que ninguém consegue ler.

## A mudança

O prompt passou a listar **11 temas e "Outros"**, cada um com uma linha do que
cobre. A lista saiu das 36 respostas de exemplo e dos exemplos de tema do
briefing.

O código não confia só no prompt. `normalizar_tema()` compara sem caixa e sem
acento, e **qualquer tema fora da lista vira "Outros"**. Assim, mesmo um modelo
que desobedeça não abre categoria nova. Falha de formato continua distinta: uma
resposta sem JSON segue como "Não classificado" e marcada como `WARNING` no
trace.

Trocar o prompt mudou a chave do cache, que se invalidou sozinho, como o
desenho do cache prevê.

## Antes e depois

As mesmas 36 respostas de exemplo, o mesmo modelo, temperatura zero.

| | Antes: tema em aberto | **Depois: taxonomia fixa** |
|---|---|---|
| Temas distintos | 23 | **11** |
| Pulverização (temas ÷ respostas) | 0,639 | **0,306** |
| Respostas cobertas pelos 8 temas exibidos | 23 de 36 | **31 de 36** |
| Respostas em "Outros" | não existia | 0 |
| Sentimento negativo | 23 | 23 |
| Latência da análise | 34 s a 57 s | 47,6 s |
| Chamadas ao provedor | 37 | 37 |
| Tokens de entrada por análise | 6.364 | **13.030** |
| Custo por análise | US$ 0,0089 | **US$ 0,0138** |

Os temas do "antes" são da linha de base de 16/10, em
[métricas e alertas](../operacao/metricas-e-alertas.md). Tokens e custo do "antes"
são de uma análise em desenvolvimento em 31/10, às 17:42, com o prompt antigo, e
o "depois" é a análise seguinte, às 17:47, já com a taxonomia. Os dois traces
estão no Langfuse, ambiente `dev`: `6a7d2d64` e `8fe87bc7`.

## O que os números não dizem

**Menos temas não é o mesmo que temas certos.** O sistema ainda não tem gabarito.
A pulverização mede se a agregação ficou legível, não se cada resposta caiu no
tema que um analista de RH escolheria. O briefing pede um conjunto de validação
para isso, e ele continua em aberto.

**Uma medição só.** A análise repetida vem do cache, então refazer a mesma
planilha não gera uma segunda amostra independente. Com temperatura zero, a
variação esperada é pequena, mas não foi medida.

**O custo subiu 56%.** A lista de temas acrescenta cerca de 180 tokens a cada
uma das 36 chamadas de classificação, e os tokens de entrada da análise
dobraram. É o lado do triângulo da aula 9 que esta mudança paga: mais qualidade,
mais custo.

Em valor absoluto, a análise de 36 respostas passou de menos de um centavo de
dólar para US$ 0,014. Com o orçamento de US$ 113 por mês para o LLM, isso ainda
dá cerca de 8 mil análises desse tamanho por mês. O cache compensa parte do
aumento: a análise repetida continua custando zero.

**A lista é desta empresa fictícia.** Um cliente real vai querer temas próprios,
e hoje a lista está fixa no código.
