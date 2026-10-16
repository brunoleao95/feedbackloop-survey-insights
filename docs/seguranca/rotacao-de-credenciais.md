# Procedimento de rotação de credenciais

**Última revisão:** 16/10/2026

Este procedimento nasceu de uma rotação que deu errado pela metade, descrita no
histórico ao fim do documento. A lição dela está embutida nos passos: rotacionar
não é criar uma chave nova, é criar a nova **e revogar a antiga**. Quem só faz a
primeira metade acaba com duas chaves válidas e nenhuma ideia de qual está em uso.

## Segredo ou configuração

Seguindo a distinção da aula 7: configuração é o endereço da casa, segredo é a
chave. Só segredo entra neste procedimento.

| Item | Tipo | Por quê |
|---|---|---|
| `OPENAI_API_KEY` | **Segredo** | Quem tem gasta o crédito da conta e envia dados em nosso nome |
| `RENDER_API_KEY` | **Segredo** | Acesso total ao workspace: cria, publica e lê logs de todos os serviços |
| Token OAuth do `gh` | **Segredo** | Escreve no repositório, inclusive nos workflows |
| `RENDER_SERVICE_ID` | Configuração | Identificador. Sozinho, não dá poder nenhum |
| `SMOKE_URL` | Configuração | URL pública |

Uma inconsistência honesta: o `RENDER_SERVICE_ID` está guardado no GitHub como
*secret*, e não como *variable*. Não é risco, é excesso de cautela, mas tem um
custo: o GitHub mascara o valor como `***` nos logs, o que atrapalha diagnosticar
qual serviço o pipeline atingiu. O `SMOKE_URL`, pelo mesmo critério, já está
corretamente como variável.

## Inventário

Levantado em 16/10/2026 pela API do GitHub, pelo painel do Render e pelo ambiente
local. Os valores nunca são listados, só onde cada segredo vive.

| Segredo | Onde vive | Quem consome | Escopo |
|---|---|---|---|
| `OPENAI_API_KEY` de dev | Variável do serviço `feedbackloop-dev` no Render | Aplicação em desenvolvimento | Uma chave dedicada |
| `OPENAI_API_KEY` de prod | Variável do serviço `feedbackloop-prod` no Render | Aplicação em produção | Uma chave dedicada, diferente da de dev |
| `RENDER_API_KEY` do CI | *Repository secret* no GitHub | Job `deploy` do pipeline | Workspace inteiro do Render |
| `RENDER_API_KEY` local | Variável de usuário do Windows | Terminal e ferramentas locais | Workspace inteiro do Render |
| Token do `gh` | Cofre de credenciais do Windows | `git push` e `gh` | Repositório, incluindo `workflow` |

Repare que **nenhum segredo está em arquivo versionado**. O `.env` local está no
`.gitignore`, e o `.env.example` documenta o nome das variáveis sem nenhum valor.

## Quando rotacionar

| Gatilho | Prazo | Exemplo |
|---|---|---|
| **Suspeita de exposição** | **Imediato** | Chave aparece em captura de tela, log, commit ou mensagem |
| Saída de alguém que tinha acesso | No mesmo dia | Foi exatamente a situação herdada do Rafael |
| Rotina | A cada 90 dias | Reduz a janela de uso de uma chave vazada sem que se saiba |

Suspeita basta. Não é preciso provar que a chave foi usada indevidamente: o custo
de rotacionar à toa é de minutos, e o de não rotacionar quando devia é a conta do
provedor e os dados enviados em nome do sistema.

## Procedimento

A ordem dos passos evita a indisponibilidade: a chave antiga só é revogada depois
que a nova foi comprovada funcionando.

**1. Gerar a nova chave.** No painel do provedor, com um nome que diga onde ela
vai viver, como `feedbackloop-prod`. Uma chave por ambiente, nunca compartilhada.

**2. Configurar no destino.** No Render, na aba Environment do serviço correto.
No GitHub, em Settings, Secrets and variables, Actions. Copiar direto do provedor
para o destino, sem passar por arquivo, mensagem ou captura de tela.

