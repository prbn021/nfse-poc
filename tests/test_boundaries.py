"""Boundaries de docs/SPEC.md §3, conferidas pelos imports de src/ e scripts/.

B-1 a B-3: T-016, DEC-017; scripts/ entrou na T-015 (DEC-031). B-5: T-042 (DEC-076, DEC-077).
B-4, que amplia a B-1: T-043 (DEC-078).
"""

import pytest

from src.config import RAIZ
from tests.boundaries import dependencias, ler_fontes, violacoes

# Módulos de exemplo: nenhum deles existe em src/ com este conteúdo.
LIMPO = "import re\nfrom lxml import etree\n"
MODELO = "src/dominio/dps/modelo.py"


def test_o_codigo_atual_respeita_as_boundaries():
    fontes = ler_fontes(RAIZ)
    # Sem isto o teste passaria sem ter lido nada.
    assert MODELO in fontes
    assert "src/dominio/__init__.py" in fontes
    assert "src/__init__.py" in fontes
    assert "scripts/gerar_dps.py" in fontes
    assert "src/aplicacao/portas.py" in fontes
    assert all(caminho.startswith(("src/", "scripts/")) for caminho in fontes)
    assert violacoes(fontes) == []


# --- B-4 (amplia a B-1): src/dominio/ só importa biblioteca padrão, lxml e a si mesmo ---


def test_o_dominio_saiu_da_raiz_de_src():
    # Critério (1) da T-043: nenhum módulo de domínio solto em src/.
    fontes = ler_fontes(RAIZ)
    for antigo in ("dps", "nfse", "evento", "erros", "lista_servicos"):
        assert f"src/{antigo}.py" not in fontes, antigo
    for novo in ("dps/__init__", "nfse", "evento", "erros", "lista_servicos", "xsd", "chave"):
        assert f"src/dominio/{novo}.py" in fontes, novo


def test_b4_dominio_importa_biblioteca_de_rede():
    assert violacoes({MODELO: "import httpx\n"}) == [
        "B-2: src.dominio.dps.modelo -> httpx",
        "B-4: src.dominio.dps.modelo -> httpx",
    ]


@pytest.mark.parametrize(
    ("codigo", "alvo"),
    [
        ("from cryptography.hazmat.primitives.serialization import pkcs12\n", "cryptography"),
        ("import signxml\n", "signxml"),
        ("from src.certificado import carregar\n", "src.certificado"),
        ("from src import certificado\n", "src.certificado"),
        ("from ... import certificado\n", "src.certificado"),
        ("from ...certificado import carregar\n", "src.certificado"),
        ("from src.assinatura import conferir_assinatura_do_sistema\n", "src.assinatura"),
        ("from ... import assinatura\n", "src.assinatura"),
    ],
)
def test_b4_dominio_importa_modulo_de_certificado(codigo, alvo):
    fontes = {MODELO: codigo, "src/certificado.py": "import cryptography\n"}
    assert violacoes(fontes) == [f"B-4: src.dominio.dps.modelo -> {alvo}"]


@pytest.mark.parametrize(
    ("codigo", "alvo"),
    [
        ("from src.client import enviar\n", "src.client"),
        ("from src.config import carregar_config\n", "src.config"),
        ("from src.emitente import Emitente\n", "src.emitente"),
        ("from src.aplicacao.portas import SefinEmissao\n", "src.aplicacao"),
        ("from dotenv import load_dotenv\n", "dotenv"),
        ("import httpx_parecido\n", "httpx_parecido"),
        ("def f():\n    import src.segredos\n", "src.segredos"),
    ],
)
def test_b4_dominio_importa_o_que_nao_e_dominio(codigo, alvo):
    assert violacoes({"src/dominio/nfse.py": codigo}) == [f"B-4: src.dominio.nfse -> {alvo}"]


def test_b4_dominio_importa_de_scripts():
    assert violacoes({"src/dominio/evento.py": "from scripts import gerar_dps\n"}) == [
        "B-3: src.dominio.evento -> scripts",
        "B-4: src.dominio.evento -> scripts",
    ]


def test_b4_dominio_chega_a_certificado_pelo_init_de_src():
    # Importar src.dominio.dps.modelo executa src/__init__.py antes.
    fontes = {"src/__init__.py": "import cryptography\n", MODELO: LIMPO}
    assert violacoes(fontes) == ["B-4: src.dominio.dps.modelo -> src -> cryptography"]


def test_b4_init_do_pacote_do_dominio_tambem_conta():
    assert violacoes({"src/dominio/__init__.py": "import signxml\n"}) == [
        "B-4: src.dominio -> signxml"
    ]


def test_b4_cada_modulo_do_dominio_responde_pelo_proprio_import():
    # O módulo que importa outro do domínio não é apontado: quem cruza a boundary é o outro.
    fontes = {MODELO: "from src.dominio.xsd import NS\n", "src/dominio/xsd.py": "import signxml\n"}
    assert violacoes(fontes) == ["B-4: src.dominio.xsd -> signxml"]


@pytest.mark.parametrize(
    "codigo",
    [
        LIMPO,
        "from __future__ import annotations\nfrom dataclasses import dataclass\nimport zipfile\n",
        "from lxml.etree import XMLSchema\nimport lxml\n",
        "from typing import Protocol\n",
        "from src.dominio.xsd import NS\nfrom src.dominio import chave\n",
        "from . import regras\nfrom .regras import texto_tsstring\nfrom ..xsd import validar_xml\n",
    ],
)
def test_b4_dominio_pode_usar_biblioteca_padrao_lxml_e_a_si_mesmo(codigo):
    assert violacoes({MODELO: codigo}) == []


