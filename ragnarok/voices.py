"""Catálogo de vozes (config/voices.json)."""
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from .paths import CONFIG_DIR


@dataclass(frozen=True)
class Voice:
    id: str
    label: str
    engine: str          # "kokoro" | "supertonic"
    voice: str           # nome interno no engine
    lang: str            # "pt" | "en"
    speed: float         # velocidade base da voz
    description: str = ""
    kokoro_lang: str = ""

    def public(self) -> dict:
        return {"id": self.id, "label": self.label, "engine": self.engine, "lang": self.lang,
                "base_speed": self.speed, "description": self.description}


@lru_cache(maxsize=1)
def _catalog() -> dict:
    with open(CONFIG_DIR / "voices.json", encoding="utf-8") as f:
        return json.load(f)


def all_voices() -> list:
    out = []
    for v in _catalog()["voices"]:
        out.append(Voice(id=v["id"], label=v["label"], engine=v["engine"], voice=v["voice"],
                         lang=v["lang"], speed=float(v.get("speed", 1.0)),
                         description=v.get("description", ""), kokoro_lang=v.get("kokoro_lang", "")))
    return out


def default_voice_id() -> str:
    return _catalog().get("default_voice", all_voices()[0].id)


def openai_aliases() -> set:
    return set(_catalog().get("openai_aliases", []))


def resolve(name: Optional[str]) -> Voice:
    """Aceita o id exato ou um prefixo único (ex.: 'michael')."""
    voices = all_voices()
    if not name:
        name = default_voice_id()
    n = name.strip().lower()
    for v in voices:
        if v.id == n:
            return v
    cands = [v for v in voices if v.id.startswith(n) or v.id.split("-")[0] == n]
    if len(cands) == 1:
        return cands[0]
    ids = ", ".join(v.id for v in voices)
    if len(cands) > 1:
        raise ValueError(f"Voz ambígua '{name}'. Opções: {ids}")
    raise ValueError(f"Voz desconhecida '{name}'. Opções: {ids}")
