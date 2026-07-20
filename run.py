"""Lanceur de l'application.

Usage : `python run.py` (ou, après `pip install -e .`, la commande `risk-guard`).
Équivaut à `streamlit run app.py`.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def main() -> None:
    app = pathlib.Path(__file__).resolve().parent / "app.py"
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)]))


if __name__ == "__main__":
    main()
