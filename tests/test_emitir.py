"""Script manual de emissão em produção restrita (T-007). Sem rede: o servidor é simulado com
`httpx.MockTransport`, e o certificado é o autoassinado de tests/pfx.py (DEC-014).
"""

import json
import sys

import httpx
import pytest
from lxml import etree

from src.codec import codificar, decodificar
from src.config import RAIZ, Config
from src.dps import NS
from tests.nfse_ficticia import CHAVE, gerar_nfse
from tests.pfx import CNPJ, gerar_pfx

sys.path.insert(0, str(RAIZ / "scripts"))

import emitir

SENHA = "s3nh4-f1ct1c14-emt"
BASE = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"
N = {"n": NS}


def config(ambiente="homologacao") -> Config:
    return Config(
        ambiente=ambiente,
        sefin_url=BASE,
        adn_url="https://adn.producaorestrita.nfse.gov.br",
        xsd_dir=RAIZ / "schemas" / "1.01",
    )


@pytest.fixture
def emitentes(tmp_path):
    pasta = tmp_path / "emitentes"
    pasta.mkdir()
    (pasta / "acme.pfx").write_bytes(gerar_pfx(SENHA))
    (pasta / "acme.toml").write_text(
        f'cnpj = "{CNPJ}"\nmunicipio = "3304557"\nop_simp_nac = 3\n'
        "reg_ap_trib_sn = 1\nreg_esp_trib = 0\n\n"
        f'[certificado]\ncaminho = "{(pasta / "acme").as_posix()}.pfx"\nsenha = "{SENHA}"\n',
        encoding="utf-8",
    )
    return pasta


class Servidor:
    """SEFIN simulada: responde `GET /dps/{id}` e `POST /nfse` conforme configurado."""

    def __init__(
        self, *, ja_emitida=False, post=None, depois_da_queda=None, pascal=False, id_da_nfse=False
    ):
        self.ja_emitida = ja_emitida
        self.pascal = pascal  # sucesso com as chaves em PascalCase, como os erros reais
        self.id_da_nfse = id_da_nfse  # `idDps` com "NFS" + chave, como o 201 real
        self.post = post  # None: aceita; httpx.Response: devolve; Exception: levanta
        self.depois_da_queda = depois_da_queda
        self.pedidos = []
        self.dps_recebida = None
        self.nfse_devolvida = None

    def _nfse(self) -> str:
        # Gerada uma vez: o certificado de teste muda a cada chamada de gerar_nfse.
        if self.nfse_devolvida is None:
            self.nfse_devolvida = gerar_nfse(self.dps_recebida)
        return codificar(self.nfse_devolvida)

    def _sucesso(self, id_dps: str) -> dict:
        return {
            "tipoAmbiente": 2,
            "versaoAplicativo": "Ficticio_1.0",
            "dataHoraProcessamento": "2026-10-12T10:00:00-03:00",
            "idDps": f"NFS{CHAVE}" if self.id_da_nfse else id_dps,
            "chaveAcesso": CHAVE,
            "nfseXmlGZipB64": self._nfse(),
            "alertas": [],
        }

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append((pedido.method, pedido.url.path))
        caminho = pedido.url.path.removeprefix("/SefinNacional/")
        if pedido.method == "GET" and caminho.startswith("dps/"):
            if self.ja_emitida or (self.dps_recebida is not None and self.depois_da_queda):
                return httpx.Response(200, json={"chaveAcesso": CHAVE, "idDps": caminho[4:]})
            return httpx.Response(404, json={"erro": {"codigo": "E404", "descricao": "não há"}})
        if pedido.method == "GET" and caminho == f"nfse/{CHAVE}":
            return httpx.Response(200, json={"chaveAcesso": CHAVE, "nfseXmlGZipB64": self._nfse()})
        if pedido.method == "POST" and caminho == "nfse":
            self.dps_recebida = decodificar(json.loads(pedido.content)["dpsXmlGZipB64"])
            if isinstance(self.post, Exception):
                raise self.post
            if self.post is not None:
                return self.post
            id_dps = etree.fromstring(self.dps_recebida).find("n:infDPS", N).get("Id")
            corpo = self._sucesso(id_dps)
            if self.pascal:
                corpo = {chave[0].upper() + chave[1:]: valor for chave, valor in corpo.items()}
            return httpx.Response(201, json=corpo)
        return httpx.Response(404)


def rodar(emitentes, tmp_path, servidor, *args, ambiente="homologacao", c_trib_nac="990101"):
    # 990101: código fictício, só para os testes.
    argv = ["--emitente", "acme", "--n-dps", "7", "--c-trib-nac", c_trib_nac, *args]
    return emitir.main(
        argv,
        pasta=emitentes,
        config=config(ambiente),
        transporte=httpx.MockTransport(servidor),
        saida=tmp_path / "out",
    )


