"""O ambiente em uso precisa bater com os pins do repositório (T-002)."""
import platform
import re
from importlib import metadata

from packaging.requirements import Requirement

from src.config import RAIZ


import pytest

# (entrada com as dependências diretas, lock gerado pelo pip-compile)
PARES = [("requirements.in", "requirements.txt"), ("requirements-dev.in", "requirements-dev.txt")]


def _requisitos(arquivo: str) -> list[Requirement]:
    reqs = []
    for linha in (RAIZ / arquivo).read_text(encoding="utf-8").splitlines():
        if not linha or linha[0] in " #-":
            continue
        reqs.append(Requirement(linha.rstrip(" \\")))
    return reqs


def _nome(req: Requirement) -> str:
    return re.sub(r"[-_.]+", "-", req.name).lower()


@pytest.mark.parametrize("entrada, lock", PARES)
def test_lock_tem_versao_exata_e_hash_para_cada_pacote(entrada, lock):
    texto = (RAIZ / lock).read_text(encoding="utf-8")
    travados = _requisitos(lock)
    assert travados
    for req in travados:
        assert re.fullmatch(r"==[^,*]+", str(req.specifier)), req
    assert texto.count("--hash=sha256:") >= len(travados)


@pytest.mark.parametrize("entrada, lock", PARES)
def test_dependencias_diretas_estao_no_lock_com_a_mesma_versao(entrada, lock):
    travados = {_nome(r): str(r.specifier) for r in _requisitos(lock)}
    diretos = _requisitos(entrada)
    assert diretos
    for req in diretos:
        assert travados.get(_nome(req)) == str(req.specifier), req


@pytest.mark.parametrize("entrada, lock", PARES)
def test_ambiente_instalado_bate_com_o_lock(entrada, lock):
    for req in _requisitos(lock):
        if req.marker is not None and not req.marker.evaluate():
            continue
        assert f"=={metadata.version(req.name)}" == str(req.specifier), req


def test_python_em_uso_e_o_da_versao_fixada():
    fixada = (RAIZ / ".python-version").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", fixada)
    assert platform.python_version_tuple()[:2] == tuple(fixada.split(".")[:2])
