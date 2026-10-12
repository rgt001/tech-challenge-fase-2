"""Caminhos resolvidos pelo projeto, sem depender do diretório do terminal."""
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("TC2_DATA_ROOT", PROJECT_ROOT / "data"))
OUTPUT_ROOT = Path(os.getenv("TC2_OUTPUT_ROOT", PROJECT_ROOT / "outputs"))


def relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name
