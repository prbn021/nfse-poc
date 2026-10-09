"""O script de exemplo monta a DPS com os dados do emitente escolhido (T-019)."""

import sys

import pytest

from src.config import RAIZ
from src.emitente import Emitente, carregar_emitente

sys.path.insert(0, str(RAIZ / "scripts"))

import gerar_dps


def test_dps_do_emitente_de_exemplo_mantem_o_id_de_antes():
    dps = gerar_dps.dps_exemplo(2, carregar_emitente("exemplo"))
    assert dps.id == "DPS330455721122233300018100001000000000000001"
    assert dps.prestador.inscricao_municipal == "12345"
    assert dps.prestador.op_simp_nac == 3


def test_dps_usa_os_dados_do_emitente_recebido():
    # Dados FICTÍCIOS de outro emitente, de outro município (INV-06).
    outro = Emitente(
        nome="beta",
        cnpj="99888777000161",
        municipio="3550308",
        inscricao_municipal=None,
        op_simp_nac=3,
        reg_esp_trib=0,
        cert_path=RAIZ / "certs" / "beta.pfx",
        cert_senha="senha-ficticia",
    )
    dps = gerar_dps.dps_exemplo(2, outro)
    assert dps.c_loc_emi == "3550308"
    assert dps.prestador.cnpj == "99888777000161"
    assert dps.prestador.inscricao_municipal is None
    assert dps.id.startswith("DPS3550308299888777000161")


def test_emitente_inexistente_sai_com_erro_claro(capsys):
    with pytest.raises(SystemExit) as saida:
        gerar_dps.main(["--emitente", "nao-existe"])
    assert saida.value.code == 2
    assert "emitente 'nao-existe' não encontrado" in capsys.readouterr().err
