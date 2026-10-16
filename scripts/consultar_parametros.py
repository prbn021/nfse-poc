"""Consulta no ADN a parametrização de um município para um código de serviço (T-026).

Script manual: usa a rede e o certificado real do emitente, só com consultas (GET) na API de
parâmetros municipais do ADN de produção restrita (INV-02). Mostra o convênio do município e o
histórico de alíquotas do `cTribNac` com o desdobramento `000`, em 9 dígitos e no formato
pontuado `NN.NN.NN.NNN`, porque a especificação não diz qual formato a API espera.
Serve para entender o E0312.
As respostas brutas vão para out/. Não mostra senha, chave nem conteúdo do certificado.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.certificado import carregar_certificado
from src.client import ClienteNfse, ConsultaParametros
from src.config import RAIZ, Config, carregar_config
from src.emitente import PASTA, carregar_emitente
from src.erros import ErroConexao, RespostaInesperada
from src.lista_servicos import localizar_anexo_b, servicos_nacionais

GOV_DOCS = RAIZ / "docs" / "referencia" / "gov-docs"

ERRO_DE_REDE = 3
RESPOSTA_INESPERADA = 8
_C_TRIB_NAC = re.compile(r"\d{6}")
_MUNICIPIO = re.compile(r"\d{7}")
_DESDOBRAMENTO = re.compile(r"\d{3}")
SEM_DESDOBRAMENTO = "000"  # desdobramento municipal "nenhum", segundo terceiros (SOURCES)


def _resumo(consulta: ConsultaParametros) -> str:
    mensagem = f" ({consulta.mensagem})" if consulta.mensagem else ""
    return f"HTTP {consulta.status}{mensagem}"


def _pares(item: object) -> str:
    if not isinstance(item, dict):
        return repr(item)
    return ", ".join(f"{chave}={valor}" for chave, valor in item.items())


def _pontuado(c_trib_nac: str, desdobramento: str = SEM_DESDOBRAMENTO) -> str:
    return f"{c_trib_nac[:2]}.{c_trib_nac[2:4]}.{c_trib_nac[4:6]}.{desdobramento}"


def _varrer(cliente: ClienteNfse, municipio: str, servicos, saida: Path, desdobramento: str) -> int:
    """Histórico de alíquotas de cada código da lista nacional, no formato pontuado (DEC-042).

    Mostra os códigos com alíquota; grava em out/ um resumo com o status de cada código.
    """
    print(f"ADN: {cliente.base_url}")
    resumo = []
    try:
        convenio = cliente.convenio(municipio)
        print(f"Convênio de {municipio}: {_resumo(convenio)}")
        for codigo, descricao in servicos:
            try:
                historico = cliente.historico_aliquotas(municipio, _pontuado(codigo, desdobramento))
            except RespostaInesperada as erro:
                resumo.append({"codigo": codigo, "status": erro.status, "mensagem": erro.motivo})
                continue
            aliquotas = historico.corpo.get("aliquotas")
            resumo.append(
                {
                    "codigo": codigo,
                    "descricao": descricao,
                    "status": historico.status,
                    "mensagem": historico.mensagem,
                    "aliquotas": aliquotas,
                }
            )
    except ErroConexao as erro:
        print(f"[X] erro de conexão: {erro}", file=sys.stderr)
        return ERRO_DE_REDE

    arquivo = saida / f"adn-{municipio}-varredura.json"
    arquivo.write_text(json.dumps(resumo, ensure_ascii=False, indent=1), encoding="utf-8")
    com = [item for item in resumo if item["status"] == 200 and item.get("aliquotas")]
    sem = [item for item in resumo if item["status"] == 404]
    outros = [item for item in resumo if item not in com and item not in sem]
    print(
        f"Varredura de {len(resumo)} códigos em {municipio}: {len(com)} com alíquota, "
        f"{len(sem)} sem (404), {len(outros)} com outro status -> {arquivo}"
    )
    if not com:
        print("  nenhum código com alíquota no município")
    for item in com:
        for lista in item["aliquotas"].values():
            for aliquota in lista if isinstance(lista, list) else [lista]:
                print(f"  {item['codigo']} {item.get('descricao', '')}: {_pares(aliquota)}")
    for item in outros:
        mensagem = f" ({item['mensagem']})" if item.get("mensagem") else ""
        print(f"  {item['codigo']}: HTTP {item['status']}{mensagem}")
    return 0


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
    alvo = parser.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--c-trib-nac", help="código de tributação nacional, 6 dígitos")
    alvo.add_argument(
        "--varrer",
        action="store_true",
        help="consulta o histórico de alíquotas de todos os códigos da lista nacional "
        "(Anexo B) e mostra os que o município tem; só GET, um por código",
    )
    parser.add_argument("--municipio", help="código IBGE do município (padrão: o do emitente)")
    parser.add_argument(
        "--desdobramento",
        default=SEM_DESDOBRAMENTO,
        help="desdobramento municipal do código, 3 dígitos; é o cTribMun da DPS "
        "(padrão: %(default)s, nenhum)",
    )
    args = parser.parse_args(argv)

    try:
        if args.c_trib_nac is not None and not _C_TRIB_NAC.fullmatch(args.c_trib_nac):
            raise ValueError("--c-trib-nac deve ter 6 dígitos")
        servicos = []
        if args.varrer:
            anexo_b = localizar_anexo_b(GOV_DOCS)
            if anexo_b is None:
                raise ValueError(f"Anexo B não encontrado em {GOV_DOCS}")
            servicos = servicos_nacionais(anexo_b)
        config = config or carregar_config()
        emitente = carregar_emitente(args.emitente, pasta)
        municipio = args.municipio or emitente.municipio
        if not _MUNICIPIO.fullmatch(municipio):
            raise ValueError("--municipio deve ter 7 dígitos (código IBGE)")
        if not _DESDOBRAMENTO.fullmatch(args.desdobramento):
            raise ValueError("--desdobramento deve ter 3 dígitos")
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
        cliente = ClienteNfse(config, cert, api="adn", transporte=transporte)
    except ValueError as erro:
        print(f"[X] {erro}", file=sys.stderr)
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    if args.varrer:
        with cliente:
            return _varrer(cliente, municipio, servicos, saida, args.desdobramento)
    # A API real recusou 6 dígitos e 9 dígitos com zero à esquerda (DEC-041): tenta também o
    # formato pontuado do guia do painel municipal.
    c = args.c_trib_nac
    d = args.desdobramento
    codigos = [c + d, _pontuado(c, d)]
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
