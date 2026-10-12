"""Consulta no ADN a parametrização de um município para um código de serviço (T-026).

Script manual: usa a rede e o certificado real do emitente, só com consultas (GET) na API de
parâmetros municipais do ADN de produção restrita (INV-02). Mostra o convênio do município e o
histórico de alíquotas do `cTribNac`, com o desdobramento `000` (9 dígitos) e sem ele (6),
porque a especificação não diz qual formato a API espera. Serve para entender o E0312.
As respostas brutas vão para out/. Não mostra senha, chave nem conteúdo do certificado.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.certificado import carregar_certificado
from src.client import ClienteNfse, ConsultaParametros, ErroConexao
from src.config import RAIZ, Config, carregar_config
from src.emitente import PASTA, carregar_emitente
from src.erros import RespostaInesperada

ERRO_DE_REDE = 3
RESPOSTA_INESPERADA = 8
_C_TRIB_NAC = re.compile(r"\d{6}")
_MUNICIPIO = re.compile(r"\d{7}")
SEM_DESDOBRAMENTO = "000"  # desdobramento municipal "nenhum", segundo terceiros (SOURCES)


def _resumo(consulta: ConsultaParametros) -> str:
    mensagem = f" ({consulta.mensagem})" if consulta.mensagem else ""
    return f"HTTP {consulta.status}{mensagem}"


def _pares(item: object) -> str:
    if not isinstance(item, dict):
        return repr(item)
    return ", ".join(f"{chave}={valor}" for chave, valor in item.items())


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
        "--c-trib-nac", required=True, help="código de tributação nacional, 6 dígitos"
    )
    parser.add_argument("--municipio", help="código IBGE do município (padrão: o do emitente)")
    args = parser.parse_args(argv)

    try:
        if not _C_TRIB_NAC.fullmatch(args.c_trib_nac):
            raise ValueError("--c-trib-nac deve ter 6 dígitos")
        config = config or carregar_config()
        emitente = carregar_emitente(args.emitente, pasta)
        municipio = args.municipio or emitente.municipio
        if not _MUNICIPIO.fullmatch(municipio):
            raise ValueError("--municipio deve ter 7 dígitos (código IBGE)")
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
        cliente = ClienteNfse(config, cert, api="adn", transporte=transporte)
    except ValueError as erro:
        print(f"[X] {erro}", file=sys.stderr)
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    codigos = [args.c_trib_nac + SEM_DESDOBRAMENTO, args.c_trib_nac]
    with cliente:
        print(f"ADN: {cliente.base_url}")
        arquivo = saida / f"adn-{municipio}-convenio.json"
        try:
            convenio = cliente.convenio(municipio)
            arquivo.write_bytes(convenio.bruto)
            print(f"Convênio de {municipio}: {_resumo(convenio)} -> {arquivo}")
            parametros = convenio.corpo.get("parametrosconvenio")
            if parametros is not None:
                print(f"  {_pares(parametros)}")

            for codigo in codigos:
                arquivo = saida / f"adn-{municipio}-{codigo}-historicoaliquotas.json"
                historico = cliente.historico_aliquotas(municipio, codigo)
                arquivo.write_bytes(historico.bruto)
                print(f"Histórico de alíquotas de {codigo}: {_resumo(historico)} -> {arquivo}")
                aliquotas = historico.corpo.get("aliquotas")
                if isinstance(aliquotas, dict):
                    for chave, lista in aliquotas.items():
                        for item in lista if isinstance(lista, list) else [lista]:
                            print(f"  {chave}: {_pares(item)}")
        except ErroConexao as erro:
            print(f"[X] erro de conexão: {erro}", file=sys.stderr)
            return ERRO_DE_REDE
        except RespostaInesperada as erro:
            if erro.corpo:
                arquivo.write_bytes(erro.corpo)
            print(f"[X] {erro} (resposta salva em {arquivo})", file=sys.stderr)
            return RESPOSTA_INESPERADA
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
