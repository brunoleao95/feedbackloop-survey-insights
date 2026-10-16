# Pipeline de análise de respostas abertas de pesquisa de clima.
# (Rafael)
#
# Fluxo (análise EM LOTE, não é chatbot):
#   1. classificar()  -> pra cada resposta, o LLM devolve {tema, sentimento}
#   2. agregar        -> conta temas e sentimentos (funções puras, testáveis)
#   3. resumir        -> o LLM gera um resumo executivo + ações recomendadas
#
# Separei de propósito as funções PURAS (parse_*, contar_*, montar_resumo) das
# que chamam o LLM (classificar_resposta, gerar_resumo, analisar). As puras dá
# pra testar offline sem mockar nada; as outras a gente mocka o cliente.

import json
import re
from collections import Counter
from dataclasses import dataclass, field

from feedbackloop.observabilidade import cliente as observabilidade
from feedbackloop.observabilidade import observe
from feedbackloop.pii import sanitizar

# Os três rótulos de sentimento que a gente aceita. Qualquer coisa fora disso
# o parser joga pra "neutro" (decisão preguiçosa, mas evita quebrar o pipeline).
SENTIMENTOS_VALIDOS = ("positivo", "neutro", "negativo")

SYSTEM_CLASSIFICACAO = """Você é um analista de RH especialista em clima organizacional.
Recebe UMA resposta aberta de uma pesquisa de engajamento de funcionários (em português do Brasil).
Sua tarefa: (1) identificar o TEMA principal em poucas palavras (ex: "Carga de trabalho",
"Liderança", "Remuneração", "Reconhecimento", "Ferramentas", "Home office", "Comunicação");
(2) classificar o SENTIMENTO como exatamente um entre: positivo, neutro, negativo.

Responda SOMENTE com um JSON no formato:
{"tema": "<tema curto>", "sentimento": "<positivo|neutro|negativo>"}
"""

SYSTEM_RESUMO = """Você é um consultor de people analytics.
Recebe um agregado de uma pesquisa de clima: principais temas com contagem e a
distribuição de sentimentos. Escreva, em português do Brasil, um RESUMO EXECUTIVO
curto (3 a 5 frases) para a liderança e, em seguida, de 3 a 5 AÇÕES RECOMENDADAS
objetivas. Seja direto e prático.
"""


# ---------------------------------------------------------------------------
# Funções PURAS (sem LLM) — fáceis de testar
# ---------------------------------------------------------------------------

def parse_sentimento(bruto: str) -> str:
    """Normaliza a string de sentimento devolvida pelo modelo.

    Aceita variações ("Positivo", "NEGATIVO ", "neutra") e cai pra "neutro"
    quando não reconhece. Nunca levanta exceção.
    """
    if not bruto:
        return "neutro"
    texto = bruto.strip().lower()
    # pega a primeira palavra-chave que aparecer
    if "positiv" in texto:
        return "positivo"
    if "negativ" in texto:
        return "negativo"
    if "neutr" in texto:
        return "neutro"
    return "neutro"


def parse_classificacao(bruto: str) -> dict:
    """Extrai {"tema", "sentimento"} do texto cru do LLM.

    Tenta achar um bloco JSON mesmo se vier embrulhado em ```json ... ```.
    Se não der pra parsear, devolve tema "Não classificado" e sentimento neutro.
    """
    tema = "Não classificado"
    sentimento_bruto = ""

    trecho = _extrair_json(bruto)
    if trecho is not None:
        try:
            dado = json.loads(trecho)
            tema = str(dado.get("tema", tema)).strip() or tema
            sentimento_bruto = str(dado.get("sentimento", ""))
        except (json.JSONDecodeError, AttributeError):
            pass

    return {"tema": tema, "sentimento": parse_sentimento(sentimento_bruto)}


