# Sanitização de dados pessoais antes de qualquer chamada ao provedor de LLM.
#
# Respostas de pesquisa de clima citam gestor, colega e quem saiu. Esse texto
# sai do Brasil a cada chamada ao provedor, então nada identificável pode ir.
# Ver docs/lgpd/mapa-de-dados.md.
#
# A abordagem é deliberadamente simples: expressões regulares e duas regras
# para nomes de pessoa. Não é NER. Ela pega o padrão que aparece nas respostas
# (nome e sobrenome no meio da frase, ou nome logo depois de um cargo) e erra
# em casos fora desse padrão. As limitações estão documentadas no fim do
# arquivo e no mapa de dados, e os testes em tests/test_pii.py fixam o que é
# garantido.

import re
from dataclasses import dataclass, field

MARCADORES = {
    "email": "[EMAIL]",
    "cpf": "[CPF]",
    "telefone": "[TELEFONE]",
    "pessoa": "[PESSOA]",
}

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
# Celular e fixo brasileiros, com ou sem DDD, com ou sem +55.
_TELEFONE = re.compile(
    r"(?<!\d)(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\s?)?\d{4}[-\s]?\d{4}(?!\d)"
)

_MAIUSCULA = r"[A-ZÀ-Ý][a-zà-ÿ]+"
_CONECTOR = r"(?:d[aeo]s?|e)"

# Regra 1: duas ou mais palavras capitalizadas em sequência, admitindo
# conectores ("Maria da Silva"). Pega "Carolina Mendes" e "João Pereira".
_SEQUENCIA_NOMES = re.compile(
    rf"\b{_MAIUSCULA}(?:\s+(?:{_CONECTOR}\s+)?{_MAIUSCULA})+\b"
)

# Regra 2: uma palavra capitalizada logo depois de um cargo. Pega "o gerente
# Marcos" mesmo sem sobrenome.
_CARGOS = (
    "gerente|gestora?|supervisora?|l[ií]der|chefe|coordenadora?|diretora?|"
    "colega|analista|cto|ceo|head|rh|lideran[çc]a"
)
_NOME_APOS_CARGO = re.compile(
    rf"(?i:\b(?:{_CARGOS})\b)\s+(?:(?i:a|o)\s+)?({_MAIUSCULA})\b"
)

# Palavras capitalizadas que não são nome de pessoa: início de frase comum e
# expressões corporativas. Sem isso, "A Carolina" mascararia o artigo junto, e
# "Recursos Humanos" viraria uma pessoa.
_NAO_NOMES = {
    "a", "o", "as", "os", "um", "uma", "eu", "ele", "ela", "nós", "eles",
    "elas", "mas", "e", "ou", "se", "quando", "hoje", "ontem", "aqui", "lá",
    "isso", "isto", "esse", "essa", "este", "esta", "meu", "minha", "nosso",
    "nossa", "tenho", "temos", "estamos", "faltam", "gosto", "acho", "sinto",
    "não", "sim", "muito", "pouco", "toda", "todo", "cada", "desde",
}
_EXPRESSOES_PERMITIDAS = {
    "recursos humanos", "home office", "black friday", "dia das mães",
    "segunda feira", "terça feira", "quarta feira", "quinta feira",
    "sexta feira",
}


@dataclass
class ResultadoSanitizacao:
    texto: str
    contagem: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.contagem.values())


def _registrar(contagem: dict, tipo: str, n: int) -> None:
    if n:
        contagem[tipo] = contagem.get(tipo, 0) + n


def _mascarar_sequencia(match: re.Match) -> str:
    """Mascara a sequência capitalizada, preservando palavras que não são nome."""
    palavras = match.group(0).split()
    # Remove do começo palavras de função e conectores que sobraram. Sem isso,
    # "Gosto do Home Office" vira "Gosto [PESSOA]": a regex aceita "do" como
    # conector de nome ("Maria do Carmo") e engole a preposição junto.
    prefixo = []
    while palavras and (palavras[0].lower() in _NAO_NOMES or palavras[0].islower()):
        prefixo.append(palavras.pop(0))
    nome = " ".join(palavras)
    capitalizadas = [p for p in palavras if p[:1].isupper()]
    if len(capitalizadas) < 2 or nome.lower() in _EXPRESSOES_PERMITIDAS:
        return match.group(0)
    return " ".join(prefixo + [MARCADORES["pessoa"]])


def sanitizar(texto: str) -> ResultadoSanitizacao:
    """Substitui dados pessoais por marcadores e conta o que foi mascarado.

    Função pura, sem efeito colateral e sem rede. A ordem importa: e-mail e CPF
    antes de telefone, para que dígitos de CPF não sejam lidos como telefone.
    """
    if not texto:
        return ResultadoSanitizacao(texto="", contagem={})

    contagem: dict = {}

    texto, n = _EMAIL.subn(MARCADORES["email"], texto)
    _registrar(contagem, "email", n)

    texto, n = _CPF.subn(MARCADORES["cpf"], texto)
    _registrar(contagem, "cpf", n)

    texto, n = _TELEFONE.subn(MARCADORES["telefone"], texto)
    _registrar(contagem, "telefone", n)

    antes = texto
    texto = _SEQUENCIA_NOMES.sub(_mascarar_sequencia, texto)
    _registrar(contagem, "pessoa", texto.count(MARCADORES["pessoa"]) - antes.count(MARCADORES["pessoa"]))

    def _cargo(m: re.Match) -> str:
        nome = m.group(1)
        if nome.lower() in _NAO_NOMES:
            return m.group(0)
        return m.group(0)[: m.start(1) - m.start(0)] + MARCADORES["pessoa"]

    antes = texto
    texto = _NOME_APOS_CARGO.sub(_cargo, texto)
    _registrar(contagem, "pessoa", texto.count(MARCADORES["pessoa"]) - antes.count(MARCADORES["pessoa"]))

    return ResultadoSanitizacao(texto=texto, contagem=contagem)


# LIMITAÇÕES CONHECIDAS
#
# - Nome isolado fora de contexto de cargo passa: "falei com a Fernanda ontem".
# - Apelido em minúscula passa: "o juninho do financeiro".
# - Identificação indireta passa: "a única mulher do time de dados". Isso não é
#   tratável por regra de texto e é a razão de a política exigir que dado real
#   só entre depois de revisão. Ver docs/lgpd/mapa-de-dados.md.
# - Pode haver falso positivo em nome de produto ou cliente com duas palavras
#   capitalizadas. Mascarar a mais é o erro aceitável; mascarar a menos não é.
