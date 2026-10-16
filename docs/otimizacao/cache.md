# Otimização: cache das respostas do LLM

**Data da medição:** 16/10/2026, em produção, com o modelo real
**Código:** `feedbackloop/cache.py`, integrado em `feedbackloop/pipeline.py`

## O problema

A auditoria do protótipo registrou como lacuna 3: cada análise faz uma chamada ao
provedor por resposta, mais uma do resumo, **toda vez que roda**. Reanalisar a
mesma planilha paga tudo de novo e espera tudo de novo.

Isso não é cenário hipotético. Num uso real, o analista de RH roda a mesma
pesquisa mais de uma vez: depois de ler o primeiro resultado, para mostrar a um
gestor, ou porque a página foi recarregada. Cada vez custava o mesmo que a
primeira.

## A escolha

A aula 9 lista as estratégias de otimização com o ganho típico de cada uma, e o
cache aparece com redução de 50% a 90% de custo e de latência no caminho
cacheado, e complexidade baixa. A mesma aula dá a regra de prazo para este tipo
de dado: **respostas de LLM de classificação, TTL de 1 a 24 horas, com invalidação
quando o prompt muda**. É exatamente o caso deste sistema.

| Decisão | O que foi feito | Por quê |
|---|---|---|
| **O que guardar** | Só o resultado: tema e sentimento de cada resposta, e o texto do resumo | O cache não precisa do texto para funcionar, então não guarda |
| **Chave** | Hash SHA-256 do modelo, do prompt e do texto **já sanitizado** | Nenhuma resposta, nem sanitizada, fica legível no arquivo |
| **Invalidação** | O prompt e o modelo fazem parte da chave | Trocar qualquer um invalida sozinho. A aula fala em invalidação manual; aqui ela não depende de alguém lembrar |
| **Prazo** | 24 horas | O teto da faixa da aula 9 para classificação |
| **Exclusão** | `DELETE` em SQL na abertura do cache e a cada gravação | É o mecanismo da política de retenção. Ver abaixo |
| **O que não guardar** | Resultado fora do formato esperado | Guardar uma falha a repetiria por 24 horas sem nova tentativa |
| **Falha** | Cache com erro vira cache vazio | A análise nunca depende do cache para funcionar |

## Antes e depois

Três análises das mesmas 36 respostas de exemplo, em produção, medidas pelos
traces do Langfuse:

| | Antes: sem cache | Depois: 1ª análise | **Depois: análise repetida** |
|---|---|---|---|
| Latência da análise | 37,5 s | 29,6 s | **0,003 s** |
| Chamadas ao provedor | 37 | 37 | **0** |
| Custo | US$ 0,0089 | US$ 0,0087 | **US$ 0** |
| Observações enviadas ao Langfuse | 76 | 76 | **2** |
| Trace | `16aadd31` | `bade0e28` | `5efbd5ac` |

Na análise repetida, **as 37 etapas vieram do cache**: 36 classificações e o
resumo. A interface informa isso ao usuário: "37 de 37 etapas vieram do cache,
sem chamar o provedor".

### O que os números não dizem

**A primeira análise não ficou mais rápida por causa do cache.** A diferença de
37,5 s para 29,6 s é variação de latência do provedor: as análises sem cache já
tinham oscilado entre 34 s e 57 s. O cache só age quando o conteúdo se repete. Na
primeira vez que uma pesquisa é analisada, o ganho é zero, e o custo extra do
cache, consultar e gravar um arquivo local, não aparece na medição.

**A redução de 37,5 s para 0,003 s é real, mas é o melhor caso.** Ela vale para a
mesma planilha analisada de novo dentro de 24 horas. Uma pesquisa nova, com
respostas diferentes, não se beneficia.

### Um ganho que não estava previsto

