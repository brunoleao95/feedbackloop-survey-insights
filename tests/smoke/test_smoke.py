"""Smoke tests do FeedbackLoop.

Estes testes NAO substituem a suite unitaria de tests/test_pipeline.py. Aquela
valida a logica com o LLM mockado e roda offline. Estes aqui respondem outra
pergunta: o que esta publicado esta de fato funcionando?

A distincao nasceu de um incidente real desta etapa. O deploy foi marcado como
`live`, a pagina respondia HTTP 200 e os 7 testes unitarios passavam, enquanto a
funcionalidade central estava quebrada por uma dependencia transitiva. Todos os
sinais estavam verdes e o sistema nao funcionava.

Por isso os tres testes cobrem camadas diferentes, do mais raso ao mais fundo:

  1. test_healthcheck_responde     -> o processo esta vivo e servindo
  2. test_app_carregou             -> o Streamlit inicializou o app, nao so o servidor
  3. test_cadeia_do_llm_construivel -> a cadeia de dependencias do LLM esta intacta

O terceiro e o que teria pego o incidente. Ele nao chama a API do provedor e nao
consome credito: usa uma chave falsa e verifica apenas que o cliente se constroi.
Se `httpx` voltar a divergir do `openai`, ele quebra aqui, no pipeline, e nao na
frente do usuario.

Uso:
    SMOKE_URL=https://feedbackloop-dev.onrender.com pytest tests/smoke -v
"""

import os

import httpx
import pytest

URL = os.environ.get("SMOKE_URL", "").rstrip("/")

# Tolerancia a cold start: o plano gratuito do Render hiberna apos 15 minutos
# sem trafego e leva cerca de um minuto para responder de novo. Sem isso, o
# pipeline falharia por hibernacao e nao por defeito. Ver ADR-002.
TIMEOUT = 90.0
TENTATIVAS = 3


requer_url = pytest.mark.skipif(
    not URL, reason="SMOKE_URL nao definida; smoke tests exigem um alvo publicado"
)


def _get(caminho: str = "") -> httpx.Response:
    """GET com tolerancia a cold start, devolvendo a ultima resposta."""
    erro = None
    for tentativa in range(TENTATIVAS):
        try:
            return httpx.get(f"{URL}{caminho}", timeout=TIMEOUT, follow_redirects=True)
        except httpx.TransportError as exc:  # rede, DNS, handshake
            erro = exc
    raise AssertionError(
        f"{URL}{caminho} nao respondeu em {TENTATIVAS} tentativas de {TIMEOUT}s: {erro}"
    )


@requer_url
def test_healthcheck_responde():
    """O endpoint de saude do Streamlit devolve ok.

    E a verificacao mais barata de todas e a unica que responde "o processo
    subiu". Nao diz nada sobre a aplicacao em si.
    """
    resposta = _get("/_stcore/health")
    assert resposta.status_code == 200, f"healthcheck devolveu {resposta.status_code}"
    assert resposta.text.strip().lower() == "ok", f"corpo inesperado: {resposta.text!r}"


@requer_url
def test_app_carregou():
    """A raiz devolve a pagina do app, e nao uma tela de erro da plataforma.

    Um 200 sozinho nao basta: a pagina de erro do Render tambem devolve 200 em
    alguns casos. Por isso o teste procura marcadores do Streamlit no HTML.
    """
    resposta = _get()
    assert resposta.status_code == 200, f"raiz devolveu {resposta.status_code}"
    corpo = resposta.text.lower()
    assert "streamlit" in corpo, "o HTML nao parece ser de uma aplicacao Streamlit"
    assert len(resposta.content) > 300, "resposta curta demais para ser a pagina do app"


def test_cadeia_do_llm_construivel():
    """O cliente do LLM se constroi com as dependencias instaladas.

    Regressao do incidente desta etapa: `openai 1.50.0` passa o argumento
    `proxies` para o `httpx`, que o removeu na versao 0.28. O resultado era
    TypeError em tempo de execucao, invisivel para o build e para o healthcheck.

    Nao roda contra a URL publicada de proposito: valida o ambiente que sera
    empacotado, no pipeline, antes de publicar. Nao consome credito do provedor,
    porque a chave falsa so e usada na construcao do cliente.
    """
    from feedbackloop.llm import ClienteLLM

    try:
        cliente = ClienteLLM()
    except KeyError:
        # Sem OPENAI_API_KEY no ambiente: injeta uma falsa so para a construcao.
        os.environ["OPENAI_API_KEY"] = "sk-chave-falsa-apenas-para-construcao"
        cliente = ClienteLLM()

    assert hasattr(cliente, "completar"), "o cliente nao expoe o metodo completar"
    assert cliente.modelo, "o modelo do cliente esta vazio"