def _extrair_json(texto: str):
    """Devolve a substring que parece um objeto JSON, ou None."""
    if not texto:
        return None
    # remove cercas de código markdown se existirem
    sem_cerca = re.sub(r"```(?:json)?", "", texto)
    inicio = sem_cerca.find("{")
    fim = sem_cerca.rfind("}")
    if inicio == -1 or fim == -1 or fim < inicio:
        return None
    return sem_cerca[inicio : fim + 1]


def contar_temas(temas: list[str]) -> list[tuple[str, int]]:
    """Agrega uma lista de temas em [(tema, contagem), ...] do maior pro menor.

    Em empate, desempata por ordem alfabética (pra saída determinística).
    """
    contagem = Counter(t for t in temas if t)
    return sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))


def contar_sentimentos(sentimentos: list[str]) -> dict:
    """Conta sentimentos garantindo as três chaves sempre presentes."""
    base = {s: 0 for s in SENTIMENTOS_VALIDOS}
    for s in sentimentos:
        rotulo = parse_sentimento(s)
        base[rotulo] += 1
    return base


def montar_resumo(
    top_temas: list[tuple[str, int]],
    contagem_sentimentos: dict,
    texto_llm: str,
    total: int,
) -> str:
    """Junta o cabeçalho determinístico (números) com o texto gerado pelo LLM.

    A ideia é não confiar só no LLM pros números: a parte de contagem é montada
    aqui, em código, e o texto qualitativo vem do modelo.
    """
    linhas = []
    linhas.append(f"# Resumo executivo — Pesquisa de clima ({total} respostas)\n")

    linhas.append("## Distribuição de sentimento")
    for rotulo in SENTIMENTOS_VALIDOS:
        qtd = contagem_sentimentos.get(rotulo, 0)
        pct = (qtd / total * 100) if total else 0
        linhas.append(f"- {rotulo.capitalize()}: {qtd} ({pct:.0f}%)")
    linhas.append("")

    linhas.append("## Principais temas")
    if top_temas:
        for tema, qtd in top_temas:
            linhas.append(f"- {tema}: {qtd}")
    else:
        linhas.append("- (nenhum tema identificado)")
    linhas.append("")

    linhas.append("## Leitura e ações recomendadas")
    linhas.append(texto_llm.strip() if texto_llm else "(sem texto do modelo)")

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Funções que CHAMAM o LLM (recebem um cliente com .completar(system, user))
# ---------------------------------------------------------------------------

# Captura de entrada desligada: o argumento `cliente` contém o cliente da OpenAI,
# com a chave de API, e seria serializado. A entrada útil, o texto sanitizado,
# já fica registrada na chamada ao LLM que está dentro deste span.
@observe(name="classificar-resposta", capture_input=False)
def _classificar(cliente, resposta: str) -> tuple[dict, bool]:
    """Classifica UMA resposta: devolve {"tema", "sentimento"}.

    Espera receber texto JÁ SANITIZADO. Quem garante isso é `analisar`, que é o
    único caminho do sistema até esta função. Chamar diretamente com texto cru
    envia PII para fora do Brasil. Ver feedbackloop/pii.py.
    """
    bruto = cliente.completar(
        system=SYSTEM_CLASSIFICACAO,
        user=f"Resposta da pesquisa:\n\"\"\"\n{resposta}\n\"\"\"",
        temperatura=0.0,
    )
    resultado = parse_classificacao(bruto)

    # Erro silencioso tornado visível. Os parsers caem para "Não classificado"
    # e "neutro" sem levantar exceção, e era impossível distinguir falha do
    # modelo de resultado legítimo. Agora a falha fica marcada no trace.
    formato_ok = resultado["tema"] != "Não classificado"
    sentimento_reconhecido = any(
        chave in (bruto or "").lower() for chave in ("positiv", "negativ", "neutr")
    )
    ok = formato_ok and sentimento_reconhecido
    if not ok:
        observabilidade().update_current_span(
            level="WARNING",
            status_message="saida do modelo fora do formato esperado; caiu no valor padrao",
            metadata={"saida_bruta": (bruto or "")[:300]},
        )
    return resultado, ok


