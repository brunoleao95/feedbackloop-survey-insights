# FeedbackLoop — Survey Insights: servidor web.
#
# Substitui a interface em Streamlit herdada do protótipo. A regra de negócio
# continua inteira em feedbackloop/; este arquivo só expõe uma API pequena e
# serve a página em static/. Ver docs/adr/adr-004-interface-web-com-fastapi.md.
#
# Roda com: uvicorn app:app --reload

import csv
import io
import json
import logging
import queue
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from feedbackloop.cache import cache_padrao
from feedbackloop.llm import ClienteLLM
from feedbackloop.observabilidade import cliente as observabilidade
from feedbackloop.pipeline import analisar

# Carrega o .env local, se existir. Em produção as variáveis vêm da plataforma e
# o arquivo não existe, então isto não faz nada lá.
load_dotenv()

RAIZ = Path(__file__).resolve().parent
ESTATICOS = RAIZ / "static"
CSV_EXEMPLO = RAIZ / "data" / "respostas-pesquisa-exemplo.csv"
COLUNA_RESPOSTA = "resposta"

# Limites de entrada. Uma análise faz uma chamada ao provedor por resposta, e a
# requisição fica aberta até o fim: sem teto, uma planilha grande prende o
# processo por minutos e consome o orçamento do mês de uma vez.
MAX_RESPOSTAS = 300
MAX_CARACTERES_POR_RESPOSTA = 2000
MAX_BYTES_CSV = 1_000_000

log = logging.getLogger("feedbackloop")

app = FastAPI(title="FeedbackLoop", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")


class PedidoAnalise(BaseModel):
    respostas: list[str] = Field(min_length=1)


class PedidoCsv(BaseModel):
    conteudo: str


def ler_respostas_csv(texto: str) -> list[str]:
    """Lê o CSV e devolve a coluna de respostas, sem linhas vazias.

    Só a coluna `resposta` é lida, de propósito: colunas como `setor`,
    combinadas com uma queixa específica, reidentificam alguém num time pequeno.
    Ver docs/lgpd/mapa-de-dados.md.
    """
    leitor = csv.DictReader(io.StringIO(texto.lstrip("﻿")))
    if not leitor.fieldnames or COLUNA_RESPOSTA not in leitor.fieldnames:
        colunas = ", ".join(leitor.fieldnames or []) or "nenhuma"
        raise ValueError(
            f"O CSV precisa ter uma coluna chamada '{COLUNA_RESPOSTA}'. "
            f"Colunas encontradas: {colunas}."
        )
    return [linha[COLUNA_RESPOSTA].strip() for linha in leitor if (linha[COLUNA_RESPOSTA] or "").strip()]


def validar(respostas: list[str]) -> list[str]:
    limpas = [r.strip() for r in respostas if r and r.strip()]
    if not limpas:
        raise HTTPException(422, "Nenhuma resposta com texto para analisar.")
    if len(limpas) > MAX_RESPOSTAS:
        raise HTTPException(
            422, f"Esta versão analisa até {MAX_RESPOSTAS} respostas por vez; recebi {len(limpas)}."
        )
    longas = sum(1 for r in limpas if len(r) > MAX_CARACTERES_POR_RESPOSTA)
    if longas:
        raise HTTPException(
            422,
            f"{longas} resposta(s) passam de {MAX_CARACTERES_POR_RESPOSTA} caracteres. "
            "Confira se o arquivo não juntou várias linhas numa só.",
        )
    return limpas


def serializar(resultado, duracao: float) -> dict:
    """Converte o resultado do pipeline no que a página precisa exibir."""
    return {
        "total": resultado.total,
        "duracao_s": round(duracao, 2),
        "chamadas_llm": resultado.chamadas_llm,
        "acertos_cache": resultado.acertos_cache,
        "pii_mascarada": resultado.pii_mascarada,
        "sentimentos": resultado.contagem_sentimentos,
        "temas": [{"tema": t, "quantidade": q} for t, q in resultado.top_temas],
        "texto_resumo": resultado.texto_resumo,
        "classificacoes": [
            {
                "resposta": c["resposta"],
                "texto_enviado": c["texto_enviado"],
                "tema": c["tema"],
                "sentimento": c["sentimento"],
            }
            for c in resultado.classificacoes
        ],
    }


@app.get("/", include_in_schema=False)
def pagina():
    return FileResponse(ESTATICOS / "index.html")


@app.get("/saude")
def saude():
    """Healthcheck barato: diz só que o processo está de pé."""
    return {"status": "ok"}


@app.get("/api/exemplo")
def exemplo():
    """As 36 respostas sintéticas de exemplo. Ver data/AVISO-DADOS-SINTETICOS.md."""
    return {"respostas": ler_respostas_csv(CSV_EXEMPLO.read_text(encoding="utf-8"))}


@app.post("/api/csv")
def importar_csv(pedido: PedidoCsv):
    if len(pedido.conteudo.encode("utf-8")) > MAX_BYTES_CSV:
        raise HTTPException(413, "Arquivo maior que 1 MB.")
    try:
        return {"respostas": ler_respostas_csv(pedido.conteudo)}
    except (ValueError, csv.Error) as erro:
        raise HTTPException(422, str(erro)) from None


@app.post("/api/analisar")
def api_analisar(pedido: PedidoAnalise):
    """Roda a análise e transmite o andamento em NDJSON, uma linha por evento.

    A análise leva dezenas de segundos. Em vez de deixar a página parada até o
    fim, cada resposta classificada vira um evento de progresso, e o último
    evento traz o resultado completo ou o erro.
    """
    respostas = validar(pedido.respostas)
    try:
        cliente = ClienteLLM()
    except KeyError:
        raise HTTPException(503, "OPENAI_API_KEY não configurada no servidor.") from None

    eventos: queue.Queue = queue.Queue()

    def trabalhar():
        try:
            try:
                cache = cache_padrao()
            except Exception:
                cache = None
            inicio = time.perf_counter()
            resultado = analisar(
                cliente,
                respostas,
                cache=cache,
                ao_progredir=lambda feitas, total: eventos.put(
                    {"tipo": "progresso", "feitas": feitas, "total": total}
                ),
            )
            eventos.put({"tipo": "resultado", **serializar(resultado, time.perf_counter() - inicio)})
        except Exception as erro:
            # O detalhe vai para o log do serviço; a página recebe só o tipo do
            # erro, sem nada que possa conter dado de entrada.
            log.exception("analise falhou")
            eventos.put({"tipo": "erro", "mensagem": f"A análise falhou: {type(erro).__name__}."})
        finally:
            # Força o envio do trace agora, em vez de esperar o próximo lote.
            try:
                observabilidade().flush()
            except Exception:
                pass
            eventos.put(None)

    threading.Thread(target=trabalhar, daemon=True).start()

    def transmitir():
        while (evento := eventos.get()) is not None:
            yield json.dumps(evento, ensure_ascii=False) + "\n"

    return StreamingResponse(transmitir(), media_type="application/x-ndjson")
