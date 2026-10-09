"""Configuração por emitente (T-019, DEC-024). Todos os dados são FICTÍCIOS."""

import pytest

from src.config import RAIZ
from src.emitente import Emitente, carregar_emitente

SENHA = "s3nh4-f1ct1c14-xyz"

COMPLETO = f"""\
cnpj = "11222333000181"
municipio = "3304557"
inscricao_municipal = "12345"
op_simp_nac = 3
reg_esp_trib = 0

[certificado]
caminho = "certs/acme.pfx"
senha = "{SENHA}"
"""


def gravar(pasta, nome="acme", texto=COMPLETO):
    (pasta / f"{nome}.toml").write_text(texto, encoding="utf-8")
    return pasta


def sem_linha(chave):
    return "".join(
        linha for linha in COMPLETO.splitlines(keepends=True) if not linha.startswith(chave)
    )


def test_carrega_um_arquivo_completo(tmp_path):
    emitente = carregar_emitente("acme", gravar(tmp_path))
    assert emitente == Emitente(
        nome="acme",
        cnpj="11222333000181",
        municipio="3304557",
        inscricao_municipal="12345",
        op_simp_nac=3,
        reg_esp_trib=0,
        cert_path=RAIZ / "certs" / "acme.pfx",
        cert_senha=SENHA,
    )


def test_inscricao_municipal_e_opcional(tmp_path):
    gravar(tmp_path, texto=sem_linha("inscricao_municipal"))
    assert carregar_emitente("acme", tmp_path).inscricao_municipal is None


def test_caminho_absoluto_do_certificado_e_mantido(tmp_path):
    absoluto = (tmp_path / "fora" / "acme.pfx").as_posix()
    gravar(tmp_path, texto=COMPLETO.replace("certs/acme.pfx", absoluto))
    assert carregar_emitente("acme", tmp_path).cert_path == tmp_path / "fora" / "acme.pfx"


def test_nao_exige_que_o_certificado_exista(tmp_path):
    emitente = carregar_emitente("acme", gravar(tmp_path))
    assert not emitente.cert_path.exists()


def test_dois_emitentes_na_mesma_pasta(tmp_path):
    # INV-06: os dados vêm do arquivo de cada emitente, não do código.
    gravar(tmp_path)
    outro = (
        COMPLETO.replace("11222333000181", "99888777000161")
        .replace("3304557", "3550308")
        .replace("certs/acme.pfx", "certs/beta.pfx")
    )
    gravar(tmp_path, nome="beta", texto=outro)
    acme = carregar_emitente("acme", tmp_path)
    beta = carregar_emitente("beta", tmp_path)
    assert (acme.cnpj, acme.municipio) == ("11222333000181", "3304557")
    assert (beta.cnpj, beta.municipio) == ("99888777000161", "3550308")
    assert acme.cert_path != beta.cert_path


def test_o_exemplo_versionado_carrega():
    emitente = carregar_emitente("exemplo")
    assert emitente.nome == "exemplo"
    assert emitente.op_simp_nac == 3
    assert not emitente.cert_path.exists()


# --- erros ------------------------------------------------------------------------------


def test_emitente_inexistente(tmp_path):
    with pytest.raises(ValueError, match="emitente 'acme' não encontrado") as erro:
        carregar_emitente("acme", tmp_path)
    assert "acme.toml" in str(erro.value)
    assert "exemplo.toml" in str(erro.value)


@pytest.mark.parametrize(
    "nome", ["", "../acme", "sub/acme", "sub\\acme", "acme.toml", "Acme", "a b"]
)
def test_nome_de_emitente_invalido(tmp_path, nome):
    gravar(tmp_path)
    with pytest.raises(ValueError, match="nome de emitente inválido"):
        carregar_emitente(nome, tmp_path)


@pytest.mark.parametrize(
    ("chave", "citada"),
    [
        ("cnpj", "cnpj"),
        ("municipio", "municipio"),
        ("op_simp_nac", "op_simp_nac"),
        ("reg_esp_trib", "reg_esp_trib"),
        ("caminho", "certificado.caminho"),
        ("senha", "certificado.senha"),
    ],
)
def test_chave_obrigatoria_ausente(tmp_path, chave, citada):
    gravar(tmp_path, texto=sem_linha(chave))
    with pytest.raises(ValueError, match="incompleto") as erro:
        carregar_emitente("acme", tmp_path)
    assert citada in str(erro.value)
    assert "acme.toml" in str(erro.value)


def test_secao_certificado_ausente(tmp_path):
    gravar(tmp_path, texto=COMPLETO.split("[certificado]")[0])
    with pytest.raises(ValueError, match="incompleto") as erro:
        carregar_emitente("acme", tmp_path)
    assert "certificado.caminho" in str(erro.value)
    assert "certificado.senha" in str(erro.value)


@pytest.mark.parametrize(
    ("texto", "onde", "aceitas"),
    [
        ('cnpjj = "1"\n' + COMPLETO, "na raiz", "cnpj, inscricao_municipal, municipio"),
        (COMPLETO + 'senhaa = "1"\n', r"em \[certificado\]", "caminho, senha"),
    ],
)
def test_chave_desconhecida(tmp_path, texto, onde, aceitas):
    gravar(tmp_path, texto=texto)
    with pytest.raises(ValueError, match=f"chave desconhecida {onde}") as erro:
        carregar_emitente("acme", tmp_path)
    # O nome da chave não é repetido: quem digitou errado pode ter posto a senha ali.
    assert "cnpjj" not in str(erro.value)
    assert "senhaa" not in str(erro.value)
    assert aceitas in str(erro.value)


