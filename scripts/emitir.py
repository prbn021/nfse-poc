"""Emite em produção restrita a DPS de exemplo do emitente indicado e salva a NFS-e (T-007).

Script manual: usa a rede e o certificado real do emitente. Monta a DPS de exemplo de
gerar_dps.py com o número pedido, o código de tributação nacional do serviço do emitente
(obrigatório, E0312), se dado, o municipal (`cTribMun`, E0314; sem ele, a DPS vai sem) e,
se dado, o CNO da obra (grupo de obra, T-020);
valida contra o XSD, assina, confere a assinatura e envia uma vez (src/emissao.py).
Salva em out/ a DPS enviada e a NFS-e devolvida. Só produção restrita (INV-02).
Não mostra senha, chave nem conteúdo do certificado (INV-05).
"""

import argparse
import dataclasses
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gerar_dps import P_TOT_TRIB_SN_FICTICIO, _decimal, dps_exemplo

from src.assinatura import assinar_dps, conferir_assinatura
from src.certificado import carregar_certificado
from src.client import ClienteNfse, ErroConexao
from src.config import RAIZ, Config, carregar_config
from src.dps import localizar_xsd_dps, para_xml, validar_xml
from src.emissao import DpsJaEmitida, EnvioIncerto, emitir
from src.emitente import PASTA, carregar_emitente
from src.erros import RejeicaoApi, RespostaInesperada
from src.nfse import localizar_xsd_nfse
from src.xsd import preparar_copia_local

# Códigos de saída, além de 0 (emitida e conferida) e 1 (erro antes do envio).
ERRO_DE_REDE = 3  # nada foi gerado; a DPS pode ser enviada de novo
REJEITADA = 4
JA_EMITIDA = 5
ENVIO_INCERTO = 6  # não reenviar sem consultar
CONFERENCIA_FALHOU = 7  # a NFS-e foi gerada e salva, mas algo não bate
RESPOSTA_INESPERADA = 8


def _erro(texto: str) -> None:
    print(f"[X] {texto}", file=sys.stderr)


def _salvar_resposta(saida: Path, id_dps: str, erro: RejeicaoApi | RespostaInesperada) -> None:
    """Guarda em out/ a resposta bruta da SEFIN, para diagnóstico (DEC-037). Pode ter dados
    da DPS, por isso fica só em out/, ignorada no git; não tem senha nem chave."""
    if not erro.corpo:
        return
    quando = datetime.now().strftime("%Y%m%d-%H%M%S")
    arquivo = saida / f"{id_dps}-resposta-{erro.status}-{quando}.json"
    arquivo.write_bytes(erro.corpo)
    print(f"Resposta completa da SEFIN: {arquivo}", file=sys.stderr)