def test_emissao_aceita_salva_a_nfse_e_mostra_a_chave(emitentes, tmp_path, capsys):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor) == 0
    assert [m for m, _ in servidor.pedidos] == ["GET", "POST"]

    out, err = capsys.readouterr()
    assert err == ""
    assert f"Chave de acesso: {CHAVE}" in out
    assert "[OK] NFS-e conferida" in out
    assert SENHA not in out
    assert "PRIVATE KEY" not in out

    saida = tmp_path / "out"
    assert (saida / f"NFSe{CHAVE}.xml").read_bytes() == servidor.nfse_devolvida
    [enviada] = saida.glob("DPS*-enviada.xml")
    assert enviada.read_bytes() == servidor.dps_recebida


def test_sucesso_em_pascalcase_tambem_e_lido(emitentes, tmp_path, capsys):
    servidor = Servidor(pascal=True)
    assert rodar(emitentes, tmp_path, servidor) == 0
    assert [m for m, _ in servidor.pedidos] == ["GET", "POST"]
    assert f"Chave de acesso: {CHAVE}" in capsys.readouterr().out
    assert (tmp_path / "out" / f"NFSe{CHAVE}.xml").read_bytes() == servidor.nfse_devolvida


def test_dps_enviada_tem_o_numero_pedido_sem_ctribmun_e_assinada(emitentes, tmp_path):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, "--serie", "3") == 0
    raiz = etree.fromstring(servidor.dps_recebida)
    inf = raiz.find("n:infDPS", N)
    assert inf.findtext("n:nDPS", namespaces=N) == "7"
    assert inf.findtext("n:serie", namespaces=N) == "3"
    assert inf.findtext("n:tpAmb", namespaces=N) == "2"
    assert inf.find("n:serv/n:cServ/n:cTribMun", N) is None
    assert inf.get("Id").endswith("00003000000000000007")
    assert raiz.find("{http://www.w3.org/2000/09/xmldsig#}Signature") is not None


def test_codigo_de_tributacao_nacional_vem_do_argumento(emitentes, tmp_path):
    # Fictício para o teste; na emissão real, o código do serviço do emitente (DEC-038).
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, c_trib_nac="990102") == 0
    inf = etree.fromstring(servidor.dps_recebida).find("n:infDPS", N)
    assert inf.findtext("n:serv/n:cServ/n:cTribNac", namespaces=N) == "990102"


def test_sem_o_codigo_de_tributacao_nao_envia(emitentes, tmp_path, capsys):
    # O código do exemplo foi recusado pela SEFIN (E0312): sem o argumento, nada é enviado.
    servidor = Servidor()
    with pytest.raises(SystemExit) as saida:
        emitir.main(
            ["--emitente", "acme", "--n-dps", "7"],
            pasta=emitentes,
            config=config(),
            transporte=httpx.MockTransport(servidor),
            saida=tmp_path / "out",
        )
    assert saida.value.code == 2
    assert servidor.pedidos == []
    assert "--c-trib-nac" in capsys.readouterr().err


@pytest.mark.parametrize("codigo", ["12", "abcdef", "1234567"])
def test_codigo_de_tributacao_invalido_nao_envia(emitentes, tmp_path, capsys, codigo):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, c_trib_nac=codigo) == 1
    assert servidor.pedidos == []
    assert "c_trib_nac" in capsys.readouterr().err


def test_codigo_municipal_vem_do_argumento(emitentes, tmp_path):
    # O município parametriza o serviço com desdobramento próprio, o cTribMun (DEC-043).
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, "--c-trib-mun", "009") == 0
    inf = etree.fromstring(servidor.dps_recebida).find("n:infDPS", N)
    assert inf.findtext("n:serv/n:cServ/n:cTribMun", namespaces=N) == "009"
    assert inf.findtext("n:serv/n:cServ/n:cTribNac", namespaces=N) == "990101"


@pytest.mark.parametrize("codigo", ["1", "0001", "abc"])
def test_codigo_municipal_invalido_nao_envia(emitentes, tmp_path, capsys, codigo):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, "--c-trib-mun", codigo) == 1
    assert servidor.pedidos == []
    assert "c_trib_mun" in capsys.readouterr().err


def test_rejeicao_mostra_os_codigos_e_nao_salva_nfse(emitentes, tmp_path, capsys):
    resposta = httpx.Response(
        400,
        json={
            "idDPS": "x",
            "erros": [
                {"codigo": "E0314", "descricao": "cTribMun inexistente", "complemento": None}
            ],
        },
    )
    assert rodar(emitentes, tmp_path, Servidor(post=resposta)) == emitir.REJEITADA
    err = capsys.readouterr().err
    assert "HTTP 400" in err
    assert "E0314: cTribMun inexistente" in err
    assert not list((tmp_path / "out").glob("NFSe*.xml"))
    # A resposta bruta fica em out/ para diagnóstico (DEC-037).
    [salva] = (tmp_path / "out").glob("DPS*-resposta-400-*.json")
    assert salva.read_bytes() == resposta.content
    assert f"Resposta completa da SEFIN: {salva}" in err


