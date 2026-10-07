"""Gera a cópia local dos XSDs oficiais (schemas/1.01 -> schemas/1.01-local), sem ^ e $ nos padrões."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import carregar_config
from src.xsd import preparar_copia_local


def main() -> int:
    cfg = carregar_config()
    destino = preparar_copia_local(cfg.xsd_dir)
    print(f"cópia gerada em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
