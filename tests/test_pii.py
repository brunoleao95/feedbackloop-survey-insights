"""Testes da sanitização de PII.

Dois tipos de teste aqui. Os unitários fixam o que `sanitizar` garante para
cada tipo de dado. O de fronteira prova a propriedade que importa para a LGPD:
nenhum nome das respostas de exemplo chega ao cliente do LLM.
"""

import csv
from pathlib import Path

import pytest

from feedbackloop.pii import MARCADORES, sanitizar
from feedbackloop.pipeline import analisar

RAIZ = Path(__file__).resolve().parent.parent
NOMES_PLANTADOS = ["Marcos Antunes", "Carolina Mendes", "João Pereira", "Fernanda Lima"]


# ---------------------------------------------------------------------------
# Unitários
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("O gerente Marcos Antunes muda tudo.", "O gerente [PESSOA] muda tudo."),
        ("A Carolina Mendes, minha supervisora, cobra.", "A [PESSOA], minha supervisora, cobra."),
        ("O João Pereira sempre escuta.", "O [PESSOA] sempre escuta."),
        ("Falei com a Maria da Silva hoje.", "Falei com a [PESSOA] hoje."),
        ("Minha gestora Joana nunca responde.", "Minha gestora [PESSOA] nunca responde."),
    ],
)
def test_mascara_nomes_de_pessoa(entrada, esperado):
    assert sanitizar(entrada).texto == esperado


@pytest.mark.parametrize(
    "entrada, tipo",
    [
        ("Meu e-mail é joana.silva@empresa.com.br, me chamem.", "email"),
        ("Meu CPF é 123.456.789-09.", "cpf"),
        ("Liguem no (41) 99876-5432.", "telefone"),
        ("Meu ramal pessoal é 3222-1100.", "telefone"),
    ],
)
def test_mascara_dados_estruturados(entrada, tipo):
    resultado = sanitizar(entrada)
    assert MARCADORES[tipo] in resultado.texto
    assert resultado.contagem.get(tipo) == 1


@pytest.mark.parametrize(
    "texto",
    [
        "A carga de trabalho está insustentável.",
        "O salário está abaixo do mercado, uns 30% a menos.",
        "O pessoal do Recursos Humanos ajudou bastante.",
        "Gosto do Home Office duas vezes por semana.",
        "Tenho ótima relação com meu líder.",
    ],
)
def test_nao_mascara_texto_sem_pii(texto):
    """Falso positivo também custa: mascarar tema apaga o sinal da análise."""
    resultado = sanitizar(texto)
    assert resultado.texto == texto
    assert resultado.total == 0


def test_texto_vazio():
    assert sanitizar("").texto == ""
    assert sanitizar("").total == 0


# ---------------------------------------------------------------------------
# Fronteira: o que de fato chega ao provedor
# ---------------------------------------------------------------------------

class ClienteEspiao:
    """Dublê que registra tudo o que seria enviado ao provedor."""

    def __init__(self):
        self.enviados: list[str] = []

    def completar(self, system: str, user: str, temperatura: float = 0.2) -> str:
        self.enviados.append(system + "\n" + user)
        if "Resposta da pesquisa" in user:
            return '{"tema": "Liderança", "sentimento": "negativo"}'
        return "Resumo de teste."


def _respostas_de_exemplo() -> list[str]:
    with open(RAIZ / "data" / "respostas-pesquisa-exemplo.csv", encoding="utf-8") as f:
        return [linha["resposta"] for linha in csv.DictReader(f)]


def test_nenhum_nome_de_exemplo_chega_ao_provedor():
    """A garantia central da etapa: PII sanitizada antes de qualquer chamada.

    Roda o pipeline completo sobre as 36 respostas de exemplo com um cliente
    espião e verifica cada mensagem que seria enviada ao provedor.
    """
    respostas = _respostas_de_exemplo()
    assert any(nome in r for r in respostas for nome in NOMES_PLANTADOS), (
        "o CSV de exemplo deveria conter os nomes plantados; o teste perdeu o sentido"
    )

    espiao = ClienteEspiao()
    analisar(espiao, respostas)

    assert len(espiao.enviados) == len(respostas) + 1
    for mensagem in espiao.enviados:
        for nome in NOMES_PLANTADOS:
            assert nome not in mensagem, f"'{nome}' vazou para o provedor"
            assert nome.split()[0] not in mensagem, f"primeiro nome de '{nome}' vazou"


def test_resultado_registra_o_que_foi_mascarado():
    """O usuário precisa poder ver o que saiu, e não confiar no escuro."""
    espiao = ClienteEspiao()
    resultado = analisar(espiao, _respostas_de_exemplo())

    assert resultado.pii_mascarada.get("pessoa", 0) >= len(NOMES_PLANTADOS)
    com_nome = [c for c in resultado.classificacoes if "[PESSOA]" in c["texto_enviado"]]
    assert len(com_nome) >= len(NOMES_PLANTADOS)
