# Matriz de decisão de stack

> **Este documento foi escrito em duas etapas, de propósito.**
> Este commit contém apenas os critérios e os pesos, definidos **antes** de eu
> avaliar qualquer opção. As notas entram em um commit posterior. A ordem está
> registrada no histórico do Git e é verificável com `git log --follow` neste
> arquivo.
>
> A razão é simples: se eu olhasse as opções primeiro e pesasse depois, a matriz
> viraria só um espelho da preferência que eu já tinha, e não uma decisão.

## De onde vêm os critérios

Os seis critérios saíram de duas fontes, ambas anteriores a qualquer avaliação
técnica: o `BRIEFING.md` da FeedbackLoop e as restrições operacionais desta fase
do projeto. Nenhum foi escolhido olhando para uma tecnologia específica.

| # | Critério | Origem |
|---|---|---|
| 1 | Custo mensal dentro de US$ 120 | Briefing: "É startup, o caixa é curto, otimize custo desde já (cache não é luxo, é sobrevivência)" |
| 2 | Esforço de migração a partir do protótipo herdado | Regra do projeto: aceitar e evoluir o protótipo, nunca reescrever do zero |
| 3 | Isolamento real entre dev e prod, com secrets distintos | Requisito operacional da fase: ambientes separados são pré-condição para operar com segurança |
| 4 | Deploy disparado por GitHub Actions em menos de 5 minutos | Requisito operacional da fase: push na branch principal precisa publicar sozinho |
| 5 | Caminho para a fase final do projeto | O mesmo sistema segue por 12 semanas e precisa terminar como aplicação de verdade, não como protótipo |
| 6 | Meu domínio da ferramenta | Preciso saber explicar e sustentar a escolha, não só fazê-la funcionar uma vez |

## Pesos

Soma 100. Definidos em 29/08/2026, antes de avaliar qualquer opção.

| # | Critério | Peso |
|---|---|---|
| 1 | Custo mensal dentro de US$ 120 | 15 |
| 2 | Esforço de migração a partir do herdado | 15 |
| 3 | Isolamento dev/prod com secrets distintos | 20 |
| 4 | Deploy por GitHub Actions em menos de 5 min | 25 |
| 5 | Caminho para a fase final | 15 |
| 6 | Meu domínio da ferramenta | 10 |
| | **Total** | **100** |

### Por que estes pesos

O entregável desta fase não é uma funcionalidade nova: é **capacidade de
operação**. A Bia não pediu um recurso a mais no produto, pediu que o protótipo
do Rafael saia da máquina dele e vire algo que o time consiga usar e que eu
consiga sustentar. Por isso os dois critérios de operação, deploy automatizado
(25) e isolamento dev/prod (20), somam 45 e dominam a matriz.

O custo ficou em 15, e não mais alto, por um motivo concreto: as quatro opções
de hospedagem que o briefing autoriza têm tier gratuito ou de poucos dólares
para o volume do piloto. O gargalo real de custo neste projeto é o número de
chamadas de LLM, que hoje é de uma por resposta sem nenhum cache, e isso não
muda com a escolha de hospedagem. Pesar custo de infraestrutura mais alto seria
inflar um critério que na prática quase não separa as opções.

O esforço de migração ficou em 15 porque a regra do projeto já elimina a
reescrita completa. Ele ainda importa para diferenciar quanto de adaptação cada
caminho exige, mas não precisa dominar: a restrição principal já está dada.

O caminho para a fase final entrou com 15 porque o mesmo sistema segue por 12
semanas. Não quero montar uma infraestrutura agora para descartá-la depois.

Meu domínio ficou em 10, o menor. É um critério legítimo, porque preciso saber
defender a escolha, mas é o que mais corre risco de virar viés de conforto: se
pesasse alto, eu estaria escolhendo o que já conheço e chamando isso de análise.

## Escala de notas

Ainda **não** aplicada. Cada opção receberá de 1 a 5 em cada critério:

| Nota | Significado |
|---|---|
| 5 | Atende plenamente, sem trabalho adicional relevante |
| 4 | Atende, com ajuste pequeno |
| 3 | Atende parcialmente, com trabalho relevante |
| 2 | Atende mal, exige contorno |
| 1 | Não atende |

Pontuação final de cada opção: soma de (peso x nota). Máximo teórico: 500.

