# Observabilidade com Langfuse: traces, spans e custo de cada análise.
#
# O ponto mais importante deste arquivo não é a instrumentação, é o que NÃO
# vai para o Langfuse. Ele é mais um serviço fora do Brasil recebendo dados do
# sistema, então vale para ele a mesma regra do provedor de LLM: nada
# identificável sai do processo. Ver docs/lgpd/mapa-de-dados.md, ponto 6.
#
# Duas camadas garantem isso:
#
#   1. Captura de entrada desligada em toda função que recebe texto cru
#      (analisar e a etapa de sanitização). Só o adaptador do LLM registra o
#      prompt, e ele recebe texto já sanitizado.
#   2. Uma função `mask` aplicada pelo próprio cliente do Langfuse a tudo o que
#      é exportado. Se algum dia alguém decorar uma função errada, a máscara
#      ainda pega o nome antes de ele sair.
#
# Sem as variáveis LANGFUSE_PUBLIC_KEY e LANGFUSE_SECRET_KEY o cliente se
# desativa sozinho. É assim que os testes e o CI rodam sem tocar a rede.

import os
import re
from functools import lru_cache

from langfuse import Langfuse, get_client, observe

from feedbackloop.pii import sanitizar

__all__ = ["iniciar", "observe", "cliente", "mascarar"]

# Terceira camada, para segredo e não para PII. Funções que recebem o objeto
# `cliente` carregam, dentro dele, o cliente da OpenAI com a chave de API. Se
# alguma delas tiver a captura de entrada ligada por engano, a serialização
# poderia exportar a chave. A sanitização de PII não pega isso: procura nomes,
# não credenciais.
_SEGREDO = re.compile(r"\b(?:sk|pk|rnd|gh[pousr])[-_][A-Za-z0-9_-]{16,}\b")


def mascarar(data, **_):
    """Aplica a sanitização de PII a qualquer estrutura antes da exportação.

    Recebe o que o Langfuse estiver prestes a enviar: texto, dicionário ou
    lista, em qualquer profundidade. Devolve a mesma estrutura com os textos
    sanitizados. Nunca levanta exceção: falhar aqui derrubaria a análise por
    causa da telemetria, que é exatamente o acoplamento a evitar.
    """
    try:
        if isinstance(data, str):
            return sanitizar(_SEGREDO.sub("[SEGREDO]", data)).texto
        if isinstance(data, dict):
            return {k: mascarar(v) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return type(data)(mascarar(v) for v in data)
        return data
    except Exception:
        return "[conteudo omitido: falha ao mascarar]"


@lru_cache(maxsize=1)
def iniciar() -> Langfuse:
    """Cria o cliente uma única vez por processo.

    O Streamlit reexecuta o script inteiro a cada interação. Sem o cache, cada
    clique criaria um cliente novo, com seu próprio exportador em segundo plano.
    """
    return Langfuse(
        mask=mascarar,
        environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "local"),
    )


def cliente() -> Langfuse:
    """Atalho para o cliente já iniciado."""
    iniciar()
    return get_client()


# O cliente com a máscara é criado AQUI, na importação do módulo, e não na
# primeira chamada ao LLM.
#
# Isso corrige um defeito encontrado em 16/10: o `@observe` de `analisar` roda
# antes de qualquer chamada a `iniciar()`, e o SDK cria um cliente padrão, sem
# máscara, para atendê-lo. A segunda e a terceira camadas de proteção ficavam
# desligadas em silêncio. Nenhum dado pessoal vazou porque a primeira camada,
# captura desligada sobre texto já sanitizado, segurou sozinha. Ver o teste
# tests/test_observabilidade.py::test_cliente_com_mascara_ativo_na_importacao.
#
# Todo módulo que usa `observe` o importa daqui, então importar este arquivo
# acontece antes de qualquer função decorada poder executar.
iniciar()
