"""Pastas do programa. Tudo local; nada sai da máquina."""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RAGNAROK_DATA", APP_DIR / "data"))
MODELS_DIR = Path(os.environ.get("RAGNAROK_MODELS", APP_DIR / "models"))
CONFIG_DIR = APP_DIR / "config"
OUTPUT_DIR = DATA_DIR / "outputs"
WORK_DIR = DATA_DIR / "work"
JOBS_DIR = DATA_DIR / "jobs"


def ensure_dirs() -> None:
    for d in (DATA_DIR, MODELS_DIR, OUTPUT_DIR, WORK_DIR, JOBS_DIR):
        d.mkdir(parents=True, exist_ok=True)
