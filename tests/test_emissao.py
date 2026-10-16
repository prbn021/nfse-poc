"""Fluxo de emissão (T-007): consulta antes, nunca reenvia, recupera a nota depois de uma queda.

O cliente aqui é um dublê que registra as chamadas; o HTTP de verdade é testado em
tests/test_client.py.
"""

from functools import partial
from pathlib import Path

import pytest

from src import emissao
from src.assinatura import assinar_dps, conferir_assinatura_do_sistema
from src.certificado import Certificado
from src.config import XSD_DIR_PADRAO
from src.dominio.erros import ErroConexao, MensagemApi, RejeicaoApi, RespostaInesperada
from src.dominio.nfse import NfseEmitida, localizar_xsd_nfse
from src.emissao import DpsJaEmitida, EnvioIncerto
from tests.nfse_ficticia import CHAVE, gerar_nfse
from tests.pfx import chave_de_teste, gerar_certificado

# Com o adaptador de assinatura de verdade, como os scripts o montam (T-043).
emitir = partial(emissao.emitir, conferir_assinatura=conferir_assinatura_do_sistema)

DPS = (Path(__file__).parent / "dados" / "dps-sem-opcionais.xml").read_bytes()
ID_DPS = "DPS330455721122233300018100001000000000000042"


@pytest.fixture(scope="module")
def xsd():
    return localizar_xsd_nfse(XSD_DIR_PADRAO)


@pytest.fixture(scope="module")
def dps_assinada():
    cert = Certificado(certificado=gerar_certificado(), chave=chave_de_teste(), cadeia=())
    return assinar_dps(DPS, cert)


@pytest.fixture(scope="module")
def nfse(dps_assinada):
    return gerar_nfse(dps_assinada)


class Dubl:
    """Cliente falso: cada método devolve ou levanta o que foi configurado, na ordem."""

    def __init__(self, *, chaves=(None,), envio=None, nfse=None):
        self.chaves = list(chaves)
        self.envio = envio
        self.nfse = nfse
        self.chamadas = []

    @staticmethod
    def _resolver(valor):
        if isinstance(valor, Exception):
            raise valor
        return valor

    def chave_da_dps(self, id_dps):
        self.chamadas.append(("chave_da_dps", id_dps))
        return self._resolver(self.chaves.pop(0))

    def emitir(self, xml):
        self.chamadas.append(("emitir", xml))
        return self._resolver(self.envio)

    def obter_nfse(self, chave):
        self.chamadas.append(("obter_nfse", chave))
        return self._resolver(self.nfse)


def _emitida(xml, **over):
    base = dict(chave=CHAVE, id_dps=ID_DPS, xml=xml, alertas=())
    base.update(over)
    return NfseEmitida(**base)


def _nomes(dubl):
    return [nome for nome, _ in dubl.chamadas]


def test_emissao_aceita_consulta_antes_e_envia_uma_vez(dps_assinada, nfse, xsd):
    dubl = Dubl(envio=_emitida(nfse))
    resultado = emitir(dubl, dps_assinada, xsd)
    assert _nomes(dubl) == ["chave_da_dps", "emitir"]
    assert dubl.chamadas[0] == ("chave_da_dps", ID_DPS)
    assert dubl.chamadas[1] == ("emitir", dps_assinada)
    assert resultado.nfse.chave == CHAVE
    assert resultado.problemas == []
    assert resultado.recuperada is False


def test_dps_ja_emitida_nao_e_enviada(dps_assinada, xsd):
    dubl = Dubl(chaves=[CHAVE])
    with pytest.raises(DpsJaEmitida) as erro:
        emitir(dubl, dps_assinada, xsd)
    assert erro.value.chave == CHAVE
    assert "E0014" in str(erro.value)
    assert _nomes(dubl) == ["chave_da_dps"]


def test_rejeicao_passa_adiante_sem_reenviar(dps_assinada, xsd):
    rejeicao = RejeicaoApi(400, ID_DPS, (MensagemApi("E0008", "dhEmi posterior", None),))
    dubl = Dubl(envio=rejeicao)
    with pytest.raises(RejeicaoApi):
        emitir(dubl, dps_assinada, xsd)
    assert _nomes(dubl) == ["chave_da_dps", "emitir"]


def test_queda_depois_do_envio_recupera_a_nota_sem_reenviar(dps_assinada, nfse, xsd):
    dubl = Dubl(chaves=[None, CHAVE], envio=ErroConexao("ReadTimeout: simulado"), nfse=nfse)
    resultado = emitir(dubl, dps_assinada, xsd)
    assert _nomes(dubl) == ["chave_da_dps", "emitir", "chave_da_dps", "obter_nfse"]
    assert resultado.recuperada is True
    assert resultado.nfse.chave == CHAVE
    assert resultado.nfse.xml == nfse
    assert resultado.problemas == []


def test_queda_sem_nota_gerada_diz_que_pode_reenviar(dps_assinada, xsd):
    dubl = Dubl(chaves=[None, None], envio=ErroConexao("ReadTimeout: simulado"))
    with pytest.raises(ErroConexao, match="nenhuma NFS-e foi gerada") as erro:
        emitir(dubl, dps_assinada, xsd)
    assert "pode ser enviada de novo" in str(erro.value)
    assert _nomes(dubl).count("emitir") == 1


