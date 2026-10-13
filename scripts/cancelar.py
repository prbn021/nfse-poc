"""Cancela em produção restrita uma NFS-e do emitente indicado, pelo evento 101101 (T-030).

Script manual: usa o certificado real do emitente e, com --confirmar, a rede. Recusa, antes de
qualquer outra coisa, uma chave que não seja de nota do emitente (o CNPJ fica nas posições 10 a
23 da chave). Monta o pedido de cancelamento, valida contra o XSD, assina, confere a assinatura e
o salva em out/. Sem --confirmar, para aí: nada é enviado. Com --confirmar, envia uma vez
(src/cancelamento.py), confere o evento devolvido e o salva em out/. O cancelamento não volta
atrás. Só produção restrita (INV-02). Não mostra senha, chave privada nem conteúdo do certificado
(INV-05).
"""

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.assinatura import assinar_pedido_evento, conferir_assinatura
from src.cancelamento import CancelamentoIncerto, NotaJaCancelada, cancelar
from src.certificado import carregar_certificado
from src.client import ClienteNfse, ErroConexao
from src.config import RAIZ, Config, carregar_config
from src.dps import NS, validar_xml
from src.emitente import PASTA, carregar_emitente
from src.erros import RejeicaoApi, RespostaInesperada
from src.evento import (
    CANCELAMENTO,
    PedidoCancelamento,
    localizar_xsd_evento,
    localizar_xsd_pedido_evento,
    para_xml_pedido,
)
from src.xsd import preparar_copia_local

# Códigos de saída, os mesmos do emitir.py: 0 cancelada e conferida (ou, sem --confirmar,
# pedido assinado e salvo); 1 erro antes do envio.
ERRO_DE_REDE = 3  # nada foi registrado; o pedido pode ser enviado de novo
REJEITADA = 4
JA_CANCELADA = 5
CANCELAMENTO_INCERTO = 6  # não reenviar sem consultar
CONFERENCIA_FALHOU = 7  # o evento foi registrado e salvo, mas algo não bate
RESPOSTA_INESPERADA = 8

BRT = timezone(timedelta(hours=-3))  # como o dhEmi de gerar_dps.py
_CHAVE = re.compile(r"[0-9]{50}")
_N = {"n": NS}

# O que fazer diante das recusas que só o servidor confere (Anexo II, aba
# RN EVENTO_PED.REG.EVENTO; DEC-052).
DICAS = {
    "E1831": "a NFS-e não existe no ADN: confira a chave e se a nota é da produção restrita",
    "E1843": "dhEvento posterior ao recebimento: o relógio deste computador pode estar adiantado",
    "E0822": "o prazo de cancelamento definido pelo município expirou",
    "E0823": "o valor da nota passa do limite de cancelamento definido pelo município",
    "E0824": "o município não permite cancelar nota sem tomador identificado",
    "E0827": "a nota tem evento de tributos recolhidos, e o município não permite cancelar",
    "E0831": "o pedido deve ir ao sistema que gerou a nota (outro ambiente ou o do município)",
    "E0840": (
        "outro evento já vinculado à nota impede o cancelamento (por exemplo, cancelamento ou "
        "substituição); veja os eventos com consultar_nfse.py --evento"
    ),
}


def _erro(texto: str) -> None:
    print(f"[X] {texto}", file=sys.stderr)


def _cnpj_da_chave(chave: str) -> str:
    # Anexo I, Id da NFS-e: município (7), ambiente gerador (1), tipo de inscrição (1),
    # inscrição federal (14), número (13), ano e mês (4), código (9), DV (1).
    return chave[9:23]


def _salvar_resposta(saida: Path, id_pedido: str, erro: RejeicaoApi | RespostaInesperada) -> None:
    """Guarda em out/ a resposta bruta da SEFIN, para diagnóstico (DEC-037)."""
    if not erro.corpo:
        return
    quando = datetime.now().strftime("%Y%m%d-%H%M%S")
    arquivo = saida / f"{id_pedido}-resposta-{erro.status}-{quando}.json"
    arquivo.write_bytes(erro.corpo)
    print(f"Resposta completa da SEFIN: {arquivo}", file=sys.stderr)


def _salvar_evento(saida: Path, chave: str, evento: bytes) -> Path:
    arquivo = saida / f"Evento{chave}-{CANCELAMENTO}-1.xml"
    arquivo.write_bytes(evento)
    return arquivo


