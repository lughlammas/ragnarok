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
    if os.name == "nt":
        # espeakng-loader copies its DLL through tempfile.mkdtemp(). Some managed
        # Windows environments deny writes to the system Temp path, so keep the
        # short lived DLL and audio files inside Ragnarok's writable data folder.
        temp_dir = DATA_DIR / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        import tempfile
        tempfile.tempdir = str(temp_dir)