A análise repetida envia **2 observações ao Langfuse em vez de 76**. O
[ADR-003](../adr/adr-003-observabilidade-com-langfuse.md) registrou que a cota
gratuita de 50 mil unidades por mês chega antes do orçamento de LLM: cerca de 650
análises. Cada análise repetida agora consome cerca de 3 unidades em vez de 77, e
a cota de observabilidade passa a durar mais na mesma proporção.

## Como reproduzir a medição

1. Fazer um deploy de produção, o que esvazia o cache, já que o disco do serviço
   é efêmero
2. Abrir a aplicação, usar os dados de exemplo e clicar em Analisar. A interface
   informa o tempo e o número de chamadas
3. Clicar em Analisar de novo, sem mudar nada
4. Conferir os dois traces no Langfuse, ambiente `prod`: o primeiro com 76
   observações e 37 chamadas, o segundo com 2 observações e nenhuma

Os testes em `tests/test_cache.py` reproduzem o mesmo comportamento offline, com
um dublê do provedor: a segunda análise da mesma planilha faz zero chamadas e
devolve exatamente o mesmo resumo e os mesmos temas.

## O trade-off: latência, custo e qualidade

A aula 9 apresenta o princípio como um triângulo em que se escolhem dois lados.
Este cache escolhe **latência e custo**, e o lado que paga a conta é o da
qualidade, em três pontos específicos.

**1. Resultado congelado por até 24 horas.** Se o provedor melhorar o modelo sem
trocar o nome dele, o cache continua devolvendo a classificação antiga até
expirar. O risco é baixo porque a classificação roda com temperatura zero, então
uma nova chamada tenderia a dar o mesmo resultado. Mas não é zero.

**2. O resumo deixa de variar.** O resumo é gerado com temperatura 0,3, ou seja,
com alguma variação de redação entre execuções. Com o cache, a mesma pesquisa
sempre recebe o mesmo texto. Para um relatório isso é até desejável, porque dois
gestores que abrirem a mesma análise vão ler a mesma coisa. Mas é uma escolha.

**3. O cache não melhora a qualidade, e pode esconder um problema dela.** A
pulverização de temas continua em 0,639, porque ela vem do prompt, e não da
falta de cache. Pior: com o cache, uma classificação ruim é repetida de graça por
24 horas, em vez de ganhar uma nova chance. Por isso só resultado no formato
esperado é guardado.

**Do lado da operação, há mais dois custos.**

**O cache não sobrevive a um deploy.** O disco do serviço no Render é efêmero,
então cada publicação começa com o cache vazio. Com o pipeline publicando a cada
mudança na `main`, a taxa de acerto real em produção vai ser menor do que a
medida aqui. Um cache persistente exigiria um serviço a mais, como um banco
externo, e não se justifica no volume atual.

**O cache é compartilhado entre clientes.** Duas empresas com uma resposta
idêntica, depois de sanitizada, recebem a mesma classificação do cache. Não há
vazamento, porque o que é compartilhado é só tema e sentimento, e a chave não é
reversível para o texto. Mas é um ponto a revisar se o sistema passar a ter
clientes com taxonomias diferentes.

## LGPD

O cache é o primeiro dado que o sistema realmente armazena, e por isso ele entrou
na [política de retenção](../lgpd/retencao-e-exclusao.md) antes de ir para
produção.

**Ele não contém dado pessoal.** O arquivo guarda o hash da chave, o tema, o
sentimento, o texto do resumo, que é gerado a partir de agregados, e a hora da
gravação. Um teste (`test_o_cache_nao_guarda_texto_nem_nome`) analisa as 36
respostas de exemplo e confere que o arquivo do cache não contém nenhum dos nomes
plantados, nenhum trecho de resposta e nem o texto sanitizado.

**A exclusão é real, e testada.** O `DELETE` roda na abertura e a cada gravação,
e a leitura ignora o que venceu mesmo antes de ser apagado. Um teste avança um
relógio falso em 24 horas e confirma, consultando o próprio banco, que a linha
deixou de existir.