**3. Reiniciar o processo.** **Este passo é o que mais se esquece.** No Render,
salvar uma variável **não** reinicia o processo em execução: as variáveis são
lidas quando o processo sobe. Sem um novo deploy, a aplicação continua com a
chave antiga, ou sem chave nenhuma, enquanto o painel mostra a nova. Isso
aconteceu neste projeto em 29/08: o painel exibia a chave configurada e a
aplicação respondia que ela não existia. O deploy pode ser disparado pelo
pipeline ou manualmente no painel.

**4. Verificar.** Rodar os smoke tests contra o ambiente:

```bash
SMOKE_URL=https://feedbackloop-prod.onrender.com pytest tests/smoke -v
```

E, para chave do provedor de LLM, executar uma análise real na interface: os
smoke tests constroem o cliente, mas não chamam a API.

**5. Revogar a antiga.** Só agora. No painel do provedor, apagar a chave
anterior. Se a verificação do passo 4 falhou, a antiga ainda está ali para voltar.

**6. Registrar.** Acrescentar uma linha ao histórico abaixo: data, segredo,
motivo e se a antiga foi revogada.

## Auditoria do histórico do Git

Rotacionar só resolve se a chave antiga não estiver também gravada no histórico
do repositório. Um segredo apagado do código continua acessível em qualquer
commit anterior.

Varredura executada em 16/10/2026 com o **gitleaks 8.30.1**, baixado da release
oficial com checksum SHA-256 conferido:

```bash
gitleaks git . --log-opts="--all" --redact -v
```

```
21 commits scanned.
scanned ~123710 bytes (123.71 KB) in 394ms
no leaks found
```

**Os 21 commits são o histórico inteiro.** O repositório tem 30 commits, dos
quais 9 são merges de promoção da `dev` para a `main`, sem nenhuma linha de
conteúdo próprio, conferido com `git diff-tree --cc`. O gitleaks escaneia os
commits que introduzem conteúdo, e os 21 restantes são todos eles.

Os testes contêm duas chaves falsas propositais, com o texto
`sk-chave-falsa-apenas-para-...`. O gitleaks não as acusou, porque além do
prefixo ele avalia entropia, e esse texto não tem a aleatoriedade de uma chave
real.

## Histórico de rotações

Este projeto não teve uma rotação completa executada segundo este procedimento.
Ele teve duas situações que motivaram escrevê-lo, registradas abaixo como lições,
porque são exatamente os dois modos de falha que os passos foram desenhados para
evitar.

| Data | Situação | Passo do procedimento que ela originou |
|---|---|---|
| 29/08/2026 | Nova `RENDER_API_KEY` criada para o CI porque a anterior foi perdida, sem revogar a antiga | Passo 5, revogar só depois de verificar, e passo 6, registrar se a antiga foi revogada |
| 29/08/2026 | Valor da `OPENAI_API_KEY` de dev parcialmente legível numa captura de tela da configuração | Gatilho de rotação imediata por suspeita de exposição, e a regra do passo 2 de nunca passar o valor por captura de tela |

### Lição 1: rotação pela metade gera chave órfã

Ao configurar o pipeline, a chave do Render já existente não estava à mão, e foi
criada uma nova para o GitHub. A antiga continuou válida. O resultado são duas
chaves com acesso total ao workspace, uma delas sem dono claro.

Esse é o modo de falha mais comum de rotação: criar a nova é a parte que todo
mundo faz, revogar a antiga é a que se esquece. Uma chave órfã não quebra nada,
e é justamente por isso que ninguém se lembra de apagá-la. Daí o passo 5 e o
registro obrigatório do passo 6.

### Lição 2: a captura de tela também é um canal de vazamento

Ao configurar a variável no Render, uma captura de tela da tela de configuração
foi compartilhada com o valor parcialmente legível. A chave nunca chegou ao
repositório, e o `gitleaks` confirma o histórico limpo, mas o valor saiu por
outro caminho.

A lição é que proteger o Git não basta: o valor de um segredo deve ir do provedor
direto para o destino, sem passar por captura de tela, mensagem ou documento. Se
passar, a política trata como suspeita de exposição e manda rotacionar.
