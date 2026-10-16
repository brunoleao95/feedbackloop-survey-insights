"""Testes do cache e do seu mecanismo de exclusão.

Os testes de expiração usam um relógio falso: avançar 24 horas não pode
depender de esperar 24 horas.
"""

import csv
import sqlite3
from pathlib import Path

import pytest

from feedbackloop.cache import Cache
from feedbackloop.pipeline import analisar

RAIZ = Path(__file__).resolve().parent.parent
NOMES_PLANTADOS = ["Marcos Antunes", "Carolina Mendes", "João Pereira", "Fernanda Lima"]


class Relogio:
    def __init__(self, agora: float = 1_000_000.0):
        self.agora = agora

    def __call__(self) -> float:
        return self.agora


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def cache(tmp_path, relogio):
    return Cache(str(tmp_path / "cache.sqlite3"), ttl_segundos=24 * 3600, relogio=relogio)


class ClienteContador:
    """Dublê que conta chamadas ao provedor."""

    modelo = "modelo-de-teste"

    def __init__(self):
        self.chamadas = 0

    def completar(self, system: str, user: str, temperatura: float = 0.2) -> str:
        self.chamadas += 1
        if "Resposta da pesquisa" in user:
            return '{"tema": "Liderança", "sentimento": "negativo"}'
        return "Resumo de teste."


def _respostas_de_exemplo() -> list[str]:
    with open(RAIZ / "data" / "respostas-pesquisa-exemplo.csv", encoding="utf-8") as f:
        return [linha["resposta"] for linha in csv.DictReader(f)]


# ---------------------------------------------------------------------------
# O cache em si
# ---------------------------------------------------------------------------

def test_guarda_e_devolve(cache):
    cache.guardar("k", {"tema": "Liderança"})
    assert cache.obter("k") == {"tema": "Liderança"}


def test_chave_ausente_devolve_none(cache):
    assert cache.obter("nao-existe") is None


def test_valor_vencido_nao_e_devolvido(cache, relogio):
    cache.guardar("k", {"tema": "Liderança"})
    relogio.agora += 24 * 3600 + 1
    assert cache.obter("k") is None


def test_expurgo_apaga_de_fato_o_que_venceu(cache, relogio):
    """O mecanismo de exclusão da política de retenção, provado no próprio banco.

    Não basta a leitura ignorar o vencido: a linha precisa deixar de existir.
    """
    cache.guardar("antiga", {"tema": "A"})
    relogio.agora += 12 * 3600
    cache.guardar("recente", {"tema": "B"})
    relogio.agora += 12 * 3600 + 1  # "antiga" passou de 24h; "recente" ainda não

    apagadas = cache.expurgar()

    assert apagadas == 1
    with sqlite3.connect(cache.caminho) as con:
        chaves = {linha[0] for linha in con.execute("SELECT chave FROM cache")}
    assert chaves == {"recente"}


def test_gravar_tambem_dispara_o_expurgo(cache, relogio):
    """Sem tarefa agendada: o próprio uso do cache mantém a retenção em dia."""
    cache.guardar("antiga", {"tema": "A"})
    relogio.agora += 24 * 3600 + 1
    cache.guardar("nova", {"tema": "B"})
    assert cache.tamanho() == 1


def test_chave_nao_revela_o_conteudo():
    chave = Cache.chave("classificacao", "modelo", "prompt", "O gerente [PESSOA] some.")
    assert len(chave) == 64
    assert "gerente" not in chave


# ---------------------------------------------------------------------------
# O cache no pipeline
# ---------------------------------------------------------------------------

def test_segunda_analise_da_mesma_planilha_nao_chama_o_provedor(cache):
    """A otimização: reanalisar a mesma planilha deixa de pagar de novo."""
    respostas = _respostas_de_exemplo()

    primeiro = ClienteContador()
    r1 = analisar(primeiro, respostas, cache=cache)
    assert primeiro.chamadas == len(respostas) + 1
    assert r1.chamadas_llm == len(respostas) + 1
    assert r1.acertos_cache == 0

    segundo = ClienteContador()
    r2 = analisar(segundo, respostas, cache=cache)
    assert segundo.chamadas == 0
    assert r2.chamadas_llm == 0
    assert r2.acertos_cache == len(respostas) + 1

    # O cache não muda o resultado, só o caminho até ele.
    assert r2.resumo == r1.resumo
    assert [c["tema"] for c in r2.classificacoes] == [c["tema"] for c in r1.classificacoes]


def test_trocar_o_modelo_invalida_o_cache(cache):
    respostas = _respostas_de_exemplo()[:5]
    analisar(ClienteContador(), respostas, cache=cache)

    outro = ClienteContador()
    outro.modelo = "outro-modelo"
    analisar(outro, respostas, cache=cache)
    assert outro.chamadas == len(respostas) + 1


def test_o_cache_nao_guarda_texto_nem_nome(cache):
    """O arquivo do cache não contém dado pessoal. Ver a política de retenção."""
    analisar(ClienteContador(), _respostas_de_exemplo(), cache=cache)

    with sqlite3.connect(cache.caminho) as con:
        conteudo = " ".join(" ".join(map(str, linha)) for linha in con.execute("SELECT * FROM cache"))

    for nome in NOMES_PLANTADOS:
        assert nome not in conteudo
        assert nome.split()[0] not in conteudo
    assert "insustentável" not in conteudo  # trecho de uma resposta de exemplo
    assert "[PESSOA]" not in conteudo  # nem o texto sanitizado fica guardado


def test_falha_no_cache_nao_derruba_a_analise(tmp_path):
    class CacheQuebrado(Cache):
        def obter(self, chave):
            raise sqlite3.OperationalError("disco cheio")

        def guardar(self, chave, valor):
            raise sqlite3.OperationalError("disco cheio")

    quebrado = CacheQuebrado(str(tmp_path / "c.sqlite3"))
    cliente = ClienteContador()
    resultado = analisar(cliente, _respostas_de_exemplo()[:3], cache=quebrado)

    assert cliente.chamadas == 4
    assert resultado.total == 3


def test_resultado_fora_do_formato_nao_vai_para_o_cache(cache):
    """Guardar uma falha a repetiria por 24 horas, sem nova tentativa."""

    class ClienteQueErra(ClienteContador):
        def completar(self, system, user, temperatura=0.2):
            self.chamadas += 1
            return "isto nao e json" if "Resposta da pesquisa" in user else "Resumo."

    analisar(ClienteQueErra(), ["Resposta qualquer."], cache=cache)
    segundo = ClienteContador()
    analisar(segundo, ["Resposta qualquer."], cache=cache)
    assert segundo.chamadas >= 1
