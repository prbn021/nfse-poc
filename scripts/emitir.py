"""Emite em produção restrita a DPS de exemplo do emitente indicado e salva a NFS-e (T-007).

Script manual: usa a rede e o certificado real do emitente. Monta a DPS de exemplo de
gerar_dps.py com o número pedido, o código de tributação nacional do serviço do emitente
(obrigatório, E0312), se dado, o municipal (`cTribMun`, E0314; sem ele, a DPS vai sem) e,
se dado, o CNO da obra (grupo de obra, T-020);
valida contra o XSD, assina, confere a assinatura e envia uma vez (src/emissao.py).
Salva em out/ a DPS enviada e a NFS-e devolvida. Só produção restrita (INV-02).
Não mostra senha, chave nem conteúdo do certificado (INV-05).

Com --substituir (T-031), a DPS leva o grupo subst. Antes de enviar, consulta a nota
substituída: recusa a que não confere, a já cancelada ou substituída (E0046) e a de outro
tomador ou valor (E0061/E0063), e copia dela a data de competência (E0061/E0063). Depois da
emissão, consulta e confere o evento 105102 que a SEFIN registra na nota substituída.
E0061 é a regra do Anexo I e E0063 a do Anexo VI (NT 009) para a mesma trava (T-037).
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
from src.dps import (
    MOTIVOS_SUBSTITUICAO,
    Dps,
    Substituicao,
    localizar_xsd_dps,
    para_xml,
    validar_xml,
)
from src.emissao import DpsJaEmitida, EnvioIncerto, emitir
from src.emitente import PASTA, carregar_emitente
from src.erros import RejeicaoApi, RespostaInesperada
from src.evento import CANCELAMENTO, SUBSTITUICAO, conferir_substituicao, localizar_xsd_evento
from src.nfse import conferir_nfse, localizar_xsd_nfse, resumo_da_dps
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


class _Recusa(Exception):
    """A substituição não pode ser enviada; `codigo` é o código de saída."""

    def __init__(self, codigo: int, mensagem: str):
        self.codigo = codigo
        super().__init__(f"{mensagem}; nada foi enviado")


def _preparar_substituicao(cliente: ClienteNfse, dps: Dps, xsd_nfse: Path) -> Dps:
    """Consulta a nota substituída e devolve a DPS com a competência dela (E0061/E0063)."""
    chave = dps.subst.chave
    try:
        original = cliente.obter_nfse(chave)
        eventos = [
            tipo
            for tipo in (CANCELAMENTO, SUBSTITUICAO)
            if cliente.consultar_evento(chave, tipo, 1) is not None
        ]
    except RejeicaoApi as erro:
        raise _Recusa(REJEITADA, f"consulta da nota substituída: {erro}") from None
    except ErroConexao as erro:
        raise _Recusa(ERRO_DE_REDE, f"consulta da nota substituída: {erro}") from None
    except RespostaInesperada as erro:
        raise _Recusa(RESPOSTA_INESPERADA, f"consulta da nota substituída: {erro}") from None

    problemas = conferir_nfse(original, chave=chave, id_dps=None, xsd=xsd_nfse)
    if problemas:
        raise _Recusa(1, f"a nota substituída não confere: {'; '.join(problemas)}")
    if eventos:
        raise _Recusa(
            1,
            f"a nota substituída já tem evento {', '.join(eventos)} (cancelada ou substituída); "
            "nota cancelada não pode ser substituída (E0046)",
        )
    try:
        resumo = resumo_da_dps(original)
    except ValueError as erro:
        raise _Recusa(1, f"nota substituída: {erro}") from None
    tomador = dps.tomador.cnpj or dps.tomador.cpf
    if resumo.tomador != tomador or resumo.v_serv != dps.valores.v_serv:
        raise _Recusa(
            1,
            "o tomador ou o valor do serviço da DPS diferem dos da nota substituída; para ME/EPP "
            "eles não podem mudar na substituição (E0061 do Anexo I, E0063 do Anexo VI)",
        )
    print(f"Competência copiada da nota substituída: {resumo.d_compet.isoformat()}")
    return dataclasses.replace(dps, d_compet=resumo.d_compet)


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
    parser.add_argument(
        "--substituir", metavar="CHAVE", help="chave de acesso da NFS-e que esta substitui"
    )
    parser.add_argument(
        "--motivo-subst",
        type=int,
        choices=MOTIVOS_SUBSTITUICAO,
        help="motivo da substituição: 1 a 5, ou 99 (Outros, exige --descricao-subst); "
        "obrigatório com --substituir",
    )
    parser.add_argument(
        "--descricao-subst",
        help="descrição do motivo, de 15 a 255 caracteres, sem travessão nem aspas curvas",
    )
    args = parser.parse_args(argv)
    if args.substituir is None and (args.motivo_subst or args.descricao_subst):
        parser.error("--motivo-subst e --descricao-subst exigem --substituir")
    if args.substituir is not None and args.motivo_subst is None:
        parser.error("--substituir exige --motivo-subst")

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
        if args.substituir is not None:
            subst = Substituicao(args.substituir, args.motivo_subst, args.descricao_subst)
            dps = dataclasses.replace(dps, subst=subst)
        cliente = ClienteNfse(config, cert, transporte=transporte)
    except ValueError as erro:
        _erro(str(erro))
        return 1

    xsd_local = preparar_copia_local(config.xsd_dir)
    xsd_dps, xsd_nfse = localizar_xsd_dps(xsd_local), localizar_xsd_nfse(xsd_local)
    xsd_evento = localizar_xsd_evento(xsd_local)
    if xsd_dps is None or xsd_nfse is None or xsd_evento is None:
        _erro(f"XSD da DPS, da NFS-e ou do evento não encontrado em {config.xsd_dir}")
        return 1

    with cliente:
        if dps.subst is not None:
            print(f"Substitui a NFS-e {dps.subst.chave}")
            try:
                dps = _preparar_substituicao(cliente, dps, xsd_nfse)
            except _Recusa as erro:
                _erro(str(erro))
                return erro.codigo
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

        # A SEFIN registra o 105102 na nota substituída ao gerar a nova (T-031).
        evento, falha_evento = None, None
        if dps.subst is not None:
            try:
                evento = cliente.consultar_evento(dps.subst.chave, SUBSTITUICAO, 1)
            except (ErroConexao, RejeicaoApi, RespostaInesperada) as erro:
                falha_evento = erro

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
    codigo = 0
    if resultado.problemas:
        for problema in resultado.problemas:
            _erro(f"conferência da NFS-e: {problema}")
        codigo = CONFERENCIA_FALHOU
    else:
        print("[OK] NFS-e conferida: XSD, Ids, ambiente e assinatura do sistema")

    if dps.subst is not None:
        chave = dps.subst.chave
        consulta = (
            f"consulte depois com consultar_nfse.py --emitente {args.emitente} --chave {chave} "
            f"--evento {SUBSTITUICAO}"
        )
        if falha_evento is not None:
            print(f"[!] Não foi possível consultar o evento 105102 ({falha_evento}); {consulta}")
        elif evento is None:
            print(f"[!] Evento 105102 ainda não registrado na nota substituída; {consulta}")
        else:
            arquivo = saida / f"Evento{chave}-{SUBSTITUICAO}-1.xml"
            arquivo.write_bytes(evento)
            print(f"Evento 105102 da nota substituída: {arquivo}")
            problemas = conferir_substituicao(
                evento, chave_substituida=chave, chave_substituta=nfse.chave, xsd=xsd_evento
            )
            for problema in problemas:
                _erro(f"conferência do evento 105102: {problema}")
            if problemas:
                codigo = CONFERENCIA_FALHOU
            else:
                print(
                    "[OK] Evento 105102 conferido: XSD, chave, tipo, ambiente, assinatura e "
                    "nota substituta"
                )
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