def _resumo(evento: bytes) -> tuple[str, str]:
    """Número sequencial e data do processamento, os únicos campos do evento que o script
    mostra."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        inf = etree.fromstring(evento, parser).find("n:infEvento", _N)
    except (etree.XMLSyntaxError, ValueError):
        inf = None
    if inf is None:
        return "?", "?"
    return inf.findtext("n:nSeqEvento", "?", _N), inf.findtext("n:dhProc", "?", _N)


def _causa(falha: Exception | None) -> str:
    """Por que o evento veio pela recuperação."""
    if isinstance(falha, RespostaInesperada):
        detalhe = f"HTTP {falha.status}: {falha.motivo}"
        return f"a resposta do envio veio fora do formato esperado ({detalhe})"
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
    parser.add_argument("--chave", required=True, help="chave de acesso da NFS-e, 50 dígitos")
    parser.add_argument(
        "--motivo",
        required=True,
        type=int,
        choices=(1, 2, 9),
        help="1 Erro na Emissão, 2 Serviço não Prestado, 9 Outros",
    )
    parser.add_argument(
        "--descricao",
        required=True,
        help="explicação do motivo, de 15 a 255 caracteres, sem travessão nem aspas curvas",
    )
    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="envia o pedido; sem esta opção, nada é enviado. O cancelamento não volta atrás",
    )
    args = parser.parse_args(argv)

    try:
        if not _CHAVE.fullmatch(args.chave):
            raise ValueError("chave de acesso fora do formato: 50 dígitos")
        config = config or carregar_config()
        emitente = carregar_emitente(args.emitente, pasta)
        if _cnpj_da_chave(args.chave) != emitente.cnpj:
            raise ValueError(
                "a chave não é de uma nota deste emitente (o CNPJ da chave é outro); nada foi feito"
            )
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
        # Criado também sem --confirmar, para recusar produção desde já (INV-02); o cliente
        # não abre conexão antes do primeiro pedido.
        cliente = ClienteNfse(config, cert, transporte=transporte)
        pedido = PedidoCancelamento(
            chave=args.chave,
            cnpj_autor=emitente.cnpj,
            tp_amb=config.tp_amb,
            dh_evento=datetime.now(BRT),
            c_motivo=args.motivo,
            x_motivo=args.descricao,
        )
    except ValueError as erro:
        _erro(str(erro))
        return 1

    xsd_local = preparar_copia_local(config.xsd_dir)
    xsd_pedido, xsd_evento = localizar_xsd_pedido_evento(xsd_local), localizar_xsd_evento(xsd_local)
    if xsd_pedido is None or xsd_evento is None:
        _erro(f"XSD do pedido de evento ou do evento não encontrado em {config.xsd_dir}")
        return 1
    try:
        assinado = assinar_pedido_evento(para_xml_pedido(pedido), cert)
        conferir_assinatura(assinado, cert.certificado)
    except ValueError as erro:
        _erro(str(erro))
        return 1
    erros = validar_xml(assinado, xsd_pedido)
    if erros:
        _erro(f"pedido inválido contra {xsd_pedido.name}: {erros[0]}")
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    arquivo = saida / f"{pedido.id}-assinado.xml"
    arquivo.write_bytes(assinado)
    print(f"Pedido de cancelamento assinado e válido: {arquivo}")
    if not args.confirmar:
        print(
            "Nada foi enviado. Para cancelar a NFS-e, o que não volta atrás, rode de novo com "
            "--confirmar"
        )
        return 0

    print(f"SEFIN: {cliente.sefin_url}")
    with cliente:
        try:
            resultado = cancelar(cliente, assinado, xsd_evento)
        except NotaJaCancelada as erro:
            _erro(str(erro))
            print(f"Evento já registrado: {_salvar_evento(saida, args.chave, erro.evento)}")
            return JA_CANCELADA
        except RejeicaoApi as erro:
            _erro(str(erro))
            for mensagem in erro.mensagens:
                if mensagem.codigo in DICAS:
                    _erro(f"{mensagem.codigo}: {DICAS[mensagem.codigo]}")
            _salvar_resposta(saida, pedido.id, erro)
            return REJEITADA
        except CancelamentoIncerto as erro:
            _erro(str(erro))
            return CANCELAMENTO_INCERTO
        except ErroConexao as erro:
            _erro(f"erro de conexão: {erro}")
            return ERRO_DE_REDE
        except RespostaInesperada as erro:
            _erro(str(erro))
            _salvar_resposta(saida, pedido.id, erro)
            return RESPOSTA_INESPERADA
        except ValueError as erro:
            _erro(str(erro))
            return 1

    arquivo = _salvar_evento(saida, args.chave, resultado.evento)
    if resultado.recuperado:
        print(f"[!] {_causa(resultado.falha)}; o evento foi recuperado pela consulta")
        if isinstance(resultado.falha, RespostaInesperada):
            _salvar_resposta(saida, pedido.id, resultado.falha)
    seq, quando = _resumo(resultado.evento)
    print(f"Chave de acesso: {args.chave}")
    print(f"Sequência: {seq}  Processado em: {quando}")
    print(f"Evento: {arquivo}")
    if resultado.problemas:
        for problema in resultado.problemas:
            _erro(f"conferência do evento: {problema}")
        return CONFERENCIA_FALHOU
    print("[OK] Evento de cancelamento conferido: XSD, chave, tipo, ambiente, pedido e assinatura")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