def classificar_resposta(cliente, resposta: str) -> dict:
    """Contrato público: devolve só {"tema", "sentimento"}, como no protótipo.

    O indicador de formato fica em `_classificar`, usado por `analisar`, para
    não mudar o formato de retorno do qual outro código pode depender.
    """
    return _classificar(cliente, resposta)[0]


@observe(name="gerar-resumo", capture_input=False)
def gerar_resumo_llm(
    cliente,
    top_temas: list[tuple[str, int]],
    contagem_sentimentos: dict,
) -> str:
    """Pede pro LLM o texto qualitativo (leitura + ações)."""
    temas_fmt = "\n".join(f"- {t}: {q}" for t, q in top_temas) or "- (nenhum)"
    sent_fmt = ", ".join(f"{k}={v}" for k, v in contagem_sentimentos.items())
    user = (
        f"Principais temas (tema: contagem):\n{temas_fmt}\n\n"
        f"Distribuição de sentimento: {sent_fmt}\n\n"
        "Gere o resumo executivo e as ações recomendadas."
    )
    # Só agregados: temas e contagens. Nenhuma resposta individual entra aqui.
    observabilidade().update_current_span(
        input={"top_temas": top_temas, "sentimentos": contagem_sentimentos},
    )
    return cliente.completar(system=SYSTEM_RESUMO, user=user, temperatura=0.3)


@dataclass
class ResultadoAnalise:
    total: int
    classificacoes: list[dict] = field(default_factory=list)
    top_temas: list[tuple[str, int]] = field(default_factory=list)
    contagem_sentimentos: dict = field(default_factory=dict)
    resumo: str = ""
    # O que foi mascarado antes do envio, por tipo. Fica visível para o
    # usuário em vez de o sistema pedir confiança cega.
    pii_mascarada: dict = field(default_factory=dict)
    # Quantas chamadas ao provedor foram de fato feitas, e quantas o cache
    # evitou. Somadas, dão o número de respostas mais um, o resumo.
    chamadas_llm: int = 0
    acertos_cache: int = 0


