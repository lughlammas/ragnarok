"""Engines TTS. Só UM fica carregado por vez (troca descarrega o anterior)."""
import gc
import threading
from typing import Tuple

import numpy as np

from .paths import MODELS_DIR
from .voices import Voice

KOKORO_DIR = MODELS_DIR / "kokoro"
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.onnx"       # SEMPRE fp32 (o int8 do pm_alex deu anomalia)
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"
SUPERTONIC_DIR = MODELS_DIR / "supertonic-3"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class KokoroEngine:
    name = "kokoro"

    def __init__(self):
        if not KOKORO_MODEL.exists() or not KOKORO_VOICES.exists():
            raise RuntimeError("Modelo Kokoro não encontrado. Rode: ragnarok models (ou install.ps1 / install.sh).")
        from kokoro_onnx import Kokoro
        self.k = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))

    def synth(self, text: str, v: Voice, speed: float) -> Tuple[np.ndarray, int]:
        a, sr = self.k.create(text, voice=v.voice, speed=_clamp(speed, 0.5, 2.0), lang=v.kokoro_lang or "en-us")
        return np.asarray(a, dtype=np.float32).reshape(-1), int(sr)

    def close(self):
        self.k = None


class SupertonicEngine:
    name = "supertonic"

    def __init__(self):
        if not (SUPERTONIC_DIR / "onnx").exists():
            raise RuntimeError("Modelo Supertonic-3 não encontrado. Rode: ragnarok models (ou install.ps1 / install.sh).")
        from supertonic import TTS
        self.tts = TTS(model_dir=str(SUPERTONIC_DIR), auto_download=False)
        self._styles = {}

    def synth(self, text: str, v: Voice, speed: float) -> Tuple[np.ndarray, int]:
        st = self._styles.get(v.voice)
        if st is None:
            st = self._styles[v.voice] = self.tts.get_voice_style(voice_name=v.voice)
        wav, _dur = self.tts.synthesize(text, voice_style=st, lang=v.lang, speed=_clamp(speed, 0.7, 2.0))
        return np.asarray(wav, dtype=np.float32).reshape(-1), int(self.tts.sample_rate)

    def close(self):
        self.tts = None
        self._styles = {}


_ENGINES = {"kokoro": KokoroEngine, "supertonic": SupertonicEngine}


class EngineManager:
    """Carrega um engine por vez e serializa o uso (um texto por vez)."""

    def __init__(self):
        self.lock = threading.RLock()
        self.job_lock = threading.RLock()   # um trabalho inteiro por vez (evita trocar de engine a cada bloco)
        self.current = None

    @property
    def loaded(self) -> str:
        return self.current.name if self.current else ""

    def _ensure(self, engine: str):
        if self.current is not None and self.current.name == engine:
            return self.current
        if self.current is not None:
            self.current.close()
            self.current = None
            gc.collect()
        self.current = _ENGINES[engine]()
        return self.current

    def unload(self):
        with self.lock:
            if self.current is not None:
                self.current.close()
                self.current = None
                gc.collect()

    def synth(self, text: str, v: Voice, speed: float) -> Tuple[np.ndarray, int]:
        with self.lock:
            eng = self._ensure(v.engine)
            return eng.synth(text, v, speed)


MANAGER = EngineManager()
