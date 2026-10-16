"""Testes da máscara aplicada a tudo o que é exportado para o Langfuse.

A máscara é a segunda e a terceira camada de proteção: a primeira é não capturar
entrada nas funções que veem texto cru. Estes testes garantem que, mesmo se a
primeira camada falhar, nome de pessoa e chave de API não saem do processo.
"""

from feedbackloop.observabilidade import mascarar


def test_mascara_nome_em_estrutura_aninhada():
    exportado = {
        "input": [{"role": "user", "content": "O gerente Marcos Antunes some toda sexta."}],
        "metadata": {"nota": "citou a Carolina Mendes"},
    }
    resultado = mascarar(exportado)
    texto = str(resultado)
    assert "Marcos" not in texto
    assert "Carolina" not in texto
    assert "[PESSOA]" in texto
    # A estrutura é preservada: o Langfuse precisa receber o mesmo formato.
    assert resultado["input"][0]["role"] == "user"


def test_mascara_chave_de_api():
    """Um objeto cliente serializado por engano carregaria a chave da OpenAI."""
    chave_falsa = "sk-proj-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
    resultado = mascarar({"cliente": {"api_key": chave_falsa}})
    assert chave_falsa not in str(resultado)
    assert "[SEGREDO]" in str(resultado)


def test_preserva_valores_que_nao_sao_texto():
    dado = {"tokens": 120, "custo": 0.0004, "ok": True, "vazio": None}
    assert mascarar(dado) == dado


def test_nunca_levanta_excecao():
    """Falhar na telemetria não pode derrubar a análise."""

    class Estranho:
        def __iter__(self):
            raise RuntimeError("nao itere")

    assert mascarar(Estranho()) is not None
    assert mascarar(None) is None


def test_cliente_com_mascara_ativo_na_importacao():
    """Regressão do defeito de 16/10: a máscara precisa existir antes do 1º @observe.

    O cliente com máscara era criado só na primeira chamada ao LLM. O `@observe`
    de `analisar` roda antes disso, e o SDK atendia com um cliente padrão, sem
    máscara: um nome em texto cru, numa função com captura ligada, saía em claro.

    Roda num interpretador separado, com chaves falsas, porque é com chaves que
    o defeito aparece: sem elas o SDK usa um cliente inativo e o teste passaria
    sem provar nada. A URL aponta para uma porta fechada, então nada sai da
    máquina.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    ambiente = {
        **os.environ,
        "LANGFUSE_PUBLIC_KEY": "pk-lf-teste-local",
        "LANGFUSE_SECRET_KEY": "sk-lf-teste-local",
        "LANGFUSE_BASE_URL": "http://127.0.0.1:9",
        "PYTHONPATH": str(raiz),
    }
    verificacao = "; ".join([
        "import feedbackloop.pipeline",
        "from langfuse import get_client",
        "from feedbackloop.observabilidade import mascarar",
        "print('MASCARA_ATIVA' if get_client()._mask is mascarar else 'SEM_MASCARA')",
    ])
    saida = subprocess.run(
        [sys.executable, "-c", verificacao],
        cwd=raiz, env=ambiente, capture_output=True, text=True, timeout=60,
    )
    assert "MASCARA_ATIVA" in saida.stdout, (
        "o cliente ativo do Langfuse não usa a máscara: a 2ª e a 3ª camadas de "
        f"proteção estão desligadas. stdout={saida.stdout!r} stderr={saida.stderr[-300:]!r}"
    )
