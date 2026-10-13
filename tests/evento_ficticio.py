"""Evento fictício de cancelamento (101101) para simular a consulta de eventos (T-028).

Segue o leiaute do Anexo II v1.01 e leva uma assinatura que faz o papel da do sistema
nacional, feita com o certificado autoassinado de tests/pfx.py. Nenhum dado aqui é real.
"""

from lxml import etree
from signxml import XMLSigner, namespaces

from src.assinatura import ASSINATURA, C14N, DIGEST
from src.dps import NS
from tests.nfse_ficticia import CHAVE
from tests.pfx import CNPJ, chave_de_teste, gerar_certificado

CANCELAMENTO = "101101"
SUBSTITUICAO = "105102"


def _sub(pai, nome: str, texto: str | None = None):
    el = etree.SubElement(pai, f"{{{NS}}}{nome}")
    if texto is not None:
        el.text = texto
    return el


def gerar_evento(
    *,
    chave: str = CHAVE,
    tipo: str = CANCELAMENTO,
    tp_amb: str = "2",
    assinar: bool = True,
    id_pedido: str | None = None,
    ch_substituta: str | None = None,
) -> bytes:
    raiz = etree.Element(f"{{{NS}}}evento", nsmap={None: NS}, versao="1.01")
    inf = _sub(raiz, "infEvento")
    # Anexo II: "EVT" + Id do pedido sem "PRE" (chave + código do evento) + nSeqEvento (3).
    id_evento = f"EVT{chave}{tipo}001"
    inf.set("Id", id_evento)
    _sub(inf, "verAplic", "Ficticio_1.0")
    _sub(inf, "ambGer", "2")
    _sub(inf, "nSeqEvento", "1")
    _sub(inf, "dhProc", "2026-10-12T11:00:00-03:00")
    _sub(inf, "nDFSe", "1")
    ped = _sub(inf, "pedRegEvento")
    ped.set("versao", "1.01")
    inf_ped = _sub(ped, "infPedReg")
    inf_ped.set("Id", id_pedido or f"PRE{chave}{tipo}")
    _sub(inf_ped, "tpAmb", tp_amb)
    _sub(inf_ped, "verAplic", "Ficticio_1.0")
    _sub(inf_ped, "dhEvento", "2026-10-12T10:59:00-03:00")
    _sub(inf_ped, "CNPJAutor", CNPJ)
    _sub(inf_ped, "chNFSe", chave)
    if tipo == SUBSTITUICAO:
        # Gerado pelo sistema ao receber a DPS substituta (T-031).
        grupo = _sub(inf_ped, f"e{SUBSTITUICAO}")
        _sub(grupo, "xDesc", "Cancelamento de NFS-e por Substituição")
        _sub(grupo, "cMotivo", "99")
        _sub(grupo, "xMotivo", "Substituicao de teste, nota ficticia")
        _sub(grupo, "chSubstituta", ch_substituta or chave)
    else:
        grupo = _sub(inf_ped, f"e{CANCELAMENTO}")
        _sub(grupo, "xDesc", "Cancelamento de NFS-e")
        _sub(grupo, "cMotivo", "1")
        _sub(grupo, "xMotivo", "Erro na emissão, nota fictícia")

    if assinar:
        signer = XMLSigner(
            signature_algorithm=ASSINATURA, digest_algorithm=DIGEST, c14n_algorithm=C14N
        )
        signer.namespaces = {None: namespaces.ds}
        raiz = signer.sign(
            raiz, key=chave_de_teste(), cert=[gerar_certificado()], reference_uri=f"#{id_evento}"
        )
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")
