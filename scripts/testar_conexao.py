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
from src.client import ClienteNfse, ErroConexao
from src.config import RAIZ, Config, carregar_config
from src.dps import gerar_id
from src.emitente import PASTA, carregar_emitente

PAGINA = "docs/index"
# Série e número que nenhuma DPS usa: a consulta deve responder que não existe.
SERIE_FICTICIA, NUMERO_FICTICIO = 49999, 999_999_999_999_999
# A página da SEFIN usa ReDoc, que recebe a especificação em `openApi: '<url>'`
# (observado em 2026-10-09); outras páginas apontam um arquivo .json.
_LINKS = (
    re.compile(rb"""openApi\s*:\s*["']([^"'\s]+)["']"""),
    re.compile(rb"""["']([^"'\s]+\.json)["']"""),
)


def _caminho_da_especificacao(pagina: bytes, base: str) -> str | None:
    """Caminho, relativo à URL base, do link da especificação; '' se estiver fora dela."""
    achado = next(filter(None, (padrao.search(pagina) for padrao in _LINKS)), None)
    if achado is None:
        return None
    url = urljoin(f"{base}/{PAGINA}", achado.group(1).decode("ascii", errors="replace"))
    if urlsplit(url).netloc != urlsplit(base).netloc or not url.startswith(base + "/"):
        return ""
    return url.removeprefix(base + "/")


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
    args = parser.parse_args(argv)
    try:
        config = config or carregar_config()
        emitente = carregar_emitente(args.emitente, pasta)
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
        cliente = ClienteNfse(config, cert, transporte=transporte)
    except ValueError as erro:
        print(f"[X] {erro}", file=sys.stderr)
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    with cliente:
        print(f"SEFIN: {cliente.sefin_url}")
        try:
            pagina = cliente.obter(PAGINA)
            arquivo = saida / "sefin-docs-index.html"
            arquivo.write_bytes(pagina.corpo)
            print(f"{_linha('GET', PAGINA, pagina.status, pagina.tipo, pagina.corpo)} -> {arquivo}")

            caminho = _caminho_da_especificacao(pagina.corpo, cliente.sefin_url)
            if caminho is None:
                print("OpenAPI: link não encontrado na página")
            elif caminho == "":
                print("OpenAPI: link fora da URL base, não seguido")
            else:
                spec = cliente.obter(caminho)
                arquivo = saida / "sefin-openapi.json"
                arquivo.write_bytes(spec.corpo)
                print(f"{_linha('GET', caminho, spec.status, spec.tipo, spec.corpo)} -> {arquivo}")
                if spec.status == 200:
                    print("\n".join(_resumo_openapi(spec.corpo)))

            id_dps = gerar_id(emitente.municipio, emitente.cnpj, SERIE_FICTICIA, NUMERO_FICTICIO)
            # O Id tem o CNPJ do emitente: não vai para a saída.
            print(f"HEAD dps/<Id que não existe>: {cliente.consultar_dps(id_dps).status}")
        except ErroConexao as erro:
            print(f"[X] erro de conexão: {erro}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
