"""`emitir.py --substituir`: substituição de NFS-e em produção restrita (T-031). Sem rede: o
servidor é simulado com `httpx.MockTransport`; certificado autoassinado (DEC-014).
"""

import dataclasses
import sys
from datetime import date
from decimal import Decimal

import httpx
import pytest
from lxml import etree

from src.assinatura import assinar_dps
from src.certificado import Certificado
from src.codec import codificar
from src.config import RAIZ
from src.dps import NS, Tomador, para_xml
from src.emitente import carregar_emitente
from tests.evento_ficticio import CANCELAMENTO, SUBSTITUICAO, gerar_evento
from tests.nfse_ficticia import CHAVE, gerar_nfse
from tests.pfx import chave_de_teste, gerar_certificado
from tests.test_emitir import SENHA, Servidor, config, emitentes  # noqa: F401 (fixture)

sys.path.insert(0, str(RAIZ / "scripts"))

import emitir
from gerar_dps import dps_exemplo

N = {"n": NS}
# A nota nova recebe CHAVE (do Servidor); a substituída é outra nota do mesmo emitente.
CHAVE_SUBST = CHAVE[:23] + "0000000000003" + CHAVE[36:]
CHAVE_DE_OUTRO = CHAVE[:9] + "99888777000161" + CHAVE[23:]
MOTIVO = "Substituicao de teste em producao restrita"
COMPETENCIA = date(2026, 10, 12)
EVENTOS = f"nfse/{CHAVE_SUBST}/eventos/"


def _nfse_original(emitentes, **mudancas) -> bytes:  # noqa: F811
    """A nota substituída: a DPS de exemplo do mesmo emitente, de outra data de competência."""
    emitente = carregar_emitente("acme", emitentes)
    dps = dataclasses.replace(
        dps_exemplo(2, emitente, c_trib_nac="990101"), n_dps=3, d_compet=COMPETENCIA
    )
    dps = dataclasses.replace(dps, **mudancas)
    cert = Certificado(certificado=gerar_certificado(), chave=chave_de_teste(), cadeia=())
    return gerar_nfse(assinar_dps(para_xml(dps), cert), chave=CHAVE_SUBST)


class ServidorSubst(Servidor):
    """Acrescenta a nota substituída e os eventos dela ao Servidor do test_emitir."""

    def __init__(
        self,
        original,
        *,
        nota=None,
        cancelada=False,
        ja_substituida=False,
        evento_depois="certo",
        **kw,
    ):
        super().__init__(**kw)
        self.original = original
        self.nota = nota  # httpx.Response no lugar da nota substituída
        self.cancelada = cancelada
        self.ja_substituida = ja_substituida
        self.evento_depois = evento_depois  # "certo", "ausente" ou "outra"

    def _evento(self, tipo):
        if tipo == CANCELAMENTO:
            if self.cancelada:
                return gerar_evento(chave=CHAVE_SUBST)
            return None
        if self.ja_substituida:
            return gerar_evento(chave=CHAVE_SUBST, tipo=SUBSTITUICAO, ch_substituta=CHAVE)
        if self.dps_recebida is None or self.evento_depois == "ausente":
            return None
        substituta = CHAVE if self.evento_depois == "certo" else CHAVE_DE_OUTRO
        return gerar_evento(chave=CHAVE_SUBST, tipo=SUBSTITUICAO, ch_substituta=substituta)

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        caminho = pedido.url.path.removeprefix("/SefinNacional/")
        if pedido.method == "GET" and caminho == f"nfse/{CHAVE_SUBST}":
            self.pedidos.append((pedido.method, pedido.url.path))
            if self.nota is not None:
                return self.nota
            return httpx.Response(
                200, json={"chaveAcesso": CHAVE_SUBST, "nfseXmlGZipB64": codificar(self.original)}
            )
        if pedido.method == "GET" and caminho.startswith(EVENTOS):
            self.pedidos.append((pedido.method, pedido.url.path))
            tipo = caminho.removeprefix(EVENTOS).split("/")[0]
            evento = self._evento(tipo)
            if evento is None:
                return httpx.Response(404, json={"erro": {"codigo": "E404", "descricao": "não"}})
            return httpx.Response(200, json={"eventoXmlGZipB64": codificar(evento)})
        return super().__call__(pedido)


