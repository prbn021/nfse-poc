"""Configuração por ambiente. Nada de segredo no código: tudo vem do .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent

# tpAmb do XML da DPS: 1 = produção, 2 = homologação (produção restrita)
TP_AMB = {"producao": 1, "homologacao": 2}


@dataclass(frozen=True)
class Config:
    ambiente: str
    cert_path: Path
    cert_password: str
    sefin_url: str
    adn_url: str
    xsd_dir: Path

    @property
    def tp_amb(self) -> int:
        return TP_AMB[self.ambiente]


def carregar_config() -> Config:
    load_dotenv(RAIZ / ".env")
    ambiente = os.getenv("NFSE_AMBIENTE", "homologacao").strip().lower()
    if ambiente not in TP_AMB:
        raise ValueError(f"NFSE_AMBIENTE inválido: {ambiente!r} (use homologacao ou producao)")
    return Config(
        ambiente=ambiente,
        cert_path=RAIZ / os.getenv("NFSE_CERT_PATH", "certs/certificado.pfx"),
        cert_password=os.getenv("NFSE_CERT_PASSWORD", ""),
        sefin_url=os.getenv("NFSE_SEFIN_URL", "").rstrip("/"),
        adn_url=os.getenv("NFSE_ADN_URL", "").rstrip("/"),
        xsd_dir=RAIZ / os.getenv("NFSE_XSD_DIR", "schemas"),
    )
