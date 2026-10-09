import pytest

from src.segredos import proibidos


@pytest.mark.parametrize(
    "caminho",
    [
        ".env",
        "config/.env",
        "certs/cliente.pfx",
        "certs/CLIENTE.PFX",
        "a/b/chave.p12",
        "chave.pem",
        "docs/referencia/nota-de-cliente.pdf",
        "docs/referencia/nota-de-cliente.xml",
        "docs/referencia/outra-pasta/arquivo.txt",
        "docs\\referencia\\nota-de-cliente.pdf",
        "emitentes/acme.toml",
        "emitentes/acme.json",
        "emitentes/sub/exemplo.toml",
        "emitentes\\acme.toml",
        "emitentes/EXEMPLO.toml",
    ],
)
def test_arquivo_de_segredo_e_apontado(caminho):
    assert proibidos([caminho]) == [caminho]


@pytest.mark.parametrize(
    "caminho",
    [
        ".env.example",
        "src/config.py",
        "docs/SPEC.md",
        "schemas/1.01/DPS_v1.01.xsd",
        "tests/test_segredos.py",
        "docs/referencia/gov-docs/LEIAME.md",
        "docs/referencia/gov-docs/SHA256SUMS",
        "docs/referencia/gov-docs/anexo_i.xlsx",
        "docs/referencia-de-estilo.md",
        "emitentes/exemplo.toml",
        "emitentes\\exemplo.toml",
        "src/emitente.py",
        "docs/emitentes/acme.toml",
    ],
)
def test_arquivo_comum_passa(caminho):
    assert proibidos([caminho]) == []


def test_lista_mista_devolve_so_os_proibidos_na_ordem():
    assert proibidos(["README.md", "b.pem", ".env", "src/dps.py"]) == ["b.pem", ".env"]