def _causa(falha: Exception | None) -> str:
    """Por que a nota veio pela recuperação (DEC-044)."""
    if isinstance(falha, RespostaInesperada):
        detalhe = f"HTTP {falha.status}: {falha.motivo}"
        return f"a resposta do envio veio fora do formato esperado ({detalhe})"
    if isinstance(falha, RejeicaoApi):
        mensagens = "; ".join(str(m) for m in falha.mensagens) or "sem mensagens"
        return f"a SEFIN respondeu com erro (HTTP {falha.status}: {mensagens})"
    return f"a conexão caiu no envio ({falha})"


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
        "--n-dps",
        required=True,
        type=int,
        help="número da DPS; um número novo a cada envio, ou a SEFIN recusa (E0014)",
    )
    parser.add_argument("--serie", type=int, default=1, help="série da DPS (padrão: %(default)s)")
    parser.add_argument(
        "--c-trib-nac",
        required=True,
        help="código de tributação nacional do serviço do emitente, 6 dígitos, administrado "
        "pelo município de incidência (E0312)",
    )
    parser.add_argument(
        "--c-trib-mun",
        help="código de tributação municipal, 3 dígitos: o desdobramento com que o município "
        "parametriza o serviço (veja consultar_parametros.py --desdobramento); padrão: nenhum",
    )
    parser.add_argument(
        "--obra-cno",
        help="número da obra no CNO (ou CEI): põe o grupo de obra, exigido pelos códigos de "
        "obra (E0370) e proibido nos demais (E0372); padrão: nenhum",
    )
    parser.add_argument(
        "--p-tot-trib-sn",
        default=str(P_TOT_TRIB_SN_FICTICIO),
        help="%% aproximado dos tributos do Simples na competência (padrão: %(default)s, fictício)",
    )
    args = parser.parse_args(argv)

    try:
        config = config or carregar_config()
        emitente = carregar_emitente(args.emitente, pasta)
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
        exemplo = dps_exemplo(
            config.tp_amb,
            emitente,
            _decimal(args.p_tot_trib_sn),
            c_trib_nac=args.c_trib_nac,
            obra_cno=args.obra_cno,
        )
        dps = dataclasses.replace(
            exemplo,
            serie=args.serie,
            n_dps=args.n_dps,
            servico=dataclasses.replace(exemplo.servico, c_trib_mun=args.c_trib_mun),
        )
        cliente = ClienteNfse(config, cert, transporte=transporte)
    except ValueError as erro:
        _erro(str(erro))
        return 1

    xsd_local = preparar_copia_local(config.xsd_dir)
    xsd_dps, xsd_nfse = localizar_xsd_dps(xsd_local), localizar_xsd_nfse(xsd_local)
    if xsd_dps is None or xsd_nfse is None:
        _erro(f"XSD da DPS ou da NFS-e não encontrado em {config.xsd_dir}")
        return 1
    try:
        assinada = assinar_dps(para_xml(dps), cert)
        conferir_assinatura(assinada, cert.certificado)
    except ValueError as erro:
        _erro(str(erro))
        return 1
    erros = validar_xml(assinada, xsd_dps)
    if erros:
        _erro(f"DPS inválida contra {xsd_dps.name}: {erros[0]}")
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    enviada = saida / f"{dps.id}-enviada.xml"
    enviada.write_bytes(assinada)
    print(f"SEFIN: {cliente.sefin_url}")
    print(f"DPS assinada e válida, série {dps.serie}, número {dps.n_dps}: {enviada}")

    with cliente:
        try:
            resultado = emitir(cliente, assinada, xsd_nfse)
        except DpsJaEmitida as erro:
            _erro(str(erro))
            return JA_EMITIDA
        except RejeicaoApi as erro:
            _erro(str(erro))
            _salvar_resposta(saida, dps.id, erro)
            return REJEITADA
        except EnvioIncerto as erro:
            _erro(str(erro))
            return ENVIO_INCERTO
        except ErroConexao as erro:
            _erro(f"erro de conexão: {erro}")
            return ERRO_DE_REDE
        except RespostaInesperada as erro:
            _erro(str(erro))
            _salvar_resposta(saida, dps.id, erro)
            return RESPOSTA_INESPERADA

    nfse = resultado.nfse
    arquivo = saida / f"NFSe{nfse.chave}.xml"
    arquivo.write_bytes(nfse.xml)
    if resultado.recuperada:
        print(f"[!] {_causa(resultado.falha)}; a NFS-e foi recuperada pela consulta da DPS")
        if isinstance(resultado.falha, (RejeicaoApi, RespostaInesperada)):
            _salvar_resposta(saida, dps.id, resultado.falha)
    print(f"Chave de acesso: {nfse.chave}")
    print(f"NFS-e: {arquivo}")
    for alerta in nfse.alertas:
        print(f"[!] Alerta: {alerta}")
    if resultado.problemas:
        for problema in resultado.problemas:
            _erro(f"conferência da NFS-e: {problema}")
        return CONFERENCIA_FALHOU
    print("[OK] NFS-e conferida: XSD, Ids, ambiente e assinatura do sistema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
