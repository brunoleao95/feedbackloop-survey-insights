"""Testes da API web (app.py), com o provedor substituído por um dublê.

Rodam offline e sem custo, como o resto da suíte. Cobrem o contrato que a
página usa: carregar o exemplo, ler um CSV, analisar com progresso e recusar
entrada fora dos limites.
"""

import json

import pytest
from fastapi.testclient import TestClient

import app as modulo
from feedbackloop.cache import Cache

NOMES_PLANTADOS = ["Marcos Antunes", "Carolina Mendes", "João Pereira", "Fernanda Lima"]


class ClienteFalso:
    modelo = "modelo-de-teste"

    def __init__(self):
        self.mensagens = []

    def completar(self, system, user, temperatura=0.2):
        self.mensagens.append(user)
        if "Resposta da pesquisa" in user:
            return '{"tema": "Liderança", "sentimento": "negativo"}'
        return "Resumo de teste.\n\n1. Primeira ação."


@pytest.fixture
def falso(monkeypatch, tmp_path):
    cliente = ClienteFalso()
    monkeypatch.setattr(modulo, "ClienteLLM", lambda: cliente)
    monkeypatch.setattr(modulo, "cache_padrao", lambda: Cache(str(tmp_path / "c.sqlite3")))
    return cliente


@pytest.fixture
def api():
    return TestClient(modulo.app)


def _eventos(resposta) -> list[dict]:
    return [json.loads(linha) for linha in resposta.text.splitlines() if linha]


def test_saude(api):
    assert api.get("/saude").json() == {"status": "ok"}


def test_pagina_e_servida(api):
    resposta = api.get("/")
    assert resposta.status_code == 200
    assert 'id="app"' in resposta.text
    assert api.get("/static/app.js").status_code == 200


def test_exemplo_traz_as_36_respostas(api):
    assert len(api.get("/api/exemplo").json()["respostas"]) == 36


def test_csv_le_so_a_coluna_resposta(api):
    conteudo = "id,setor,resposta\n1,RH,Gosto do time\n2,TI,\n3,TI,Falta ferramenta\n"
    assert api.post("/api/csv", json={"conteudo": conteudo}).json() == {
        "respostas": ["Gosto do time", "Falta ferramenta"]
    }


def test_csv_sem_a_coluna_explica_o_que_faltou(api):
    resposta = api.post("/api/csv", json={"conteudo": "id,comentario\n1,oi\n"})
    assert resposta.status_code == 422
    assert "resposta" in resposta.json()["detail"]
    assert "comentario" in resposta.json()["detail"]


def test_analise_transmite_progresso_e_termina_com_resultado(api, falso):
    respostas = api.get("/api/exemplo").json()["respostas"]
    eventos = _eventos(api.post("/api/analisar", json={"respostas": respostas}))

    progresso = [e for e in eventos if e["tipo"] == "progresso"]
    assert [e["feitas"] for e in progresso] == list(range(1, 38))
    assert eventos[-1]["tipo"] == "resultado"

    resultado = eventos[-1]
    assert resultado["total"] == 36
    assert resultado["sentimentos"]["negativo"] == 36
    assert resultado["temas"] == [{"tema": "Liderança", "quantidade": 36}]
    assert resultado["pii_mascarada"] == {"pessoa": 4}
    assert resultado["texto_resumo"].startswith("Resumo de teste.")


def test_nenhum_nome_chega_ao_provedor_pela_api(api, falso):
    """A fronteira LGPD vale também no caminho novo, pela web."""
    respostas = api.get("/api/exemplo").json()["respostas"]
    api.post("/api/analisar", json={"respostas": respostas})
    enviado = "\n".join(falso.mensagens)
    for nome in NOMES_PLANTADOS:
        assert nome.split()[0] not in enviado


def test_segunda_analise_vem_do_cache(api, falso):
    respostas = ["Gosto do time.", "Falta ferramenta."]
    api.post("/api/analisar", json={"respostas": respostas})
    resultado = _eventos(api.post("/api/analisar", json={"respostas": respostas}))[-1]
    assert resultado["chamadas_llm"] == 0
    assert resultado["acertos_cache"] == 3


def test_recusa_lista_vazia_ou_grande_demais(api, falso):
    assert api.post("/api/analisar", json={"respostas": ["   "]}).status_code == 422
    grande = ["resposta"] * (modulo.MAX_RESPOSTAS + 1)
    assert api.post("/api/analisar", json={"respostas": grande}).status_code == 422
    assert falso.mensagens == []


def test_sem_chave_responde_503_com_mensagem(api, monkeypatch):
    def sem_chave():
        raise KeyError("OPENAI_API_KEY")

    monkeypatch.setattr(modulo, "ClienteLLM", sem_chave)
    resposta = api.post("/api/analisar", json={"respostas": ["oi"]})
    assert resposta.status_code == 503
    assert "OPENAI_API_KEY" in resposta.json()["detail"]


def test_falha_do_provedor_vira_evento_de_erro_sem_detalhe(api, monkeypatch, tmp_path):
    class Quebrado(ClienteFalso):
        def completar(self, system, user, temperatura=0.2):
            raise RuntimeError("Marcos Antunes estourou o limite")

    monkeypatch.setattr(modulo, "ClienteLLM", Quebrado)
    monkeypatch.setattr(modulo, "cache_padrao", lambda: Cache(str(tmp_path / "c.sqlite3")))
    eventos = _eventos(api.post("/api/analisar", json={"respostas": ["oi"]}))
    assert eventos[-1] == {"tipo": "erro", "mensagem": "A análise falhou: RuntimeError."}
