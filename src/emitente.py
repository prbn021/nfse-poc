"""Dados fixos e certificado de cada emitente, lidos de emitentes/<nome>.toml (T-019, DEC-024).

A pasta emitentes/ fica fora do git, menos o exemplo.toml, que só tem dados fictícios.
Nenhuma mensagem de erro daqui repete valor ou nome de chave vindos do arquivo: a senha do
certificado está nele (INV-05).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from src.config import RAIZ
from src.dps import email_valido, fone_valido

PASTA = RAIZ / "emitentes"
EXEMPLO = "exemplo"

_NOME = re.compile(r"[a-z0-9_-]+")
_LINHA = re.compile(r"\(at line (\d+), column \d+\)$")

# Tabelas do leiaute v1.01 (docs/SPEC.md §6).
_OP_SIMP_NAC = (1, 2, 3)
_REG_ESP_TRIB = (0, 1, 2, 3, 4, 5, 6, 9)
_REG_AP_TRIB_SN = (1, 2, 3)
_ME_EPP = 3

_SECAO = "certificado"
_RAIZ_OBRIGATORIAS = ("cnpj", "municipio", "op_simp_nac", "reg_esp_trib")
# reg_ap_trib_sn: obrigatória para ME/EPP e proibida para os demais (T-010).
_RAIZ_OPCIONAIS = ("inscricao_municipal", "fone", "email", "reg_ap_trib_sn")
_CERTIFICADO = ("caminho", "senha")


@dataclass(frozen=True)
class Emitente:
    nome: str
    cnpj: str
    municipio: str  # código IBGE (7 dígitos)
    inscricao_municipal: str | None
    fone: str | None
    email: str | None
    op_simp_nac: int
    reg_esp_trib: int
    reg_ap_trib_sn: int | None  # só ME/EPP
    cert_path: Path
    cert_senha: str = field(repr=False)


def _texto(valor: object, padrao: str | None = None) -> bool:
    if not isinstance(valor, str) or not valor:
        return False
    return padrao is None or re.fullmatch(padrao, valor) is not None


def _inteiro(valor: object, tabela: tuple[int, ...]) -> bool:
    # bool é subclasse de int: `true` no TOML não vale como número.
    return isinstance(valor, int) and not isinstance(valor, bool) and valor in tabela


def _ler(arquivo: Path) -> dict:
    falha = None
    try:
        dados = tomllib.loads(arquivo.read_bytes().decode("utf-8"))
    except UnicodeDecodeError:
        falha = "não está em UTF-8"
    except tomllib.TOMLDecodeError as erro:
        # A mensagem do tomllib pode trazer trecho do arquivo; só a linha é aproveitada.
        linha = _LINHA.search(str(erro))
        falha = "TOML inválido" + (f" na linha {linha.group(1)}" if linha else "")
    # Levantado fora do `except`, para a exceção original não ficar encadeada.
    if falha:
        raise ValueError(f"{arquivo.name}: {falha}")
    return dados


def carregar_emitente(nome: str, pasta: Path = PASTA) -> Emitente:
    """Lê `<pasta>/<nome>.toml`. Não abre o certificado nem confere se ele existe."""
    if not _NOME.fullmatch(nome):
        raise ValueError(
            f"nome de emitente inválido: {nome!r} (use letras minúsculas, dígitos, '-' e '_')"
        )
    arquivo = pasta / f"{nome}.toml"
    if not arquivo.is_file():
        raise ValueError(
            f"emitente {nome!r} não encontrado: crie {arquivo} a partir de {EXEMPLO}.toml"
        )
    dados = _ler(arquivo)

    aceitas = {*_RAIZ_OBRIGATORIAS, *_RAIZ_OPCIONAIS, _SECAO}
    if dados.keys() - aceitas:
        raise ValueError(
            f"{arquivo.name}: chave desconhecida na raiz; aceitas: {', '.join(sorted(aceitas))}"
        )
    cert = dados.get(_SECAO, {})
    if not isinstance(cert, dict):
        raise ValueError(f"{arquivo.name}: {_SECAO} inválido: esperada a seção [{_SECAO}]")
    if cert.keys() - set(_CERTIFICADO):
        raise ValueError(
            f"{arquivo.name}: chave desconhecida em [{_SECAO}]; "
            f"aceitas: {', '.join(sorted(_CERTIFICADO))}"
        )

    faltam = [c for c in _RAIZ_OBRIGATORIAS if c not in dados]
    if dados.get("op_simp_nac") == _ME_EPP and "reg_ap_trib_sn" not in dados:
        faltam.append("reg_ap_trib_sn")
    faltam += [f"{_SECAO}.{c}" for c in _CERTIFICADO if c not in cert]
    if faltam:
        raise ValueError(f"{arquivo.name}: incompleto, falta: {', '.join(faltam)}")

    inscricao = dados.get("inscricao_municipal")
    reg_ap = dados.get("reg_ap_trib_sn")
    conferencias = (
        ("cnpj", _texto(dados["cnpj"], r"\d{14}"), "14 dígitos, entre aspas"),
        (
            "municipio",
            _texto(dados["municipio"], r"\d{7}"),
            "código IBGE de 7 dígitos, entre aspas",
        ),
        (
            "inscricao_municipal",
            inscricao is None or _texto(inscricao),
            "texto não vazio (ou apague a linha)",
        ),
        (
            "fone",
            "fone" not in dados or fone_valido(dados["fone"]),
            "de 6 a 20 dígitos, entre aspas, sem espaços nem sinais (ou apague a linha)",
        ),
        (
            "email",
            "email" not in dados or email_valido(dados["email"]),
            "e-mail com até 80 caracteres, entre aspas (ou apague a linha)",
        ),
        ("op_simp_nac", _inteiro(dados["op_simp_nac"], _OP_SIMP_NAC), f"um de {_OP_SIMP_NAC}"),
        ("reg_esp_trib", _inteiro(dados["reg_esp_trib"], _REG_ESP_TRIB), f"um de {_REG_ESP_TRIB}"),
        (
            "reg_ap_trib_sn",
            reg_ap is None or _inteiro(reg_ap, _REG_AP_TRIB_SN),
            f"um de {_REG_AP_TRIB_SN}",
        ),
        (f"{_SECAO}.caminho", _texto(cert["caminho"]), "caminho do .pfx, entre aspas"),
        (f"{_SECAO}.senha", isinstance(cert["senha"], str), "texto entre aspas"),
    )
    for chave, valido, esperado in conferencias:
        if not valido:
            raise ValueError(f"{arquivo.name}: {chave} inválido: esperado {esperado}")
    if reg_ap is not None and dados["op_simp_nac"] != _ME_EPP:
        raise ValueError(f"{arquivo.name}: reg_ap_trib_sn só vale para op_simp_nac = {_ME_EPP}")

    return Emitente(
        nome=nome,
        cnpj=dados["cnpj"],
        municipio=dados["municipio"],
        inscricao_municipal=inscricao,
        fone=dados.get("fone"),
        email=dados.get("email"),
        op_simp_nac=dados["op_simp_nac"],
        reg_esp_trib=dados["reg_esp_trib"],
        reg_ap_trib_sn=reg_ap,
        cert_path=RAIZ / cert["caminho"],
        cert_senha=cert["senha"],
    )
