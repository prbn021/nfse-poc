import pytest

from src import config
from src.config import carregar_config

VARIAVEIS = (
    "NFSE_AMBIENTE",
    "NFSE_CERT_PATH",
    "NFSE_CERT_PASSWORD",
    "NFSE_SEFIN_URL",
    "NFSE_ADN_URL",
    "NFSE_XSD_DIR",
)


@pytest.fixture(autouse=True)
def sem_ambiente(monkeypatch):
    # Isola do .env da máquina e das variáveis já exportadas.
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    for nome in VARIAVEIS:
        monkeypatch.delenv(nome, raising=False)


def test_sem_variaveis_o_ambiente_e_homologacao():
    cfg = carregar_config()
    assert cfg.ambiente == "homologacao"
    assert cfg.tp_amb == 2


@pytest.mark.parametrize("valor", ["producao", "PRODUCAO", " Producao "])
def test_producao_e_recusado(monkeypatch, valor):
    monkeypatch.setenv("NFSE_AMBIENTE", valor)
    with pytest.raises(ValueError, match="INV-02") as erro:
        carregar_config()
    assert "DEC-002" in str(erro.value)


def test_ambiente_desconhecido_e_recusado(monkeypatch):
    monkeypatch.setenv("NFSE_AMBIENTE", "teste")
    with pytest.raises(ValueError, match="NFSE_AMBIENTE inválido"):
        carregar_config()


def test_env_example_nao_anuncia_producao():
    linhas = (config.RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
    ambiente = [linha for linha in linhas if linha.startswith("NFSE_AMBIENTE=")]
    assert len(ambiente) == 1
    assert ambiente[0].split("#")[0].strip() == "NFSE_AMBIENTE=homologacao"
    assert "| producao" not in ambiente[0]
