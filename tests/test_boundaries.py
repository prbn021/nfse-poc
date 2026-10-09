"""Boundaries B-1 a B-3 de docs/SPEC.md §3, conferidas pelos imports de src/ e scripts/.

T-016, DEC-017; scripts/ entrou na T-015 (DEC-031).
"""

import pytest

from src.config import RAIZ
from tests.boundaries import ler_fontes, violacoes

# Módulos de exemplo: nenhum deles existe em src/ com este conteúdo.
LIMPO = "import re\nfrom lxml import etree\n"


def test_o_codigo_atual_respeita_as_boundaries():
    fontes = ler_fontes(RAIZ)
    # Sem isto o teste passaria sem ter lido nada.
    assert "src/dps.py" in fontes
    assert "src/__init__.py" in fontes
    assert "scripts/gerar_dps.py" in fontes
    assert all(caminho.startswith(("src/", "scripts/")) for caminho in fontes)
    assert violacoes(fontes) == []


# --- B-1: src/dps.py não depende de rede nem de certificado ---------------------------


def test_b1_dps_importa_biblioteca_de_rede():
    fontes = {"src/dps.py": "import httpx\n"}
    assert violacoes(fontes) == ["B-1: src.dps -> httpx", "B-2: src.dps -> httpx"]


@pytest.mark.parametrize(
    ("codigo", "alvo"),
    [
        ("from cryptography.hazmat.primitives.serialization import pkcs12\n", "cryptography"),
        ("import signxml\n", "signxml"),
        ("from src.certificado import carregar\n", "src.certificado"),
        ("from src import certificado\n", "src.certificado"),
        ("from . import certificado\n", "src.certificado"),
        ("from .certificado import carregar\n", "src.certificado"),
    ],
)
def test_b1_dps_importa_modulo_de_certificado(codigo, alvo):
    fontes = {"src/dps.py": codigo, "src/certificado.py": "import cryptography\n"}
    assert violacoes(fontes) == [f"B-1: src.dps -> {alvo}"]


def test_b1_dps_importa_o_cliente_de_rede():
    fontes = {"src/dps.py": "from src.client import enviar\n", "src/client.py": "import httpx\n"}
    assert violacoes(fontes) == ["B-1: src.dps -> src.client"]


def test_b1_dps_chega_a_rede_por_outro_modulo():
    fontes = {
        "src/dps.py": "from src.util import baixar\n",
        "src/util.py": "from src.outro import abrir\n",
        "src/outro.py": "def abrir():\n    import socket\n",
    }
    assert violacoes(fontes) == [
        "B-1: src.dps -> src.util -> src.outro -> socket",
        "B-2: src.outro -> socket",
    ]


def test_b1_dps_chega_a_certificado_pelo_init_do_pacote():
    # Importar src.dps executa src/__init__.py antes.
    fontes = {"src/__init__.py": "import cryptography\n", "src/dps.py": LIMPO}
    assert violacoes(fontes) == ["B-1: src.dps -> src -> cryptography"]


def test_b1_so_vale_para_dps():
    fontes = {"src/assinatura.py": "import signxml\nfrom src.certificado import carregar\n"}
    assert violacoes(fontes) == []


# --- B-2: só src/client.py faz I/O de rede --------------------------------------------


@pytest.mark.parametrize(
    ("codigo", "alvo"),
    [
        ("import httpx\n", "httpx"),
        ("import requests as r\n", "requests"),
        ("import urllib.request\n", "urllib.request"),
        ("from urllib import request\n", "urllib.request"),
        ("from urllib.request import urlopen\n", "urllib.request"),
        ("from http import client\n", "http.client"),
        ("from http.client import HTTPSConnection\n", "http.client"),
        ("import ssl\n", "ssl"),
        ("def f():\n    import socket\n    return socket\n", "socket"),
        ("try:\n    import urllib3\nexcept ImportError:\n    pass\n", "urllib3"),
    ],
)
def test_b2_outro_modulo_importa_biblioteca_de_rede(codigo, alvo):
    assert violacoes({"src/xsd.py": codigo}) == [f"B-2: src.xsd -> {alvo}"]


def test_b2_client_pode_importar_biblioteca_de_rede():
    fontes = {"src/client.py": "import ssl\nimport httpx\n", "src/dps.py": LIMPO}
    assert violacoes(fontes) == []


def test_b2_outro_modulo_pode_usar_o_client():
    fontes = {
        "src/emissao.py": "from src.client import enviar\n",
        "src/client.py": "import httpx\n",
    }
    assert violacoes(fontes) == []


@pytest.mark.parametrize(
    "codigo", ["import httpx\n", "import ssl\n", "from socket import socket\n"]
)
def test_b2_script_importa_biblioteca_de_rede(codigo):
    alvo = codigo.split()[1]
    assert violacoes({"scripts/testar_conexao.py": codigo}) == [
        f"B-2: scripts.testar_conexao -> {alvo}"
    ]


def test_b2_script_pode_usar_o_client():
    fontes = {
        "scripts/testar_conexao.py": "from src.client import ClienteNfse\n",
        "src/client.py": "import httpx\n",
    }
    assert violacoes(fontes) == []


@pytest.mark.parametrize(
    "codigo",
    [
        "from urllib.parse import quote\n",
        "from http import HTTPStatus\n",
        "import socket_falso\n",
        "import httpx_parecido.util\n",
        "import gzip\nimport base64\n",
    ],
)
def test_b2_import_que_nao_e_de_rede_passa(codigo):
    assert violacoes({"src/xsd.py": codigo}) == []


# --- B-3: src/ nunca depende de scripts/ ----------------------------------------------


@pytest.mark.parametrize(
    "codigo",
    [
        "import scripts\n",
        "import scripts.gerar_dps\n",
        "from scripts import gerar_dps\n",
        "from scripts.gerar_dps import main\n",
        "def f():\n    from scripts.preparar_xsd import main\n    return main\n",
    ],
)
def test_b3_src_importa_de_scripts(codigo):
    assert violacoes({"src/config.py": codigo}) == ["B-3: src.config -> scripts"]


def test_b3_nao_vale_dentro_de_scripts():
    fontes = {"scripts/emitir.py": "from scripts import gerar_dps\nfrom src.dps import Dps\n"}
    assert violacoes(fontes) == []


def test_b3_nome_parecido_com_scripts_passa():
    assert violacoes({"src/config.py": "import scripts_util\nfrom src import scripts_x\n"}) == []


# --- várias de uma vez -----------------------------------------------------------------


def test_violacoes_saem_ordenadas_e_sem_repeticao():
    fontes = {
        "src/dps.py": "import httpx\nfrom httpx import Client\nimport scripts\n",
        "src/xsd.py": "import socket\n",
    }
    assert violacoes(fontes) == [
        "B-1: src.dps -> httpx",
        "B-2: src.dps -> httpx",
        "B-2: src.xsd -> socket",
        "B-3: src.dps -> scripts",
    ]
