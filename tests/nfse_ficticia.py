"""NFS-e fictícia para simular o retorno da SEFIN nos testes (T-007). Nenhum dado aqui é real.

A NFS-e embute a DPS recebida e leva uma assinatura que faz o papel da do sistema nacional,
feita com o certificado autoassinado de tests/pfx.py.
"""

from lxml import etree
from signxml import XMLSigner, namespaces

from src.assinatura import ASSINATURA, C14N, DIGEST
from src.dps import NS
from tests.pfx import CNPJ, chave_de_teste, gerar_certificado

CHAVE = "33045572" + "2" + CNPJ + "0" * 27  # 50 dígitos, fictícia


def _sub(pai, nome: str, texto: str | None = None):
    el = etree.SubElement(pai, f"{{{NS}}}{nome}")
    if texto is not None:
        el.text = texto
    return el


def gerar_nfse(dps: bytes, *, chave: str = CHAVE, assinar: bool = True) -> bytes:
    raiz = etree.Element(f"{{{NS}}}NFSe", nsmap={None: NS}, versao="1.01")
    inf = _sub(raiz, "infNFSe")
    inf.set("Id", f"NFS{chave}")
    for nome, texto in [
        ("xLocEmi", "Rio de Janeiro"),
        ("xLocPrestacao", "Rio de Janeiro"),
        ("nNFSe", "1"),
        ("xTribNac", "Serviço fictício"),
        ("verAplic", "Ficticio_1.0"),
        ("ambGer", "2"),
        ("tpEmis", "1"),
        ("cStat", "100"),
        ("dhProc", "2026-10-12T10:00:00-03:00"),
        ("nDFSe", "1"),
    ]:
        _sub(inf, nome, texto)
    emit = _sub(inf, "emit")
    _sub(emit, "CNPJ", CNPJ)
    _sub(emit, "xNome", "EMPRESA FICTICIA LTDA")
    ender = _sub(emit, "enderNac")
    for nome, texto in [
        ("xLgr", "Rua Ficticia"),
        ("nro", "1"),
        ("xBairro", "Centro"),
        ("cMun", "3304557"),
        ("UF", "RJ"),
        ("CEP", "20000000"),
    ]:
        _sub(ender, nome, texto)
    _sub(_sub(inf, "valores"), "vLiq", "100.00")
    inf.append(etree.fromstring(dps))

    if assinar:
        signer = XMLSigner(
            signature_algorithm=ASSINATURA, digest_algorithm=DIGEST, c14n_algorithm=C14N
        )
        signer.namespaces = {None: namespaces.ds}
        raiz = signer.sign(
            raiz, key=chave_de_teste(), cert=[gerar_certificado()], reference_uri=f"#NFS{chave}"
        )
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")
