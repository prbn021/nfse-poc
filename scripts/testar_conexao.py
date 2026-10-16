"""Teste de conexão mTLS com a SEFIN Nacional em produção restrita, sem emitir nada (T-015).

Script manual: abre o certificado do emitente indicado e faz três consultas pelo src/client.py:
a página de documentação da API, a especificação OpenAPI que ela aponta (se houver) e um
`HEAD /dps/{id}` com um Id que não existe. As respostas da documentação vão para out/.
Não mostra senha, chave nem dado do certificado (INV-05).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.certificado import carregar_certificado
from src.client import ClienteNfse
from src.config import RAIZ, Config, carregar_config
from src.dominio.dps import gerar_id
from src.dominio.erros import ErroConexao
from src.emitente import PASTA, carregar_emitente

PAGINA = "docs/index"
# Com --api: qual API, a página de documentação dela e o prefixo dos arquivos em out/.
# A parametrização municipal saiu da SEFIN e foi para o ADN (docs/SOURCES.md, T-026).
APIS = {
    "sefin": ("sefin", "SEFIN", PAGINA, "sefin"),
    "parametrizacao": ("adn", "ADN", "parametrizacao/docs/index.html", "adn-parametrizacao"),
    # O DANFSe também saiu da SEFIN: GET /DANFSe responde 501 e aponta para o ADN (T-032).
    "danfse": ("adn", "ADN", "danfse/docs/index.html", "adn-danfse"),
}
# Série e número que nenhuma DPS usa: a consulta deve responder que não existe.
SERIE_FICTICIA, NUMERO_FICTICIO = 49999, 999_999_999_999_999
# A página da SEFIN usa ReDoc, que recebe a especificação em `openApi: '<url>'`
# (observado em 2026-10-09); outras páginas apontam um arquivo .json.
_LINKS = (
    re.compile(rb"""openApi\s*:\s*["']([^"'\s]+)["']"""),
    re.compile(rb"""["']([^"'\s]+\.json)["']"""),
)


# A página do ADN (observada em 2026-10-12) não traz o link: carrega um index.js local, que
# chama o ReDoc com a especificação. A biblioteca do ReDoc em si não é baixada.
_SCRIPTS = re.compile(rb"""<script[^>]*\ssrc\s*=\s*["']([^"']+)["']""")
_BIBLIOTECA = "redoc.standalone"


def _relativo(link: str, base: str, onde: str) -> str:
    """`link`, visto a partir de `onde`, como caminho relativo à URL base; '' se sair dela."""
    url = urljoin(f"{base}/{onde}", link)
    if urlsplit(url).netloc != urlsplit(base).netloc or not url.startswith(base + "/"):
        return ""
    return url.removeprefix(base + "/")


def _caminho_da_especificacao(pagina: bytes, base: str, onde: str = PAGINA) -> str | None:
    """Caminho, relativo à URL base, do link da especificação; '' se estiver fora dela."""
    achado = next(filter(None, (padrao.search(pagina) for padrao in _LINKS)), None)
    if achado is None:
        return None
    return _relativo(achado.group(1).decode("ascii", errors="replace"), base, onde)


def _scripts_locais(pagina: bytes, base: str, onde: str) -> list[str]:
    """Scripts da página dentro da URL base, menos a biblioteca do ReDoc."""
    caminhos = []
    for achado in _SCRIPTS.finditer(pagina):
        src = achado.group(1).decode("ascii", errors="replace")
        caminho = _relativo(src, base, onde)
        if caminho and _BIBLIOTECA not in caminho and caminho not in caminhos:
            caminhos.append(caminho)
    return caminhos


def _resumo_openapi(corpo: bytes) -> list[str]:
    try:
        especificacao = json.loads(corpo)
    except ValueError:
        return ["  (não é JSON)"]
    if not isinstance(especificacao, dict):
        return ["  (JSON sem objeto na raiz)"]
    linhas = []
    servers = [s.get("url", "") for s in especificacao.get("servers", []) if isinstance(s, dict)]
    if servers:
        linhas.append(f"servers: {', '.join(servers)}")
    if "host" in especificacao or "basePath" in especificacao:  # Swagger 2.0
        linhas.append(
            f"host: {especificacao.get('host', '')}, basePath: {especificacao.get('basePath', '')}"
        )
    rotas = sorted(especificacao.get("paths", {}))
    linhas.append(f"rotas: {', '.join(rotas) if rotas else '(nenhuma)'}")
    return linhas


def _linha(metodo: str, caminho: str, status: int, tipo: str, corpo: bytes) -> str:
    return f"{metodo} {caminho}: {status} ({tipo or 'sem Content-Type'}, {len(corpo)} bytes)"


def main(
    argv: list[str] | None = None,
    pasta: Path = PASTA,
    *,
    config: Config | None = None,
    transporte=None,
    saida: Path = RAIZ / "out",
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--emitente", required=True, help="nome do arquivo em emitentes/, sem .toml"
    )
    parser.add_argument(
        "--api",
        choices=sorted(APIS),
        default="sefin",
        help="sefin (padrão): documentação, especificação e HEAD de uma DPS; "
        "parametrizacao: documentação e especificação da parametrização municipal no ADN; "
        "danfse: documentação e especificação da API de DANFSe no ADN",
    )
    args = parser.parse_args(argv)
    api, rotulo, onde, prefixo = APIS[args.api]
    try:
        config = config or carregar_config()
        emitente = carregar_emitente(args.emitente, pasta)
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
        cliente = ClienteNfse(config, cert, api=api, transporte=transporte)
    except ValueError as erro:
        print(f"[X] {erro}", file=sys.stderr)
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    with cliente:
        print(f"{rotulo}: {cliente.base_url}")
        try:
            pagina = cliente.obter(onde)
            arquivo = saida / f"{prefixo}-docs-index.html"
            arquivo.write_bytes(pagina.corpo)
            print(f"{_linha('GET', onde, pagina.status, pagina.tipo, pagina.corpo)} -> {arquivo}")

            caminho = _caminho_da_especificacao(pagina.corpo, cliente.base_url, onde)
            scripts = []
            if caminho is None:
                scripts = _scripts_locais(pagina.corpo, cliente.base_url, onde)
            for script in scripts:
                corpo_js = cliente.obter(script)
                arquivo = saida / f"{prefixo}-{script.rsplit('/', 1)[-1]}"
                arquivo.write_bytes(corpo_js.corpo)
                linha = _linha("GET", script, corpo_js.status, corpo_js.tipo, corpo_js.corpo)
                print(f"{linha} -> {arquivo}")
                caminho = _caminho_da_especificacao(corpo_js.corpo, cliente.base_url, script)
                if caminho is not None:
                    break
            if caminho is None:
                nomes = ", ".join(s.rsplit("/", 1)[-1] for s in scripts)
                print(
                    f"OpenAPI: link não encontrado na página{f' nem em {nomes}' if nomes else ''}"
                )
            elif caminho == "":
                print("OpenAPI: link fora da URL base, não seguido")
            else:
                spec = cliente.obter(caminho)
                arquivo = saida / f"{prefixo}-openapi.json"
                arquivo.write_bytes(spec.corpo)
                print(f"{_linha('GET', caminho, spec.status, spec.tipo, spec.corpo)} -> {arquivo}")
                if spec.status == 200:
                    print("\n".join(_resumo_openapi(spec.corpo)))

            if api == "sefin":
                id_dps = gerar_id(
                    emitente.municipio, emitente.cnpj, SERIE_FICTICIA, NUMERO_FICTICIO
                )
                # O Id tem o CNPJ do emitente: não vai para a saída.
                print(f"HEAD dps/<Id que não existe>: {cliente.consultar_dps(id_dps).status}")
        except ErroConexao as erro:
            print(f"[X] erro de conexão: {erro}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