def test_resposta_inesperada_tambem_e_salva(emitentes, tmp_path, capsys):
    resposta = httpx.Response(502, content=b"Bad Gateway")
    assert rodar(emitentes, tmp_path, Servidor(post=resposta)) == emitir.RESPOSTA_INESPERADA
    [salva] = (tmp_path / "out").glob("DPS*-resposta-502-*.json")
    assert salva.read_bytes() == b"Bad Gateway"
    assert "Bad Gateway" not in capsys.readouterr().err


def test_dps_ja_emitida_nao_e_enviada(emitentes, tmp_path, capsys):
    servidor = Servidor(ja_emitida=True)
    assert rodar(emitentes, tmp_path, servidor) == emitir.JA_EMITIDA
    assert [m for m, _ in servidor.pedidos] == ["GET"]
    assert "E0014" in capsys.readouterr().err


def test_queda_depois_do_envio_recupera_a_nota(emitentes, tmp_path, capsys):
    servidor = Servidor(post=httpx.ReadTimeout("simulado"), depois_da_queda=True)
    assert rodar(emitentes, tmp_path, servidor) == 0
    assert [m for m, _ in servidor.pedidos] == ["GET", "POST", "GET", "GET"]
    out = capsys.readouterr().out
    assert "recuperada" in out
    assert "a conexão caiu no envio (ReadTimeout: simulado)" in out
    assert (tmp_path / "out" / f"NFSe{CHAVE}.xml").exists()


def test_201_real_com_id_da_nfse_e_lido_direto(emitentes, tmp_path, capsys):
    # Formato da resposta real (2026-10-12): `idDps` traz "NFS" + chave (DEC-045).
    servidor = Servidor(id_da_nfse=True)
    assert rodar(emitentes, tmp_path, servidor) == 0
    assert [m for m, _ in servidor.pedidos] == ["GET", "POST"]
    out = capsys.readouterr().out
    assert "recuperada" not in out
    assert "[OK] NFS-e conferida" in out


def test_201_ilegivel_diz_a_causa_e_salva_a_resposta(emitentes, tmp_path, capsys):
    # A primeira nota real veio pela recuperação sem dizer a causa (DEC-044).
    resposta = httpx.Response(201, json={"Outro": "formato"})
    servidor = Servidor(post=resposta, depois_da_queda=True)
    assert rodar(emitentes, tmp_path, servidor) == 0
    captura = capsys.readouterr()
    assert "a resposta do envio veio fora do formato esperado (HTTP 201" in captura.out
    assert "chaveAcesso" in captura.out
    [salva] = (tmp_path / "out").glob("DPS*-resposta-201-*.json")
    assert salva.read_bytes() == resposta.content
    assert (tmp_path / "out" / f"NFSe{CHAVE}.xml").exists()


def test_500_com_nota_gerada_diz_a_causa(emitentes, tmp_path, capsys):
    resposta = httpx.Response(500, json={"erros": [{"Codigo": "X1", "Descricao": "falha"}]})
    servidor = Servidor(post=resposta, depois_da_queda=True)
    assert rodar(emitentes, tmp_path, servidor) == 0
    assert "a SEFIN respondeu com erro (HTTP 500: X1: falha)" in capsys.readouterr().out
    assert list((tmp_path / "out").glob("DPS*-resposta-500-*.json"))


def test_queda_sem_nota_gerada(emitentes, tmp_path, capsys):
    servidor = Servidor(post=httpx.ReadTimeout("simulado"), depois_da_queda=False)
    assert rodar(emitentes, tmp_path, servidor) == emitir.ERRO_DE_REDE
    assert [m for m, _ in servidor.pedidos].count("POST") == 1
    assert "pode ser enviada de novo" in capsys.readouterr().err


def test_producao_e_recusada_antes_de_qualquer_chamada(emitentes, tmp_path, capsys):
    servidor = Servidor()
    assert rodar(emitentes, tmp_path, servidor, ambiente="producao") == 1
    assert servidor.pedidos == []
    assert "INV-02" in capsys.readouterr().err


def test_numero_invalido_nao_envia(emitentes, tmp_path, capsys):
    servidor = Servidor()
    argv = ["--emitente", "acme", "--n-dps", "0", "--c-trib-nac", "990101"]
    codigo = emitir.main(
        argv,
        pasta=emitentes,
        config=config(),
        transporte=httpx.MockTransport(servidor),
        saida=tmp_path / "out",
    )
    assert codigo == 1
    assert servidor.pedidos == []
    assert "n_dps" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--emitente", "acme", "--c-trib-nac", "990101"],
        ["--n-dps", "1", "--c-trib-nac", "990101"],
        ["--emitente", "acme", "--n-dps", "1"],
    ],
)
def test_emitente_numero_e_codigo_sao_obrigatorios(argv, capsys):
    with pytest.raises(SystemExit) as saida:
        emitir.main(argv)
    assert saida.value.code == 2
