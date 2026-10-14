"""O script de exemplo monta a DPS com os dados do emitente escolhido (T-019, T-010)."""

import sys
from decimal import Decimal

import pytest

from src.config import RAIZ
from src.emitente import Emitente, carregar_emitente

sys.path.insert(0, str(RAIZ / "scripts"))

import gerar_dps


def test_dps_do_emitente_de_exemplo_mantem_o_id_de_antes():
    dps = gerar_dps.dps_exemplo(2, carregar_emitente("exemplo"))
    assert dps.id == "DPS330455721122233300018100001000000000000001"


def test_exemplo_usa_o_perfil_mais_comum_da_carteira():
    # ME/EPP pelo Simples, prestador sem inscrição municipal, tomador pessoa física
    # (DEC-013). Tudo fictício.
    dps = gerar_dps.dps_exemplo(2, carregar_emitente("exemplo"))
    assert dps.prestador.op_simp_nac == 3
    assert dps.prestador.reg_ap_trib_sn == 1
    assert dps.prestador.inscricao_municipal is None
    assert dps.tomador.cpf is not None and dps.tomador.cnpj is None
    assert dps.valores.p_tot_trib_sn == gerar_dps.P_TOT_TRIB_SN_FICTICIO


def test_exemplo_emite_os_campos_opcionais_das_notas_atuais():
    # T-018: cTribMun, fone, email e PIS/COFINS, com dados fictícios. O perfil de PIS/COFINS
    # é o da nota real do primeiro emitente: CST 08, sem retenção.
    emitente = carregar_emitente("exemplo")
    dps = gerar_dps.dps_exemplo(2, emitente)
    assert dps.servico.c_trib_mun is not None
    assert (dps.prestador.fone, dps.prestador.email) == (emitente.fone, emitente.email)
    assert dps.valores.pis_cofins.cst == "08"
    assert dps.valores.pis_cofins.tp_ret_pis_cofins == 0


def test_ptottribsn_vem_do_argumento():
    dps = gerar_dps.dps_exemplo(2, carregar_emitente("exemplo"), Decimal("4.50"))
    assert dps.valores.p_tot_trib_sn == Decimal("4.50")


def test_dps_usa_os_dados_do_emitente_recebido():
    # Dados FICTÍCIOS de outro emitente, de outro município (INV-06).
    outro = Emitente(
        nome="beta",
        cnpj="99888777000161",
        municipio="3550308",
        inscricao_municipal="98765",
        fone=None,
        email=None,
        op_simp_nac=3,
        reg_esp_trib=0,
        reg_ap_trib_sn=1,
        cert_path=RAIZ / "certs" / "beta.pfx",
        cert_senha="senha-ficticia",
    )
    dps = gerar_dps.dps_exemplo(2, outro)
    assert dps.c_loc_emi == "3550308"
    assert dps.prestador.cnpj == "99888777000161"
    assert dps.prestador.inscricao_municipal == "98765"
    assert dps.id.startswith("DPS3550308299888777000161")


def test_emitente_inexistente_sai_com_erro_claro(capsys):
    with pytest.raises(SystemExit) as saida:
        gerar_dps.main(["--emitente", "nao-existe"])
    assert saida.value.code == 2
    assert "emitente 'nao-existe' não encontrado" in capsys.readouterr().err


@pytest.mark.parametrize("valor", ["abc", "100", "6.123", "-1"])
def test_ptottribsn_invalido_sai_com_erro_claro(capsys, valor):
    with pytest.raises(SystemExit) as saida:
        gerar_dps.main(["--p-tot-trib-sn", valor])
    assert saida.value.code == 2
    assert "p_tot_trib_sn" in capsys.readouterr().err


# --- obra (T-020, DEC-047) -------------------------------------------------------------------

CNO_FICTICIO = "900000000001"


def test_exemplo_sem_obra_nao_tem_o_grupo():
    assert gerar_dps.dps_exemplo(2, carregar_emitente("exemplo")).servico.obra is None


def test_obra_e_codigo_vem_dos_argumentos():
    dps = gerar_dps.dps_exemplo(
        2, carregar_emitente("exemplo"), c_trib_nac="070202", obra_cno=CNO_FICTICIO
    )
    assert dps.servico.c_trib_nac == "070202"
    assert dps.servico.obra.c_obra == CNO_FICTICIO


def test_script_gera_dps_de_obra_valida(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert gerar_dps.main(["--c-trib-nac", "070202", "--obra-cno", CNO_FICTICIO]) == 0
    out = capsys.readouterr().out
    assert f"<cObra>{CNO_FICTICIO}</cObra>" in out
    assert "[OK] Válida" in out


def test_codigo_de_obra_sem_cno_sai_com_erro_claro(capsys):
    with pytest.raises(SystemExit) as saida:
        gerar_dps.main(["--c-trib-nac", "070202"])
    assert saida.value.code == 2
    assert "E0370" in capsys.readouterr().err


def test_cno_com_codigo_que_nao_e_de_obra_sai_com_erro_claro(capsys):
    with pytest.raises(SystemExit) as saida:
        gerar_dps.main(["--obra-cno", CNO_FICTICIO])
    assert saida.value.code == 2
    assert "E0372" in capsys.readouterr().err


# --- grupo IBS/CBS (T-034, DEC-069) ------------------------------------------------------


def test_exemplo_leva_o_grupo_ibscbs_do_anexo_viii_para_o_servico_padrao():
    # Serviço padrão fictício 01.01.01: a linha do Anexo VIII dá 100301 e 000001.
    dps = gerar_dps.dps_exemplo(2, carregar_emitente("exemplo"))
    assert (dps.ibs_cbs.c_ind_op, dps.ibs_cbs.c_class_trib) == ("100301", "000001")
    assert (gerar_dps.C_IND_OP_FICTICIO, gerar_dps.C_CLASS_TRIB_FICTICIO) == ("100301", "000001")
    # NBS do mesmo item (1.1502.10.00), exigido com o grupo (E0322).
    assert dps.servico.c_nbs == gerar_dps.C_NBS_FICTICIO == "115021000"


def test_codigos_ibscbs_vem_dos_argumentos(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    args = ["--c-ind-op", "030101", "--c-class-trib", "200052", "--c-nbs", "1.2301.23.00"]
    assert gerar_dps.main(args) == 0
    out = capsys.readouterr().out
    assert "<cNBS>123012300</cNBS>" in out
    assert "<cIndOp>030101</cIndOp>" in out
    assert "<CST>200</CST><cClassTrib>200052</cClassTrib>" in out
    assert "[OK] Válida" in out


def test_cind_op_invalido_sai_com_erro_claro(capsys):
    with pytest.raises(SystemExit) as saida:
        gerar_dps.main(["--c-ind-op", "080101"])
    assert saida.value.code == 2
    assert "E0901" in capsys.readouterr().err
