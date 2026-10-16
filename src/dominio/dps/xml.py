"""XML da DPS, sem assinatura, na ordem do XSD (T-043, saiu de src/dps.py).

ATENÇÃO: a estrutura segue o layout da DPS v1.x, mas o XSD oficial é a fonte de verdade. Rode
`scripts/gerar_dps.py`: se a validação reclamar de ordem/obrigatoriedade de elementos, ajuste
`para_xml()` conforme o XSD.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from lxml import etree

from src.dominio.dps.modelo import Dps, IbsCbs, Obra
from src.dominio.xsd import NS, VERSAO


def _dinheiro(valor: Decimal) -> str:
    return f"{Decimal(valor):.2f}"


def _sub(pai, nome: str, texto: str | None = None):
    el = etree.SubElement(pai, f"{{{NS}}}{nome}")
    if texto is not None:
        el.text = texto
    return el


def para_xml(dps: Dps) -> bytes:
    """Gera o XML da DPS, SEM assinatura. Ordem dos elementos = ordem do XSD."""
    raiz = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS}, versao=VERSAO)
    inf = _sub(raiz, "infDPS")
    inf.set("Id", dps.id)

    _sub(inf, "tpAmb", str(dps.tp_amb))
    _sub(inf, "dhEmi", dps.dh_emi.isoformat(timespec="seconds"))
    _sub(inf, "verAplic", dps.ver_aplic)
    _sub(inf, "serie", str(dps.serie))
    _sub(inf, "nDPS", str(dps.n_dps))
    _sub(inf, "dCompet", dps.d_compet.isoformat())
    _sub(inf, "tpEmit", str(dps.tp_emit))
    _sub(inf, "cLocEmi", dps.c_loc_emi)
    if dps.subst is not None:
        subst = _sub(inf, "subst")
        _sub(subst, "chSubstda", dps.subst.chave)
        _sub(subst, "cMotivo", f"{dps.subst.c_motivo:02d}")
        if dps.subst.x_motivo is not None:
            _sub(subst, "xMotivo", dps.subst.x_motivo)

    prest = _sub(inf, "prest")
    _sub(prest, "CNPJ", dps.prestador.cnpj)
    if dps.prestador.inscricao_municipal:
        _sub(prest, "IM", dps.prestador.inscricao_municipal)
    if dps.prestador.fone is not None:
        _sub(prest, "fone", dps.prestador.fone)
    if dps.prestador.email is not None:
        _sub(prest, "email", dps.prestador.email)
    reg = _sub(prest, "regTrib")
    _sub(reg, "opSimpNac", str(dps.prestador.op_simp_nac))
    if dps.prestador.reg_ap_trib_sn is not None:
        _sub(reg, "regApTribSN", str(dps.prestador.reg_ap_trib_sn))
    _sub(reg, "regEspTrib", str(dps.prestador.reg_esp_trib))

    toma = _sub(inf, "toma")
    if dps.tomador.cnpj:
        _sub(toma, "CNPJ", dps.tomador.cnpj)
    else:
        _sub(toma, "CPF", dps.tomador.cpf)
    _sub(toma, "xNome", dps.tomador.nome)

    serv = _sub(inf, "serv")
    loc = _sub(serv, "locPrest")
    _sub(loc, "cLocPrestacao", dps.servico.c_loc_prestacao)
    cserv = _sub(serv, "cServ")
    _sub(cserv, "cTribNac", dps.servico.c_trib_nac)
    if dps.servico.c_trib_mun is not None:
        _sub(cserv, "cTribMun", dps.servico.c_trib_mun)
    _sub(cserv, "xDescServ", dps.servico.descricao)
    if dps.servico.c_nbs is not None:
        _sub(cserv, "cNBS", dps.servico.c_nbs)
    if dps.servico.obra is not None:
        _obra_xml(serv, dps.servico.obra)

    val = _sub(inf, "valores")
    vsp = _sub(val, "vServPrest")
    _sub(vsp, "vServ", _dinheiro(dps.valores.v_serv))
    trib = _sub(val, "trib")
    tm = _sub(trib, "tribMun")
    _sub(tm, "tribISSQN", str(dps.valores.trib_issqn))
    _sub(tm, "tpRetISSQN", str(dps.valores.tp_ret_issqn))
    if dps.valores.p_aliq is not None:
        _sub(tm, "pAliq", _dinheiro(dps.valores.p_aliq))
    if dps.valores.pis_cofins is not None:
        pc = _sub(_sub(trib, "tribFed"), "piscofins")
        _sub(pc, "CST", dps.valores.pis_cofins.cst)
        if dps.valores.pis_cofins.tp_ret_pis_cofins is not None:
            _sub(pc, "tpRetPisCofins", str(dps.valores.pis_cofins.tp_ret_pis_cofins))
    # ME/EPP: indTotTrib é proibido (E0712); vai o percentual do Simples (DEC-013).
    tot = _sub(trib, "totTrib")
    _sub(tot, "pTotTribSN", _dinheiro(dps.valores.p_tot_trib_sn))
    if dps.ibs_cbs is not None:
        _ibs_cbs_xml(inf, dps.ibs_cbs)

    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


def _ibs_cbs_xml(inf, grupo: IbsCbs) -> None:
    # Ordem de TCRTCInfoIBSCBS: finNFSe, indFinal, cIndOp, (tpOper, gRefNFSe, tpEnteGov),
    # indDest, (dest, imovel), valores/trib/gIBSCBS (CST, cClassTrib).
    el = _sub(inf, "IBSCBS")
    _sub(el, "finNFSe", "0")
    if grupo.ind_final is not None:
        _sub(el, "indFinal", str(grupo.ind_final))
    _sub(el, "cIndOp", grupo.c_ind_op)
    _sub(el, "indDest", "0")
    g = _sub(_sub(_sub(el, "valores"), "trib"), "gIBSCBS")
    _sub(g, "CST", grupo.cst)
    _sub(g, "cClassTrib", grupo.c_class_trib)


def _obra_xml(serv, obra: Obra) -> None:
    el = _sub(serv, "obra")
    if obra.insc_imob_fisc is not None:
        _sub(el, "inscImobFisc", obra.insc_imob_fisc)
    if obra.c_obra is not None:
        _sub(el, "cObra", obra.c_obra)
    elif obra.c_cib is not None:
        _sub(el, "cCIB", obra.c_cib)
    else:
        end = _sub(el, "end")
        _sub(end, "CEP", obra.endereco.cep)
        _sub(end, "xLgr", obra.endereco.logradouro)
        _sub(end, "nro", obra.endereco.numero)
        if obra.endereco.complemento is not None:
            _sub(end, "xCpl", obra.endereco.complemento)
        _sub(end, "xBairro", obra.endereco.bairro)


def localizar_xsd_dps(xsd_dir: Path) -> Path | None:
    candidatos = sorted(Path(xsd_dir).glob("DPS_v*.xsd"))
    return candidatos[-1] if candidatos else None
