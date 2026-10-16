# Cache das respostas do LLM, com expiração e exclusão automáticas.
#
# Uma análise faz uma chamada ao provedor por resposta, mais uma do resumo.
# Reanalisar a mesma planilha pagava tudo de novo e esperava tudo de novo. Este
# módulo guarda o resultado de cada classificação e do resumo, e devolve o que
# já foi calculado sem chamar o provedor. Ver docs/otimizacao/cache.md.
#
# Três decisões de desenho, e as três importam fora da performance:
#
#   1. Não guarda texto. A chave é um hash SHA-256 do texto JÁ SANITIZADO, e o
#      valor é só o resultado: tema e sentimento, ou o texto do resumo, que é
#      gerado a partir de agregados. Não há resposta de pesquisa nem nome de
#      pessoa no arquivo do cache. Ver docs/lgpd/retencao-e-exclusao.md.
#   2. O prompt e o modelo entram na chave. Trocar qualquer um dos dois
#      invalida o cache sozinho, sem ninguém precisar lembrar de limpá-lo.
#   3. Expira em 24 horas, o teto que a aula 9 sugere para classificação. A
#      exclusão é um DELETE em SQL, executado na abertura e a cada gravação, e a
#      leitura ignora o que já venceu mesmo antes de ser apagado.
#
# Uma falha no cache nunca derruba a análise: o pipeline segue chamando o
# provedor, como antes de o cache existir.

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
from functools import lru_cache

TTL_PADRAO_SEGUNDOS = 24 * 60 * 60

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS cache (
    chave     TEXT PRIMARY KEY,
    valor     TEXT NOT NULL,
    criado_em REAL NOT NULL
)
"""


class Cache:
    """Cache chave-valor em SQLite com expiração por tempo.

    O `relogio` é injetável para que os testes possam avançar o tempo sem
    esperar 24 horas.
    """

    def __init__(self, caminho: str, ttl_segundos: int = TTL_PADRAO_SEGUNDOS, relogio=time.time):
        self.caminho = caminho
        self.ttl = ttl_segundos
        self._relogio = relogio
        # O Streamlit executa cada sessão numa thread. A trava serializa o
        # acesso, e check_same_thread=False permite compartilhar a conexão.
        self._trava = threading.Lock()
        self._con = sqlite3.connect(caminho, check_same_thread=False)
        with self._trava:
            self._con.execute(_ESQUEMA)
            self._con.commit()
        self.expurgar()

    @staticmethod
    def chave(*partes) -> str:
        """Hash estável das partes. Nenhuma parte fica legível no cache."""
        bruto = json.dumps(partes, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()

    def obter(self, chave: str):
        """Devolve o valor guardado, ou None se não existe ou já venceu."""
        limite = self._relogio() - self.ttl
        with self._trava:
            linha = self._con.execute(
                "SELECT valor FROM cache WHERE chave = ? AND criado_em >= ?",
                (chave, limite),
            ).fetchone()
        return json.loads(linha[0]) if linha else None

    def guardar(self, chave: str, valor) -> None:
        with self._trava:
            self._con.execute(
                "INSERT OR REPLACE INTO cache (chave, valor, criado_em) VALUES (?, ?, ?)",
                (chave, json.dumps(valor, ensure_ascii=False), self._relogio()),
            )
            self._con.commit()
        self.expurgar()

    def expurgar(self) -> int:
        """Apaga o que passou do prazo. Devolve quantas entradas foram apagadas.

        É o mecanismo de exclusão da política de retenção.
        """
        limite = self._relogio() - self.ttl
        with self._trava:
            cursor = self._con.execute("DELETE FROM cache WHERE criado_em < ?", (limite,))
            self._con.commit()
        return cursor.rowcount

    def tamanho(self) -> int:
        with self._trava:
            return self._con.execute("SELECT COUNT(*) FROM cache").fetchone()[0]


@lru_cache(maxsize=1)
def cache_padrao() -> Cache:
    """Cache do processo, num arquivo do diretório temporário.

    No Render o disco é efêmero: cada deploy começa com o cache vazio. Isso é
    aceitável, e é registrado como trade-off em docs/otimizacao/cache.md.
    """
    caminho = os.getenv(
        "CACHE_PATH", os.path.join(tempfile.gettempdir(), "feedbackloop-cache.sqlite3")
    )
    ttl = int(os.getenv("CACHE_TTL_SEGUNDOS", TTL_PADRAO_SEGUNDOS))
    return Cache(caminho, ttl)
