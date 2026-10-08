"""Falha se o git rastrear .env ou certificado (.pfx, .p12, .pem). Gate G-4, INV-03."""
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.segredos import proibidos


def main() -> int:
    saida = subprocess.run(["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, check=True).stdout
    rastreados = [c for c in saida.decode("utf-8").split("\0") if c]
    achados = proibidos(rastreados)
    if achados:
        print("[X] Segredo rastreado pelo git (INV-03):")
        for a in achados:
            print("   -", a)
        return 1
    print(f"[OK] Nenhum .env ou certificado entre os {len(rastreados)} arquivos rastreados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