# Entrada e saída desligadas: este é o único ponto do sistema que recebe as
# respostas cruas, com nomes, e a saída contém o texto original para exibição.
# O que vai para o trace é só o que está em `metadata`, no fim da função.
@observe(name="analise-pesquisa", capture_input=False, capture_output=False)
def analisar(cliente, respostas: list[str], top_n: int = 8, cache=None) -> ResultadoAnalise:
    """Pipeline ponta a ponta.

    Recebe a lista de respostas abertas e um `cliente` com método
    `.completar(system, user, temperatura)`. Nos testes esse cliente é um mock.

    Sem `cache`, faz 1 chamada de LLM por resposta mais 1 do resumo, toda vez
    que roda, como no protótipo. Com `cache`, o que já foi classificado nas
    últimas 24 horas volta sem chamar o provedor. Ver feedbackloop/cache.py.
    """
    respostas_limpas = [r.strip() for r in respostas if r and r.strip()]

    # Fronteira LGPD: nada sai deste processo sem passar por aqui. Toda a
    # sanitização acontece antes da primeira chamada ao provedor, o que deixa a
    # ordem visível na linha do tempo do trace. O span registra só contagens.
    pii_total: dict = {}
    sanitizadas = []
    with observabilidade().start_as_current_observation(
        as_type="span", name="sanitizar-pii"
    ) as span:
        for resp in respostas_limpas:
            s = sanitizar(resp)
            for tipo, n in s.contagem.items():
                pii_total[tipo] = pii_total.get(tipo, 0) + n
            sanitizadas.append(s)
        span.update(
            metadata={
                "respostas": len(respostas_limpas),
                "respostas_alteradas": sum(1 for s in sanitizadas if s.total),
                "pii_mascarada": pii_total,
            }
        )

    # Chave do cache: modelo, prompt e texto JÁ SANITIZADO. Trocar o prompt ou o
    # modelo muda a chave e invalida o cache sem intervenção manual.
    modelo = getattr(cliente, "modelo", "desconhecido")
    chamadas_llm = 0
    acertos_cache = 0

    def _ler_cache(chave):
        if cache is None:
            return None
        try:
            return cache.obter(chave)
        except Exception:
            # Cache quebrado vira cache vazio: a análise segue chamando o
            # provedor, como antes de o cache existir.
            return None

    def _gravar_cache(chave, valor):
        if cache is None:
            return
        try:
            cache.guardar(chave, valor)
        except Exception:
            pass

    classificacoes = []
    for resp, s in zip(respostas_limpas, sanitizadas):
        chave = cache.chave("classificacao", modelo, SYSTEM_CLASSIFICACAO, s.texto) if cache else None
        guardado = _ler_cache(chave)
        if guardado is not None:
            c, ok = dict(guardado), True
            acertos_cache += 1
        else:
            c, ok = _classificar(cliente, s.texto)
            chamadas_llm += 1
            # Só resultado no formato certo vai para o cache. Guardar uma falha
            # a repetiria por 24 horas sem nova tentativa.
            if ok:
                _gravar_cache(chave, {"tema": c["tema"], "sentimento": c["sentimento"]})
        c["formato_ok"] = ok
        # O texto original fica só em memória, para exibição a quem enviou a
        # planilha. Ele não é passado a nenhuma função observada.
        c["resposta"] = resp
        c["texto_enviado"] = s.texto
        classificacoes.append(c)

    top_temas = contar_temas([c["tema"] for c in classificacoes])[:top_n]
    contagem = contar_sentimentos([c["sentimento"] for c in classificacoes])

    # O resumo também vai para o cache. A entrada dele são só agregados, então a
    # chave depende dos temas e das contagens, e não de nenhuma resposta.
    chave_resumo = (
        cache.chave("resumo", modelo, SYSTEM_RESUMO, top_temas, contagem) if cache else None
    )
    guardado = _ler_cache(chave_resumo)
    if guardado is not None:
        texto = guardado["texto"]
        acertos_cache += 1
    else:
        texto = gerar_resumo_llm(cliente, top_temas, contagem)
        chamadas_llm += 1
        if texto:
            _gravar_cache(chave_resumo, {"texto": texto})
    resumo = montar_resumo(top_temas, contagem, texto, len(respostas_limpas))

    # Métricas de qualidade da análise, usadas no dashboard. São indicadores
    # indiretos: o sistema não tem gabarito para saber se um tema está certo,
    # mas sabe se o modelo respondeu no formato e se a agregação se pulverizou.
    temas_distintos = len({c["tema"] for c in classificacoes})
    falhas_formato = sum(1 for c in classificacoes if not c.get("formato_ok", True))
    total = len(respostas_limpas)
    observabilidade().update_current_span(
        metadata={
            "respostas": total,
            "chamadas_llm": chamadas_llm,
            "acertos_cache": acertos_cache,
            "taxa_acerto_cache": round(acertos_cache / (total + 1), 3) if total else 0,
            "pii_mascarada": pii_total,
            "temas_distintos": temas_distintos,
            "pulverizacao_temas": round(temas_distintos / total, 3) if total else 0,
            "falhas_formato": falhas_formato,
            "taxa_formato_valido": round(1 - falhas_formato / total, 3) if total else 1,
            "sentimentos": contagem,
        }
    )

    return ResultadoAnalise(
        total=len(respostas_limpas),
        classificacoes=classificacoes,
        top_temas=top_temas,
        contagem_sentimentos=contagem,
        resumo=resumo,
        pii_mascarada=pii_total,
        chamadas_llm=chamadas_llm,
        acertos_cache=acertos_cache,
    )