@pytest.mark.parametrize(
    ("antigo", "novo", "citada"),
    [
        ('cnpj = "11222333000181"', "cnpj = 11222333000181", "cnpj"),
        ("op_simp_nac = 3", 'op_simp_nac = "3"', "op_simp_nac"),
        ("op_simp_nac = 3", "op_simp_nac = true", "op_simp_nac"),
        ("reg_esp_trib = 0", "reg_esp_trib = 0.5", "reg_esp_trib"),
        (f'senha = "{SENHA}"', "senha = 123456", "certificado.senha"),
        ('caminho = "certs/acme.pfx"', 'caminho = ""', "certificado.caminho"),
        ('cnpj = "11222333000181"', 'cnpj = "1122233300018"', "cnpj"),
        ('cnpj = "11222333000181"', 'cnpj = "11.222.333/0001-81"', "cnpj"),
        ('municipio = "3304557"', 'municipio = "330455"', "municipio"),
        ('inscricao_municipal = "12345"', 'inscricao_municipal = ""', "inscricao_municipal"),
        ("op_simp_nac = 3", "op_simp_nac = 4", "op_simp_nac"),
        ("op_simp_nac = 3", "op_simp_nac = 0", "op_simp_nac"),
        ("reg_esp_trib = 0", "reg_esp_trib = -1", "reg_esp_trib"),
    ],
)
def test_valor_invalido(tmp_path, antigo, novo, citada):
    assert antigo in COMPLETO
    gravar(tmp_path, texto=COMPLETO.replace(antigo, novo))
    with pytest.raises(ValueError, match=f"{citada}.*inválid") as erro:
        carregar_emitente("acme", tmp_path)
    assert "acme.toml" in str(erro.value)


def test_certificado_que_nao_e_secao(tmp_path):
    gravar(tmp_path, texto=COMPLETO.split("[certificado]")[0] + f'certificado = "{SENHA}"\n')
    with pytest.raises(ValueError, match=r"certificado.*inválid"):
        carregar_emitente("acme", tmp_path)


def test_arquivo_que_nao_e_utf8(tmp_path):
    (tmp_path / "acme.toml").write_bytes(COMPLETO.encode("utf-8") + bytes([0x23, 0xFF]))
    with pytest.raises(ValueError, match=r"acme.toml: não está em UTF-8") as erro:
        carregar_emitente("acme", tmp_path)
    assert erro.value.__context__ is None


def test_toml_malformado_cita_arquivo_e_linha(tmp_path):
    gravar(tmp_path, texto=COMPLETO.replace("op_simp_nac = 3", "op_simp_nac 3"))
    with pytest.raises(ValueError, match="TOML inválido") as erro:
        carregar_emitente("acme", tmp_path)
    assert "acme.toml" in str(erro.value)
    assert "linha 4" in str(erro.value)


# --- INV-05: a senha nunca aparece em repr nem em mensagem de erro ------------------------


def test_senha_nao_aparece_no_repr(tmp_path):
    emitente = carregar_emitente("acme", gravar(tmp_path))
    assert emitente.cert_senha == SENHA
    assert SENHA not in repr(emitente)
    assert SENHA not in str(emitente)
    assert "cert_senha" not in repr(emitente)


ERROS_COM_SENHA_NO_ARQUIVO = [
    # TOML malformado justamente na linha da senha
    COMPLETO.replace(f'senha = "{SENHA}"', f'senha = "{SENHA}'),
    COMPLETO.replace(f'senha = "{SENHA}"', f"senha = {SENHA}"),
    COMPLETO.replace(f'senha = "{SENHA}"', f'senha "{SENHA}"'),
    # senha repetida
    COMPLETO + f'senha = "{SENHA}"\n',
    # senha na chave errada
    COMPLETO + f'senhaa = "{SENHA}"\n',
    f'senha = "{SENHA}"\n' + COMPLETO,
    # senha usada como nome de chave
    COMPLETO + f'"{SENHA}" = 1\n',
    # senha no lugar de outro valor
    COMPLETO.replace('"11222333000181"', f'"{SENHA}"'),
    COMPLETO.replace("op_simp_nac = 3", f'op_simp_nac = "{SENHA}"'),
    # outro erro, com a senha certa no arquivo
    COMPLETO.replace("op_simp_nac = 3", "op_simp_nac = 9"),
    sem_linha("cnpj"),
]


@pytest.mark.parametrize("texto", ERROS_COM_SENHA_NO_ARQUIVO, ids=range(11))
def test_senha_nao_aparece_em_mensagem_de_erro(tmp_path, texto):
    gravar(tmp_path, texto=texto)
    with pytest.raises(ValueError) as erro:
        carregar_emitente("acme", tmp_path)
    assert SENHA not in str(erro.value)
    assert SENHA not in repr(erro.value)
    # Nem pela exceção original do tomllib, que não pode ficar encadeada.
    assert erro.value.__cause__ is None
    assert erro.value.__suppress_context__ or erro.value.__context__ is None
