# Interface fina com o LLM.
# (Rafael)
#
# A graça aqui é que TODO o resto do código só conhece o método `.completar()`.
# Isso deixa o pipeline testável sem chamar a API de verdade: nos testes a gente
# passa um cliente fake (um dublê) que devolve respostas fixas. Ver tests/.
#
# Hoje só tem implementação pra OpenAI. Pra trocar pro Claude
# (um modelo Haiku da Anthropic) seria mais ou menos:
#
#     from anthropic import Anthropic
#     resp = Anthropic().messages.create(model="<modelo-haiku-da-anthropic>", ...)
#
# ...mas não cheguei a fazer. Fica de TODO pra quem assumir.

import os

from feedbackloop.observabilidade import cliente as observabilidade
from feedbackloop.observabilidade import observe

# TODO: modelo hardcoded. Devia vir do .env junto com temperatura. (Rafael)
MODELO_PADRAO = "gpt-5.4-mini"


class ClienteLLM:
    """Wrapper minimalista em cima do SDK da OpenAI.

    O construtor já lê a chave do ambiente sem nenhum fallback bonitinho:
    se não tiver OPENAI_API_KEY setada, quebra na hora. (planted: segredo cru)
    """

    def __init__(self, modelo: str = MODELO_PADRAO):
        # import tardio: assim os testes conseguem importar o módulo sem ter
        # o pacote openai instalado nem chave configurada.
        from openai import OpenAI

        self.modelo = modelo
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Registrado como "generation" no Langfuse: modelo, prompt, resposta,
    # tokens e latência de cada chamada. A captura automática de entrada fica
    # desligada porque ela registraria o `self`; a entrada é informada abaixo,
    # explicitamente, e já chega aqui sanitizada por `analisar`.
    @observe(name="chamada-llm", as_type="generation", capture_input=False)
    def completar(self, system: str, user: str, temperatura: float = 0.2) -> str:
        """Manda um par (system, user) e devolve o texto da resposta."""
        mensagens = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        observabilidade().update_current_generation(
            input=mensagens,
            model=self.modelo,
            model_parameters={"temperature": temperatura},
        )

        completion = self._client.chat.completions.create(
            model=self.modelo,
            messages=mensagens,
            temperature=temperatura,
        )

        uso = completion.usage
        if uso is not None:
            observabilidade().update_current_generation(
                usage_details={
                    "input": uso.prompt_tokens,
                    "output": uso.completion_tokens,
                },
            )
        return completion.choices[0].message.content or ""