def test_b4_so_vale_dentro_de_src_dominio():
    fontes = {
        "src/assinatura.py": "import signxml\nfrom src.certificado import carregar\n",
        "src/dominio_velho.py": "import signxml\n",
        "scripts/dominio.py": "from src.config import carregar_config\n",
    }
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
        "def f():\n    from scripts.gerar_dps import main\n    return main\n",
    ],
)
def test_b3_src_importa_de_scripts(codigo):
    assert violacoes({"src/config.py": codigo}) == ["B-3: src.config -> scripts"]


def test_b3_nao_vale_dentro_de_scripts():
    fontes = {"scripts/emitir.py": "from scripts import gerar_dps\nfrom src.dps import Dps\n"}
    assert violacoes(fontes) == []


def test_b3_nome_parecido_com_scripts_passa():
    assert violacoes({"src/config.py": "import scripts_util\nfrom src import scripts_x\n"}) == []


# --- B-5: src/aplicacao/ só depende da biblioteca padrão, do domínio e de si mesma -----


@pytest.mark.parametrize(
    ("codigo", "alvo"),
    [
        ("from lxml import etree\n", "lxml"),
        ("import signxml\n", "signxml"),
        ("from cryptography import x509\n", "cryptography"),
        ("from dotenv import load_dotenv\n", "dotenv"),
        ("from src.client import ClienteNfse\n", "src.client"),
        ("from src import client\n", "src.client"),
        ("from .. import client\n", "src.client"),
        ("from src.assinatura import conferir_assinatura\n", "src.assinatura"),
        ("from src.config import carregar_config\n", "src.config"),
        ("def f():\n    import src.certificado\n", "src.certificado"),
        # Os caminhos de antes da T-043, que esvaziou a lista provisória da B-5.
        ("from src.nfse import NfseEmitida\n", "src.nfse"),
        ("from src.erros import ErroConexao\n", "src.erros"),
        ("from src.dps import NS\n", "src.dps"),
    ],
)
def test_b5_aplicacao_importa_o_que_nao_e_dominio(codigo, alvo):
    assert violacoes({"src/aplicacao/portas.py": codigo}) == [
        f"B-5: src.aplicacao.portas -> {alvo}"
    ]


def test_b5_aplicacao_importa_biblioteca_de_rede():
    assert violacoes({"src/aplicacao/emissao.py": "import httpx\n"}) == [
        "B-2: src.aplicacao.emissao -> httpx",
        "B-5: src.aplicacao.emissao -> httpx",
    ]


def test_b5_aplicacao_importa_de_scripts():
    assert violacoes({"src/aplicacao/emissao.py": "from scripts import gerar_dps\n"}) == [
        "B-3: src.aplicacao.emissao -> scripts",
        "B-5: src.aplicacao.emissao -> scripts",
    ]


def test_b5_init_do_pacote_da_aplicacao_tambem_conta():
    assert violacoes({"src/aplicacao/__init__.py": "import signxml\n"}) == [
        "B-5: src.aplicacao -> signxml"
    ]


@pytest.mark.parametrize(
    "codigo",
    [
        "from __future__ import annotations\nfrom typing import Protocol\n",
        "from dataclasses import dataclass\nfrom pathlib import Path\nimport xml.etree\n",
        "from src.dominio.dps import Dps\nfrom src.dominio import evento\n",
        "from src.aplicacao.portas import SefinEmissao\nfrom . import portas\n",
        "from src.dominio.nfse import NfseEmitida\nfrom src.dominio.erros import ErroConexao\n",
    ],
)
def test_b5_aplicacao_pode_usar_biblioteca_padrao_dominio_e_a_si_mesma(codigo):
    assert violacoes({"src/aplicacao/servico.py": codigo}) == []


def test_b5_so_vale_dentro_de_src_aplicacao():
    fontes = {
        "src/aplicacao_velha.py": "from lxml import etree\n",
        "src/emissao.py": "from lxml import etree\nfrom src.client import ClienteNfse\n",
        "scripts/aplicacao.py": "import signxml\n",
    }
    assert violacoes(fontes) == []


def test_emissao_e_cancelamento_nao_dependem_do_cliente_de_rede():
    # Critério (3) da T-042: os dois usam as portas e o ErroConexao de src/dominio/erros.py.
    deps = dependencias(ler_fontes(RAIZ))
    for modulo in ("src.emissao", "src.cancelamento"):
        assert "src.client" not in deps[modulo], modulo


# --- várias de uma vez -----------------------------------------------------------------


def test_violacoes_saem_ordenadas_e_sem_repeticao():
    fontes = {
        MODELO: "import httpx\nfrom httpx import Client\nimport scripts\n",
        "src/xsd.py": "import socket\n",
    }
    assert violacoes(fontes) == [
        "B-2: src.dominio.dps.modelo -> httpx",
        "B-2: src.xsd -> socket",
        "B-3: src.dominio.dps.modelo -> scripts",
        "B-4: src.dominio.dps.modelo -> httpx",
        "B-4: src.dominio.dps.modelo -> scripts",
    ]
