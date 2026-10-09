"""Abre o certificado A1 de um emitente e mostra só titular, CNPJ e validade (T-004).

Script manual: é o único jeito de abrir um certificado real fora dos testes (DEC-014).
Não mostra senha, chave nem outro conteúdo do certificado (INV-05).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.certificado import carregar_certificado
from src.emitente import PASTA, carregar_emitente

FORMATO = "%Y-%m-%d %H:%M:%S UTC"


def main(argv: list[str] | None = None, pasta: Path = PASTA) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--emitente", required=True, help="nome do arquivo em emitentes/, sem .toml"
    )
    args = parser.parse_args(argv)
    try:
        emitente = carregar_emitente(args.emitente, pasta)
        cert = carregar_certificado(emitente.cert_path, emitente.cert_senha)
    except ValueError as erro:
        print(f"[X] {erro}", file=sys.stderr)
        return 1

    print(f"Titular:  {cert.titular}")
    print(f"CNPJ:     {cert.cnpj or 'não encontrado no certificado'}")
    print(
        f"Validade: de {cert.valido_de.strftime(FORMATO)} até {cert.valido_ate.strftime(FORMATO)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
