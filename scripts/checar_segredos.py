"""Gate G-4 (INV-03): falha se o git rastrear o que não pode ser versionado.

Isto é: .env, certificado (.pfx, .p12, .pem) ou arquivo de docs/referencia fora de gov-docs.
"""

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.segredos import proibidos


def main() -> int:
    saida = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607 (o git vem do PATH de quem roda o gate)
        cwd=RAIZ,
        capture_output=True,
        check=True,
    ).stdout
    rastreados = [c for c in saida.decode("utf-8").split("\0") if c]
    achados = proibidos(rastreados)
    if achados:
        print("[X] Arquivo que não pode ser versionado (INV-03, T-017):")
        for a in achados:
            print("   -", a)
        return 1
    print(
        "[OK] Nenhum .env, certificado ou referência privada "
        f"entre os {len(rastreados)} arquivos rastreados"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
