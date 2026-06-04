"""Main entrypoint. Thin wrapper around trading.cli.main for `python main.py ...`."""

import sys
from pathlib import Path

# Ensure src/ is importable without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from trading.cli import main

if __name__ == "__main__":
    main()
