"""Confere as boundaries de docs/SPEC.md §3 pelos imports de src/ e scripts/ (T-016, T-015, T-042,
T-043).

Lê só os `import` e `from ... import` do código, em qualquer nível (inclusive dentro de
função ou de `try`). Import feito por nome em texto (`importlib.import_module`, `__import__`)
não é visto.
"""

import ast
import sys
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
CLIENT = "src.client"
SCRIPTS = "scripts"

# B-4 (T-043, DEC-078): src/dominio/ só importa biblioteca padrão, lxml e o próprio domínio.
# Amplia a B-1, que valia só para src/dps.py, hoje src/dominio/dps/.
DOMINIO = "src.dominio"
LXML = "lxml"
# B-5 (T-042, DEC-077): src/aplicacao/ só importa biblioteca padrão, domínio e a si mesma.
APLICACAO = "src.aplicacao"


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


def _dentro(nome: str, pacote: str) -> bool:
    return nome == pacote or nome.startswith(pacote + ".")


def _biblioteca_padrao(nome: str) -> bool:
    return nome.split(".")[0] in sys.stdlib_module_names


def _mais_curtos(proibidos: dict[str, list[str]]) -> list[list[str]]:
    """Só o nome mais curto proibido: `src.client.X` aparece como `src.client`."""
    return [
        cadeia
        for alvo, cadeia in proibidos.items()
        if not any(acima in proibidos for acima in _prefixos(alvo)[:-1])
    ]


def _permitido_no_dominio(alvo: str) -> bool:
    return (
        alvo == "src" or _biblioteca_padrao(alvo) or _dentro(alvo, LXML) or _dentro(alvo, DOMINIO)
    )


def _b4(nome: str, deps: dict[str, set[str]]) -> set[str]:
    """Percorre em largura o que um módulo do domínio alcança; aponta o caminho mais curto.

    Os outros módulos do domínio têm a própria conferência, então o percurso só segue por
    `src` (o `src/__init__.py`, executado antes de qualquer import de `src.`).
    """
    proibidos: dict[str, list[str]] = {}
    vistos = {nome}
    fila = deque([[nome]])
    while fila:
        cadeia = fila.popleft()
        for alvo in sorted(deps.get(cadeia[-1], ())):
            if alvo in vistos:
                continue
            vistos.add(alvo)
            if not _permitido_no_dominio(alvo):
                proibidos[alvo] = [*cadeia, alvo]
            elif alvo in deps and not _dentro(alvo, DOMINIO):
                fila.append([*cadeia, alvo])
    return {"B-4: " + " -> ".join(cadeia) for cadeia in _mais_curtos(proibidos)}


def _permitido_na_aplicacao(alvo: str) -> bool:
    if alvo == "src" or _biblioteca_padrao(alvo):
        return True
    return _dentro(alvo, APLICACAO) or _dentro(alvo, DOMINIO)


def _b5(nome: str, importados: set[str]) -> set[str]:
    proibidos = {alvo: [nome, alvo] for alvo in importados if not _permitido_na_aplicacao(alvo)}
    return {"B-5: " + " -> ".join(cadeia) for cadeia in _mais_curtos(proibidos)}


def dependencias(fontes: dict[str, str]) -> dict[str, set[str]]:
    """Nome de cada módulo -> os nomes que ele importa (diretamente)."""
    return dict(_dependencias(caminho, codigo) for caminho, codigo in fontes.items())


def violacoes(fontes: dict[str, str]) -> list[str]:
    """Aponta cada import que cruza uma boundary, no formato `B-n: módulo -> ... -> alvo`."""
    deps = dependencias(fontes)

    achadas = set()
    for nome, importados in deps.items():
        if nome != CLIENT and not nome.startswith(CLIENT + "."):
            achadas.update(f"B-2: {nome} -> {alvo}" for alvo in importados & REDE)
        # B-3 vale para src/; scripts/ pode depender de si mesmo.
        if not nome.startswith(SCRIPTS + ".") and SCRIPTS in importados:
            achadas.add(f"B-3: {nome} -> {SCRIPTS}")
        if _dentro(nome, DOMINIO):
            achadas.update(_b4(nome, deps))
        if _dentro(nome, APLICACAO):
            achadas.update(_b5(nome, importados))
    return sorted(achadas)
