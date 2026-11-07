"""Testes da taxonomia fixa de temas.

Com o tema em aberto, 36 respostas viravam 23 temas. A taxonomia limita o
universo de temas, e estes testes garantem que nenhum caminho reabre a lista.
"""

import pytest

from feedbackloop.pipeline import (
    SYSTEM_CLASSIFICACAO,
    TEMA_OUTROS,
    TEMAS,
    analisar,
    normalizar_tema,
    parse_classificacao,
)


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("Liderança", "Liderança"),
        ("lideranca", "Liderança"),
        ("  CARGA   DE TRABALHO ", "Carga de trabalho"),
        ("Comunicacao interna", "Comunicação interna"),
        ("outros", TEMA_OUTROS),
        ("Salário", TEMA_OUTROS),  # sinônimo fora da lista não abre tema novo
        ("", TEMA_OUTROS),
    ],
)
def test_normalizar_tema(bruto, esperado):
    assert normalizar_tema(bruto) == esperado


def test_todo_tema_da_lista_esta_no_prompt():
    for tema in [*TEMAS, TEMA_OUTROS]:
        assert f"- {tema}:" in SYSTEM_CLASSIFICACAO


def test_parse_leva_tema_inventado_para_outros():
    dado = parse_classificacao('{"tema": "Saúde mental", "sentimento": "negativo"}')
    assert dado == {"tema": TEMA_OUTROS, "sentimento": "negativo"}


def test_parse_sem_json_continua_nao_classificado():
    """Falha de formato segue distinguível de tema fora da lista."""
    assert parse_classificacao("não sei")["tema"] == "Não classificado"


def test_analise_nunca_tem_mais_temas_que_a_taxonomia():
    class Criativo:
        modelo = "teste"
        n = 0

        def completar(self, system, user, temperatura=0.2):
            if "Resposta da pesquisa" not in user:
                return "Resumo."
            self.n += 1
            return '{"tema": "Tema inventado %d", "sentimento": "neutro"}' % self.n

    resultado = analisar(Criativo(), [f"resposta {i}" for i in range(30)])
    temas = {c["tema"] for c in resultado.classificacoes}
    assert temas <= {*TEMAS, TEMA_OUTROS}
