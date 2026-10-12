"""Consulta em produção restrita uma NFS-e do emitente, pela chave, e os eventos dela (T-028).

Script manual: usa a rede e o certificado real do emitente, e só lê. Recusa, antes de qualquer
pedido, uma chave que não seja de nota do emitente (o CNPJ fica nas posições 10 a 23 da chave).
Confere a NFS-e (XSD, Id, ambiente, assinatura) e a salva em out/; com --evento, faz o mesmo com
o evento pedido. Só produção restrita (INV-02). Não mostra senha, chave privada nem conteúdo do
certificado (INV-05), nem dados do tomador ou valores da nota.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.certificado import carregar_certificado
from src.client import ClienteNfse, ErroConexao
from src.config import RAIZ, Config, carregar_config
from src.dps import NS
from src.emitente import PASTA, carregar_emitente
from src.erros import RejeicaoApi, RespostaInesperada
from src.evento import conferir_evento, localizar_xsd_evento
from src.nfse import conferir_nfse, localizar_xsd_nfse
from src.xsd import preparar_copia_local

# Códigos de saída, os mesmos do emitir.py: 0 consultada e conferida; 1 erro antes da consulta.
ERRO_DE_REDE = 3
REJEITADA = 4
CONFERENCIA_FALHOU = 7  # o documento foi salvo, mas algo não bate
RESPOSTA_INESPERADA = 8

_CHAVE = re.compile(r"[0-9]{50}")
_N = {"n": NS}


def _erro(texto: str) -> None:
    print(f"[X] {texto}", file=sys.stderr)


def _cnpj_da_chave(chave: str) -> str:
    # Anexo I, Id da NFS-e: município (7), ambiente gerador (1), tipo de inscrição (1),
    # inscrição federal (14), número (13), ano e mês (4), código (9), DV (1).
    return chave[9:23]


def _salvar_resposta(saida: Path, chave: str, erro: RejeicaoApi | RespostaInesperada) -> None:
    """Guarda em out/ a resposta bruta da SEFIN, para diagnóstico (DEC-037)."""
    corpo = getattr(erro, "corpo", None)
    if not corpo:
        return
    quando = datetime.now().strftime("%Y%m%d-%H%M%S")
    arquivo = saida / f"NFSe{chave}-resposta-{erro.status}-{quando}.json"
    arquivo.write_bytes(corpo)
    print(f"Resposta completa da SEFIN: {arquivo}", file=sys.stderr)


def _resumo(xml: bytes) -> tuple[str, str]:
    """Número e situação da NFS-e, os únicos campos da nota que o script mostra."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        inf = etree.fromstring(xml, parser).find("n:infNFSe", _N)
    except (etree.XMLSyntaxError, ValueError):
        inf = None
    if inf is None:
        return "?", "?"
    return inf.findtext("n:nNFSe", "?", _N), inf.findtext("n:cStat", "?", _N)


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
    parser.add_argument("--chave", required=True, help="chave de acesso da NFS-e, 50 dígitos")
    parser.add_argument(
        "--evento", help="código do evento a consultar, 6 dígitos (ex.: 101101, cancelamento)"
    )
    parser.add_argument(
        "--seq", type=int, help="número sequencial do evento (padrão: 1); exige --evento"
    )
    args = parser.parse_args(argv)
    if args.seq is not None and args.evento is None:
        parser.error("--seq exige --evento")
    seq = 1 if args.seq is None else args.seq

    try:
        if not _CHAVE.fullmatch(args.chave):
            raise ValueError("chave de acesso fora do formato: 50 dígitos")
        config = config or carregar_config()
        emitente = carregar_emitente(args.emitente, pasta)
        if _cnpj_da_chave(args.chave) != emitente.cnpj:
            raise ValueError(
                "a chave não é de uma nota deste emitente (o CNPJ da chave é outro); "
                "nada foi consultado"
            )
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
        cliente = ClienteNfse(config, cert, transporte=transporte)
    except ValueError as erro:
        _erro(str(erro))
        return 1

    xsd_local = preparar_copia_local(config.xsd_dir)
    xsd_nfse, xsd_evento = localizar_xsd_nfse(xsd_local), localizar_xsd_evento(xsd_local)
    if xsd_nfse is None or xsd_evento is None:
        _erro(f"XSD da NFS-e ou do evento não encontrado em {config.xsd_dir}")
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    print(f"SEFIN: {cliente.sefin_url}")
    problemas = []
    with cliente:
        try:
            nfse = cliente.obter_nfse(args.chave)
            evento = None
            if args.evento is not None:
                evento = cliente.consultar_evento(args.chave, args.evento, seq)
        except ValueError as erro:
            _erro(str(erro))
            return 1
        except RejeicaoApi as erro:
            _erro(str(erro))
            _salvar_resposta(saida, args.chave, erro)
            return REJEITADA
        except ErroConexao as erro:
            _erro(f"erro de conexão: {erro}")
            return ERRO_DE_REDE
        except RespostaInesperada as erro:
            _erro(str(erro))
            _salvar_resposta(saida, args.chave, erro)
            return RESPOSTA_INESPERADA

    arquivo = saida / f"NFSe{args.chave}-consulta.xml"
    arquivo.write_bytes(nfse)
    numero, situacao = _resumo(nfse)
    print(f"Chave de acesso: {args.chave}")
    print(f"Número: {numero}  cStat: {situacao}")
    print(f"NFS-e: {arquivo}")
    problemas_nfse = conferir_nfse(nfse, chave=args.chave, id_dps=None, xsd=xsd_nfse)
    for problema in problemas_nfse:
        _erro(f"conferência da NFS-e: {problema}")
    if not problemas_nfse:
        print("[OK] NFS-e conferida: XSD, Id, ambiente e assinatura do sistema")
    problemas += problemas_nfse

    if args.evento is not None:
        rotulo = f"{args.evento} (sequência {seq})"
        if evento is None:
            print(f"Nenhum evento {rotulo} para esta NFS-e")
        else:
            arquivo = saida / f"Evento{args.chave}-{args.evento}-{seq}.xml"
            arquivo.write_bytes(evento)
            print(f"Evento: {arquivo}")
            problemas_evento = conferir_evento(
                evento, chave=args.chave, tipo=args.evento, xsd=xsd_evento
            )
            for problema in problemas_evento:
                _erro(f"conferência do evento: {problema}")
            if not problemas_evento:
                print(f"[OK] Evento {rotulo} conferido: XSD, chave, tipo, ambiente e assinatura")
            problemas += problemas_evento

    return CONFERENCIA_FALHOU if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