def test_queda_e_consulta_que_tambem_falha_e_envio_incerto(dps_assinada, xsd):
    dubl = Dubl(
        chaves=[None, ErroConexao("ConnectError: simulado")],
        envio=ErroConexao("ReadTimeout: simulado"),
    )
    with pytest.raises(EnvioIncerto) as erro:
        emitir(dubl, dps_assinada, xsd)
    assert erro.value.id_dps == ID_DPS
    assert "Não reenvie" in str(erro.value)
    assert _nomes(dubl).count("emitir") == 1


def test_queda_na_consulta_inicial_nao_envia(dps_assinada, xsd):
    dubl = Dubl(chaves=[ErroConexao("ConnectError: simulado")])
    with pytest.raises(ErroConexao):
        emitir(dubl, dps_assinada, xsd)
    assert _nomes(dubl) == ["chave_da_dps"]


@pytest.mark.parametrize(
    "falha",
    [
        RespostaInesperada(201, "chaveAcesso ausente"),
        RespostaInesperada(502, "HTTP 502 não previsto no envio"),
        RejeicaoApi(500, ID_DPS, (MensagemApi("E9999", "falha interna"),)),
    ],
    ids=["201-ilegivel", "502", "500"],
)
def test_resposta_que_pode_esconder_nota_gerada_recupera_a_nota(dps_assinada, nfse, xsd, falha):
    # A nota pode ter sido gerada mesmo com a resposta ilegível ou com erro interno: consulta.
    dubl = Dubl(chaves=[None, CHAVE], envio=falha, nfse=nfse)
    resultado = emitir(dubl, dps_assinada, xsd)
    assert _nomes(dubl) == ["chave_da_dps", "emitir", "chave_da_dps", "obter_nfse"]
    assert resultado.recuperada is True
    assert resultado.nfse.chave == CHAVE
    # A causa da recuperação fica no resultado (DEC-044).
    assert resultado.falha is falha


def test_retorno_sem_id_da_dps_e_aceito_pela_conferencia(dps_assinada, nfse, xsd):
    # Quando a SEFIN devolve o Id da NFS-e em `idDps`, o cliente não tem o Id da DPS (DEC-045);
    # quem confere é a DPS embutida na nota.
    dubl = Dubl(envio=_emitida(nfse, id_dps=None))
    resultado = emitir(dubl, dps_assinada, xsd)
    assert resultado.recuperada is False
    assert resultado.problemas == []
    assert _nomes(dubl) == ["chave_da_dps", "emitir"]


def test_sem_recuperacao_nao_ha_falha(dps_assinada, nfse, xsd):
    resultado = emitir(Dubl(envio=_emitida(nfse)), dps_assinada, xsd)
    assert resultado.falha is None


@pytest.mark.parametrize(
    "falha",
    [
        RespostaInesperada(201, "chaveAcesso ausente"),
        RejeicaoApi(500, ID_DPS, (MensagemApi("E9999", "falha interna"),)),
    ],
    ids=["201-ilegivel", "500"],
)
def test_sem_nota_gerada_o_erro_original_passa_adiante(dps_assinada, xsd, falha):
    dubl = Dubl(chaves=[None, None], envio=falha)
    with pytest.raises(type(falha)) as erro:
        emitir(dubl, dps_assinada, xsd)
    assert erro.value is falha
    assert _nomes(dubl) == ["chave_da_dps", "emitir", "chave_da_dps"]


def test_resposta_ilegivel_e_consulta_que_falha_e_envio_incerto(dps_assinada, xsd):
    dubl = Dubl(
        chaves=[None, ErroConexao("ConnectError: simulado")],
        envio=RespostaInesperada(201, "chaveAcesso ausente"),
    )
    with pytest.raises(EnvioIncerto):
        emitir(dubl, dps_assinada, xsd)


def test_rejeicao_400_nao_consulta_de_novo(dps_assinada, xsd):
    # 400 e 403 são recusas: a nota não foi gerada, não há o que recuperar.
    for status in (400, 403):
        dubl = Dubl(envio=RejeicaoApi(status, ID_DPS, (MensagemApi("E0312", "x"),)))
        with pytest.raises(RejeicaoApi):
            emitir(dubl, dps_assinada, xsd)
        assert _nomes(dubl) == ["chave_da_dps", "emitir"]


def test_id_devolvido_diferente_do_enviado(dps_assinada, nfse, xsd):
    dubl = Dubl(envio=_emitida(nfse, id_dps=ID_DPS[:-1] + "3"))
    with pytest.raises(RespostaInesperada, match="idDps"):
        emitir(dubl, dps_assinada, xsd)


def test_problemas_na_nfse_vem_no_resultado_sem_perder_a_nota(dps_assinada, nfse, xsd):
    alterada = nfse.replace(b"<vLiq>100.00</vLiq>", b"<vLiq>999.00</vLiq>", 1)
    dubl = Dubl(envio=_emitida(alterada))
    resultado = emitir(dubl, dps_assinada, xsd)
    assert resultado.nfse.xml == alterada
    assert resultado.problemas == ["assinatura da NFS-e não confere com o certificado que ela traz"]


@pytest.mark.parametrize("xml", [b"nao e xml", b"<DPS/>"])
def test_dps_sem_id_nao_e_enviada(xml, xsd):
    dubl = Dubl()
    with pytest.raises(ValueError, match="Id"):
        emitir(dubl, xml, xsd)
    assert dubl.chamadas == []


def test_dps_sem_assinatura_nao_e_enviada(xsd):
    dubl = Dubl()
    with pytest.raises(ValueError, match="assinada"):
        emitir(dubl, DPS, xsd)
    assert dubl.chamadas == []
