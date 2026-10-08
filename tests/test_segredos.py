import pytest

from src.segredos import proibidos


@pytest.mark.parametrize("caminho", [
    ".env",
    "config/.env",
    "certs/cliente.pfx",
    "certs/CLIENTE.PFX",
    "a/b/chave.p12",
    "chave.pem",
])
def test_arquivo_de_segredo_e_apontado(caminho):
    assert proibidos([caminho]) == [caminho]


@pytest.mark.parametrize("caminho", [
    ".env.example",
    "src/config.py",
    "docs/SPEC.md",
    "schemas/1.01/DPS_v1.01.xsd",
    "tests/test_segredos.py",
])
def test_arquivo_comum_passa(caminho):
    assert proibidos([caminho]) == []


def test_lista_mista_devolve_so_os_proibidos_na_ordem():
    assert proibidos(["README.md", "b.pem", ".env", "src/dps.py"]) == ["b.pem", ".env"]
