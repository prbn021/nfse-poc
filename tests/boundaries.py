"""Confere as boundaries de docs/SPEC.md §3 a partir dos imports de src/ e scripts/ (T-016, T-015).

Lê só os `import` e `from ... import` do código, em qualquer nível (inclusive dentro de
função ou de `try`). Import feito por nome em texto (`importlib.import_module`, `__import__`)
não é visto.
"""

import ast
from collections import deque
from pathlib import Path, PurePosixPath

# Bibliotecas que abrem conexão. A lista é fechada: uma biblioteca de rede nova entra aqui
# na task que a instalar.
REDE = frozenset(
    {
        # biblioteca padrão
        "socket",
        "socketserver",
        "ssl",
        "http.client",
        "http.server",
        "urllib.request",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "telnetlib",
        "xmlrpc",
        # terceiros
        "httpx",
        "httpcore",
        "requests",
        "requests_pkcs12",
        "urllib3",
        "aiohttp",
        "websockets",
    }
)
# Módulos que carregam ou usam certificado e chave privada.
CERTIFICADO = frozenset({"src.certificado", "cryptography", "OpenSSL", "signxml", "xmlsec"})

CLIENT = "src.client"
DPS = "src.dps"
SCRIPTS = "scripts"

# B-1: o que src/dps.py não pode alcançar, nem por intermédio de outro módulo de src/.
PROIBIDO_PARA_DPS = REDE | CERTIFICADO | {CLIENT}


def ler_fontes(raiz: Path) -> dict[str, str]:
    """Lê os .py sob src/ e scripts/: caminho relativo à raiz (com barras) -> código."""
    return {
        arquivo.relative_to(raiz).as_posix(): arquivo.read_text(encoding="utf-8")
        for pasta in ("src", SCRIPTS)
        for arquivo in sorted((raiz / pasta).rglob("*.py"))
    }


def _prefixos(nome: str) -> list[str]:
    """`a.b.c` -> `a`, `a.b`, `a.b.c`: importar um módulo importa também os pacotes acima."""
    partes = nome.split(".")
    return [".".join(partes[:i]) for i in range(1, len(partes) + 1)]


def _dependencias(caminho: str, codigo: str) -> tuple[str, set[str]]:
    """Nome do módulo e os nomes que ele importa, com imports relativos já resolvidos.

    `from a import b` conta como `a` e `a.b`, porque `b` pode ser um submódulo.
    """
    partes = PurePosixPath(caminho).with_suffix("").parts
    pacote = partes[:-1]
    nome = ".".join(pacote if partes[-1] == "__init__" else partes)

    importados = set(_prefixos(nome)[:-1])
    for no in ast.walk(ast.parse(codigo, filename=caminho)):
        if isinstance(no, ast.Import):
            alvos = [alias.name for alias in no.names]
        elif isinstance(no, ast.ImportFrom):
            base = list(pacote[: len(pacote) - (no.level - 1)]) if no.level else []
            if no.module:
                base += no.module.split(".")
            alvos = [".".join([*base, alias.name]) for alias in no.names if alias.name != "*"]
            alvos.append(".".join(base))
        else:
            continue
        for alvo in alvos:
            importados.update(_prefixos(alvo))
    return nome, importados


def _b1(deps: dict[str, set[str]]) -> set[str]:
    """Percorre em largura o que src.dps alcança dentro de src/; aponta o caminho mais curto."""
    achadas = set()
    vistos = {DPS}
    fila = deque([[DPS]])
    while fila:
        cadeia = fila.popleft()
        for alvo in sorted(deps.get(cadeia[-1], ())):
            if alvo in vistos:
                continue
            vistos.add(alvo)
            if alvo in PROIBIDO_PARA_DPS:
                achadas.add("B-1: " + " -> ".join([*cadeia, alvo]))
            elif alvo in deps:
                fila.append([*cadeia, alvo])
    return achadas


def violacoes(fontes: dict[str, str]) -> list[str]:
    """Aponta cada import que cruza uma boundary, no formato `B-n: módulo -> ... -> alvo`."""
    deps = dict(_dependencias(caminho, codigo) for caminho, codigo in fontes.items())

    achadas = _b1(deps)
    for nome, importados in deps.items():
        if nome != CLIENT and not nome.startswith(CLIENT + "."):
            achadas.update(f"B-2: {nome} -> {alvo}" for alvo in importados & REDE)
        # B-3 vale para src/; scripts/ pode depender de si mesmo.
        if not nome.startswith(SCRIPTS + ".") and SCRIPTS in importados:
            achadas.add(f"B-3: {nome} -> {SCRIPTS}")
    return sorted(achadas)
