"""Download e verificação dos modelos (único acesso à internet do programa: só no install)."""
import hashlib
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

from .engines import KOKORO_DIR, KOKORO_MODEL, KOKORO_VOICES, SUPERTONIC_DIR

KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
# SHA-256 fixados na 1ª baixada (27/10/2026). Não há hash oficial publicado para cruzar: protege contra
# corrupção/alteração POSTERIOR, não prova a origem.
KOKORO_FILES = {
    "kokoro-v1.0.onnx": ("7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5", 325532387),
    "voices-v1.0.bin": ("bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d", 28214398),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _download(url: str, dest: Path, size: int) -> None:
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "ragnarok-installer/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        got, t0, last = 0, time.time(), 0
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b); got += len(b)
            if time.time() - last > 1:
                last = time.time()
                print(f"\r  {dest.name}: {got / 1e6:6.1f} / {size / 1e6:.1f} MB", end="", flush=True)
    print(f"\r  {dest.name}: {got / 1e6:6.1f} / {size / 1e6:.1f} MB  ok")
    os.replace(tmp, dest)


def ensure_kokoro(verify: bool = True) -> None:
    KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    for name, (digest, size) in KOKORO_FILES.items():
        dest = KOKORO_DIR / name
        if dest.exists() and dest.stat().st_size == size and (not verify or sha256(dest) == digest):
            print(f"  {name}: já existe e confere")
            continue
        for attempt in (1, 2, 3):
            try:
                _download(KOKORO_BASE + name, dest, size)
                if sha256(dest) != digest:
                    dest.unlink(missing_ok=True)
                    raise RuntimeError(f"SHA-256 de {name} não confere")
                break
            except Exception as e:
                print(f"\n  tentativa {attempt} falhou: {e}")
                if attempt == 3:
                    raise
                time.sleep(3)


def ensure_supertonic() -> None:
    SUPERTONIC_DIR.mkdir(parents=True, exist_ok=True)
    if (SUPERTONIC_DIR / "onnx").exists() and (SUPERTONIC_DIR / "voice_styles" / "M5.json").exists():
        print("  Supertonic-3: já existe")
        return
    from supertonic import TTS
    print("  Supertonic-3: baixando do Hugging Face (~400 MB)...")
    TTS(model_dir=str(SUPERTONIC_DIR), auto_download=True)


def ensure_all(kokoro_only: bool = False) -> None:
    print("Kokoro (fp32):")
    ensure_kokoro()
    if kokoro_only:
        print("Kokoro pronto (Supertonic não instalado).")
        return
    print("Supertonic-3:")
    ensure_supertonic()
    print("Modelos prontos.")


def status() -> dict:
    return {
        "kokoro": KOKORO_MODEL.exists() and KOKORO_VOICES.exists(),
        "supertonic": (SUPERTONIC_DIR / "onnx").exists(),
    }