def rodar(emitentes, tmp_path, servidor, *args, chave=CHAVE_SUBST, ambiente="homologacao"):  # noqa: F811
    argv = ["--emitente", "acme", "--n-dps", "4", "--c-trib-nac", "990101"]
    if chave is not None:
        argv += ["--substituir", chave]
    return emitir.main(
        [*argv, *args],
        pasta=emitentes,
        config=config(ambiente),
        transporte=httpx.MockTransport(servidor),
        saida=tmp_path / "out",
    )


MOTIVO_99 = ("--motivo-subst", "99", "--descricao-subst", MOTIVO)


def _caminhos(servidor):
    return [(m, c.removeprefix("/SefinNacional/")) for m, c in servidor.pedidos]


def test_substitui_copia_a_competencia_e_confere_o_105102(emitentes, tmp_path, capsys):  # noqa: F811
    servidor = ServidorSubst(_nfse_original(emitentes))
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99) == 0
    caminhos = _caminhos(servidor)
    assert caminhos[:3] == [
        ("GET", f"nfse/{CHAVE_SUBST}"),
        ("GET", f"{EVENTOS}101101/1"),
        ("GET", f"{EVENTOS}105102/1"),
    ]
    assert [m for m, _ in caminhos].count("POST") == 1
    assert caminhos[-1] == ("GET", f"{EVENTOS}105102/1")

    inf = etree.fromstring(servidor.dps_recebida).find("n:infDPS", N)
    assert inf.findtext("n:dCompet", namespaces=N) == COMPETENCIA.isoformat()
    subst = inf.find("n:subst", N)
    assert subst.findtext("n:chSubstda", namespaces=N) == CHAVE_SUBST
    assert subst.findtext("n:cMotivo", namespaces=N) == "99"
    assert subst.findtext("n:xMotivo", namespaces=N) == MOTIVO

    evento = tmp_path / "out" / f"Evento{CHAVE_SUBST}-105102-1.xml"
    assert evento.exists()
    out, err = capsys.readouterr()
    assert err == ""
    assert f"Substitui a NFS-e {CHAVE_SUBST}" in out
    assert "[OK] Evento 105102 conferido" in out
    assert SENHA not in out


def test_motivo_sem_descricao_quando_nao_e_99(emitentes, tmp_path):  # noqa: F811
    servidor = ServidorSubst(_nfse_original(emitentes))
    assert rodar(emitentes, tmp_path, servidor, "--motivo-subst", "5") == 0
    subst = etree.fromstring(servidor.dps_recebida).find("n:infDPS/n:subst", N)
    assert subst.findtext("n:cMotivo", namespaces=N) == "05"
    assert subst.find("n:xMotivo", N) is None


def _sem_post(servidor):
    return "POST" not in [m for m, _ in servidor.pedidos]


def test_nota_substituida_inexistente(emitentes, tmp_path, capsys):  # noqa: F811
    nao = httpx.Response(404, json={"erro": {"codigo": "E404", "descricao": "não encontrada"}})
    servidor = ServidorSubst(_nfse_original(emitentes), nota=nao)
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99) == emitir.REJEITADA
    assert _sem_post(servidor)
    assert "nada foi enviado" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("estado", "codigo"), [({"cancelada": True}, "E0046"), ({"ja_substituida": True}, "E0046")]
)
def test_nota_ja_cancelada_ou_substituida(emitentes, tmp_path, capsys, estado, codigo):  # noqa: F811
    servidor = ServidorSubst(_nfse_original(emitentes), **estado)
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99) == 1
    assert _sem_post(servidor)
    assert codigo in capsys.readouterr().err


