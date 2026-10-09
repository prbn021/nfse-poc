"""O script manual mostra só titular, CNPJ e validade do certificado do emitente (T-004)."""

import datetime
import sys

import pytest

from src.config import RAIZ
from tests.pfx import CNPJ, TITULAR, gerar_pfx

sys.path.insert(0, str(RAIZ / "scripts"))

import ver_certificado

SENHA = "s3nh4-f1ct1c14-xyz"
INICIO = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)


def emitente(pasta, *, senha=SENHA, pfx: bytes | None = None, nome="acme"):
    """Grava um PFX autoassinado e o arquivo do emitente fictício que aponta para ele."""
    if pfx is None:
        pfx = gerar_pfx(SENHA, inicio=INICIO, dias=365)
    (pasta / f"{nome}.pfx").write_bytes(pfx)
    (pasta / f"{nome}.toml").write_text(
        f'cnpj = "{CNPJ}"\nmunicipio = "3304557"\nop_simp_nac = 3\nreg_esp_trib = 0\n\n'
        f'[certificado]\ncaminho = "{(pasta / nome).as_posix()}.pfx"\nsenha = "{senha}"\n',
        encoding="utf-8",
    )
    return pasta


def test_mostra_so_titular_cnpj_e_validade(tmp_path, capsys):
    assert ver_certificado.main(["--emitente", "acme"], pasta=emitente(tmp_path)) == 0
    saida = capsys.readouterr()
    assert saida.err == ""
    assert saida.out.splitlines() == [
        f"Titular:  {TITULAR}",
        f"CNPJ:     {CNPJ}",
        "Validade: de 2026-01-02 03:04:05 UTC até 2027-01-02 03:04:05 UTC",
    ]
    assert SENHA not in saida.out


def test_certificado_sem_cnpj(tmp_path, capsys):
    pfx = gerar_pfx(SENHA, cn="EMPRESA FICTICIA LTDA", cnpj_no_san=None)
    assert ver_certificado.main(["--emitente", "acme"], pasta=emitente(tmp_path, pfx=pfx)) == 0
    assert "CNPJ:     não encontrado no certificado" in capsys.readouterr().out


def test_senha_errada_sai_com_erro_sem_mostrar_a_senha(tmp_path, capsys):
    pasta = emitente(tmp_path, senha="0utr4-s3nh4-qwe")
    assert ver_certificado.main(["--emitente", "acme"], pasta=pasta) == 1
    saida = capsys.readouterr()
    assert saida.out == ""
    assert "senha incorreta" in saida.err
    assert "0utr4-s3nh4-qwe" not in saida.err
    assert SENHA not in saida.err


def test_emitente_inexistente(tmp_path, capsys):
    assert ver_certificado.main(["--emitente", "nao-existe"], pasta=tmp_path) == 1
    assert "emitente 'nao-existe' não encontrado" in capsys.readouterr().err


def test_emitente_e_obrigatorio(capsys):
    with pytest.raises(SystemExit) as saida:
        ver_certificado.main([])
    assert saida.value.code == 2
    assert "--emitente" in capsys.readouterr().err


def test_o_emitente_de_exemplo_nao_tem_certificado(capsys):
    assert ver_certificado.main(["--emitente", "exemplo"]) == 1
    assert "certificado não encontrado" in capsys.readouterr().err
