# ADR-003: Observabilidade com Langfuse, instrumentado manualmente

## Status

Aceito em 2026-10-16.

## Contexto

O sistema estava em produção sem nenhum log, métrica ou rastro. A auditoria do
protótipo já tinha apontado o pior efeito disso: os parsers engolem erro e
devolvem "neutro" ou "Não classificado" em silêncio, então uma falha do modelo é
indistinguível de um resultado legítimo. O post-mortem de 29/08 acrescentou o
segundo: a queda de produção foi descoberta porque havia uma pessoa olhando a
tela, e não por algum sinal do sistema.

Preciso de instrumentação que cubra o fluxo real com traces e spans, que meça
latência, custo, erro, volume e qualidade, e que sustente um alerta.

As restrições são quatro. Orçamento curto, já consumido pelo LLM e pela
hospedagem. Serviço de produção com 512 MB de memória. Nenhum dado identificável
pode sair do processo, e qualquer ferramenta de observabilidade é mais um destino
fora do Brasil. E o material da disciplina não prescreve ferramenta: a aula 2
cita o Langfuse como a observabilidade típica da stack B, sem detalhar uso.

## Decisão

Adotar o **Langfuse Cloud**, região **União Europeia**, plano gratuito, com o SDK
Python 5.0.2 e **instrumentação manual** pelo decorator `@observe`, em
`feedbackloop/observabilidade.py`.

Cada análise vira um trace com spans para a sanitização, para cada classificação
e para o resumo, e uma *generation* por chamada ao LLM, com modelo, prompt,
resposta, tokens e latência. Um par de chaves por ambiente, e o atributo
`environment` separa dev de prod no mesmo projeto.

## Consequências

**Positivas.** O erro silencioso deixa de ser silencioso: quando o modelo
responde fora do formato, o span da classificação é marcado como `WARNING` com a
saída bruta, e isso vira métrica. Custo e latência passam a existir por chamada,
e não como estimativa extrapolada de uma nota do antecessor. A estrutura do
trace mostra a sanitização acontecendo antes da primeira chamada ao provedor, o
que transforma uma afirmação do mapa de dados em algo verificável. Sem as chaves,
o cliente se desativa sozinho, então testes e CI seguem sem rede.

**Negativas, e são cinco.**

Primeira: é um segundo processador fora do Brasil. Mesmo com as três camadas de
proteção, o texto sanitizado e as respostas do modelo passam a existir também na
União Europeia. Entrou como ponto 6 do mapa de dados.

Segunda: no plano gratuito os dados ficam acessíveis por 30 dias e não há
retenção configurável. Sei por quanto tempo o dado é visível, mas não controlo
quando ele é apagado.

Terceira: a cota é de 50 mil unidades por mês. Uma análise das 36 respostas de
exemplo gera cerca de 77 unidades, o trace mais 76 observações, o que dá perto de
650 análises por mês. Numa pesquisa de 2.000 respostas, seriam cerca de 12. O
limite de observabilidade chega antes do limite de orçamento de LLM.

Quarta: dependências novas, e uma delas quebrou o ambiente na instalação. O SDK
puxou `protobuf` 7.x, que o Streamlit 1.40 não aceita, e o pip instalou com
apenas um aviso. Foi corrigido fixando `protobuf` e as dependências de
OpenTelemetry no `requirements.txt`, pela mesma lição do incidente do `httpx`.

Quinta: acoplamento entre telemetria e análise. Uma falha no Langfuse não pode
derrubar a análise, então a máscara nunca levanta exceção e o envio ao fim de
cada análise é protegido. Isso também significa que telemetria pode se perder em
silêncio, o que é aceitável para observabilidade e inaceitável para auditoria.

O custo em memória medido localmente foi de cerca de 5 MB na importação, sobre
uma base de 120 MB. A medição é local e não inclui o buffer do exportador em
execução, então o número de referência é o das métricas do Render em produção.

## Alternativas consideradas

**Métricas nativas do Render e logs estruturados.** Gratuito e sem novo
processador de dados, mas não atende o requisito central: o Render mede CPU,
memória e requisições HTTP, e não sabe o que é uma chamada ao LLM, um token ou
uma classificação fora do formato. Teria logs, não traces. Continua sendo usado
para as métricas de infraestrutura, que o Langfuse não vê.

**OpenTelemetry puro para um backend genérico**, como Grafana Cloud. É padrão
aberto e evitaria acoplamento a um fornecedor, e o próprio Langfuse é construído
sobre ele. Descartado porque um backend genérico não entende LLM: tokens, custo
por modelo e prompt teriam de ser modelados à mão, para o mesmo resultado.

**Integração automática do Langfuse com o SDK da OpenAI.** Capturaria cada
chamada sem decorator. Descartada por controle: a decisão mais importante desta
instrumentação é o que **não** é capturado, e isso exige dizer explicitamente,
função por função, onde a entrada pode ser registrada. Como todas as chamadas já
passam por um único adaptador, a instrumentação manual custa pouco a mais.

**A "skill" de instalação sugerida pelo próprio Langfuse**, que propõe que um
assistente de código instale um pacote externo e instrumente a aplicação.
Descartada pelo mesmo motivo da anterior, e por um segundo: aplicar mudanças
automáticas de terceiros num sistema que trata dado pessoal tira de mim a decisão
sobre o que é exportado.