## Notas

Aplicadas em 29/08/2026, depois que os pesos já estavam commitados.

### Matriz 1: escolha de stack

| Critério | Peso | Stack A (n8n) | Stack B (Streamlit) | Stack C (Make) |
|---|---|---|---|---|
| 1. Custo <= US$ 120 | 15 | 4 | 5 | 3 |
| 2. Esforço de migração | 15 | 2 | 5 | 1 |
| 3. Isolamento dev/prod | 20 | 4 | 5 | 2 |
| 4. Deploy por Actions <5min | 25 | 4 | 5 | 2 |
| 5. Caminho para a fase final | 15 | 2 | 4 | 1 |
| 6. Meu domínio | 10 | 3 | 4 | 3 |
| **Total** | | **330** | **475** | **195** |

**Resultado: stack B, com 475 de 500.**

O critério que mais separa é o esforço de migração. O protótipo herdado são 918
linhas de Python organizadas em um pacote (`feedbackloop/`) com 7 testes
passando offline. Migrar para a stack A ou C significa recodar essa lógica como
nós de workflow ou como cenários low-code, descartando a suíte de testes junto.
É exatamente a reescrita que a regra do projeto proíbe.

Ressalva honesta: **nenhuma das três stacks evita a migração de interface na
fase final** do projeto, que exige sair de uma tela de protótipo para uma
aplicação de verdade. A stack B recebeu 4 e não 5 nesse critério por isso. O que
ela oferece é que a lógica de domínio no pacote `feedbackloop/` é reaproveitável
integralmente: vira uma API, e só a camada de apresentação é substituída.

### Matriz 2: onde hospedar

| Critério | Peso | Streamlit Cloud | HF Spaces | Render | Vercel |
|---|---|---|---|---|---|
| 1. Custo <= US$ 120 | 15 | 5 | 5 | 4 | 4 |
| 2. Esforço de migração | 15 | 5 | 4 | 4 | 1 |
| 3. Isolamento dev/prod | 20 | 4 | 5 | 5 | 5 |
| 4. Deploy por Actions <5min | 25 | 2 | 5 | 5 | 5 |
| 5. Caminho para a fase final | 15 | 2 | 4 | 5 | 3 |
| 6. Meu domínio | 10 | 2 | 2 | 5 | 5 |
| **Total** | | **330** | **440** | **470** | **395** |

**Resultado: Render, com 470 de 500.**

Usei deliberadamente os mesmos seis critérios e os mesmos pesos da matriz 1.
Inventar um segundo conjunto de pesos para esta decisão reintroduziria
exatamente o viés que a primeira matriz existe para evitar.

Três observações que valem mais que o número final:

**Streamlit Cloud tira 2 no critério de maior peso.** É a opção mais cômoda e a
mais óbvia para quem herdou um app Streamlit, mas ela faz auto-deploy pela
própria integração com o Git, e não pelo pipeline. Dá para manter um GitHub
Actions rodando os testes, porém o deploy não é disparado por ele. A exigência
desta fase é que o push na branch principal dispare o deploy pelo CI/CD, e não
que a plataforma observe o repositório por conta própria. São coisas diferentes.

**Vercel tira 1 em esforço de migração.** Streamlit não roda bem em ambiente
serverless, então adotar Vercel agora significaria reescrever a interface antes
mesmo de publicar a primeira URL. Vercel volta a ser candidato forte na fase
final, quando a interface for reconstruída.

**A decisão foi tomada por um empate desfeito no critério 6.** Antes de pontuar
meu próprio domínio, HF Spaces e Render estavam empatados em 450. Registro isso
porque o critério de familiaridade é o que mais corre risco de virar viés de
conforto, e aqui ele foi decisivo. Testei a robustez: mesmo que HF Spaces
recebesse 4 em domínio em vez de 2, chegaria a 460 e ainda perderia. A escolha
não depende dessa nota.

### Consequências que já vejo

O tier gratuito do Render hiberna por inatividade, o que produz cold start e
conflita com o requisito de URL estável durante a avaliação. O plano pago mais
barato resolve isso e cabe com folga nos US$ 120/mês do briefing, já que o custo
dominante do projeto é o de LLM, não o de hospedagem. Preciso confirmar os
valores e a política de hibernação vigentes antes de fechar o ADR-002.