@pytest.mark.parametrize("campo", ["tomador", "v_serv"])
def test_tomador_ou_valor_diferentes_nao_envia(emitentes, tmp_path, capsys, campo):  # noqa: F811
    exemplo = dps_exemplo(2, carregar_emitente("acme", emitentes), c_trib_nac="990101")
    if campo == "tomador":
        mudanca = {"tomador": Tomador(nome="Cliente de Teste", cpf="98765432100")}
    else:
        mudanca = {"valores": dataclasses.replace(exemplo.valores, v_serv=Decimal("150.00"))}
    servidor = ServidorSubst(_nfse_original(emitentes, **mudanca))
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99) == 1
    assert _sem_post(servidor)
    err = capsys.readouterr().err
    # Anexo I (E0061) e Anexo VI (E0063) numeram a mesma trava de forma diferente (T-037).
    assert "E0061" in err
    assert "E0063" in err


def test_nota_substituida_com_problema_na_conferencia(emitentes, tmp_path, capsys):  # noqa: F811
    original = _nfse_original(emitentes).replace(b"<cStat>100<", b"<cStat>101<", 1)
    servidor = ServidorSubst(original)
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99) == 1
    assert _sem_post(servidor)
    assert "nota substituída" in capsys.readouterr().err


def test_evento_105102_ainda_ausente_e_so_aviso(emitentes, tmp_path, capsys):  # noqa: F811
    servidor = ServidorSubst(_nfse_original(emitentes), evento_depois="ausente")
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99) == 0
    out = capsys.readouterr().out
    assert "[!] Evento 105102 ainda não registrado" in out
    assert "consultar_nfse.py" in out


def test_evento_105102_aponta_outra_nota(emitentes, tmp_path, capsys):  # noqa: F811
    servidor = ServidorSubst(_nfse_original(emitentes), evento_depois="outra")
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99) == emitir.CONFERENCIA_FALHOU
    assert "chSubstituta diferente" in capsys.readouterr().err


def test_chave_de_outro_emitente_nao_faz_pedido(emitentes, tmp_path, capsys):  # noqa: F811
    servidor = ServidorSubst(_nfse_original(emitentes))
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99, chave=CHAVE_DE_OUTRO) == 1
    assert servidor.pedidos == []
    assert "E0042" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("args", "texto"),
    [
        (("--motivo-subst", "99"), "E0078"),
        (("--motivo-subst", "99", "--descricao-subst", "curta"), "x_motivo"),
    ],
)
def test_motivo_invalido_nao_faz_pedido(emitentes, tmp_path, capsys, args, texto):  # noqa: F811
    servidor = ServidorSubst(_nfse_original(emitentes))
    assert rodar(emitentes, tmp_path, servidor, *args) == 1
    assert servidor.pedidos == []
    assert texto in capsys.readouterr().err


@pytest.mark.parametrize(
    "args",
    [
        ("--motivo-subst", "99"),
        ("--descricao-subst", MOTIVO),
        ("--substituir", CHAVE_SUBST),
        ("--substituir", CHAVE_SUBST, "--motivo-subst", "6"),
    ],
)
def test_opcoes_incoerentes(emitentes, tmp_path, args):  # noqa: F811
    with pytest.raises(SystemExit) as saida:
        rodar(emitentes, tmp_path, ServidorSubst(b""), *args, chave=None)
    assert saida.value.code == 2


def test_producao_e_recusada_com_substituicao(emitentes, tmp_path, capsys):  # noqa: F811
    servidor = ServidorSubst(_nfse_original(emitentes))
    assert rodar(emitentes, tmp_path, servidor, *MOTIVO_99, ambiente="producao") == 1
    assert servidor.pedidos == []
    assert "INV-02" in capsys.readouterr().err
