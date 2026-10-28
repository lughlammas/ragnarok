"""Render: unidades de texto -> blocos de áudio em disco (com retomada) -> arquivo final."""
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
import soundfile as sf

from . import audio, textproc
from .engines import MANAGER
from .paths import WORK_DIR, ensure_dirs
from .textproc import Book, Unit
from .voices import Voice

FORMAT_VERSION = "1"
GAP_CHAPTER = 2.0       # silêncio entre capítulos (s)
MIN_CPS = 4.0           # abaixo disso (caracteres por segundo de áudio) suspeitamos de anomalia

ProgressCB = Callable[[int, int, float], None]   # (feitos, total, eta_s)


class Cancelled(Exception):
    pass


class DirLock:
    """Trava por pasta de trabalho: impede dois processos gerando o mesmo livro ao mesmo tempo.
    Liberada automaticamente se o processo morrer (flock no Linux/macOS, msvcrt.locking no Windows)."""

    def __init__(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / ".lock"
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise RuntimeError("Este texto já está sendo gerado por outro processo do Ragnarok (mesma voz e velocidade). "
                               "Espere terminar ou feche o outro processo.")
        return self

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()


@dataclass
class Stats:
    chunks: int = 0
    reused: int = 0
    generated: int = 0
    anomalies: int = 0
    retries: int = 0
    gen_seconds: float = 0.0          # tempo só de síntese (neste processo)
    audio_seconds: float = 0.0        # duração total do áudio final
    total_seconds: float = 0.0        # tempo de parede da operação inteira
    chars: int = 0
    sample_rate: int = 0
    chapters: List[Tuple[str, float, float]] = field(default_factory=list)
    peak_ram_mb: float = 0.0
    workdir: str = ""

    @property
    def rtf(self) -> float:
        return self.total_seconds / self.audio_seconds if self.audio_seconds else 0.0


def effective_speed(v: Voice, mult: float) -> float:
    mult = max(0.5, min(2.0, float(mult)))
    return round(v.speed * mult, 4)


def work_key(units: List[Unit], v: Voice, speed: float) -> str:
    h = hashlib.sha1()
    h.update(json.dumps({"fv": FORMAT_VERSION, "voice": v.id, "engine": v.engine, "native": v.voice,
                         "lang": v.lang, "speed": speed, "texts": [u.text for u in units]},
                        ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()[:16]


def _chunk_path(workdir: Path, i: int) -> Path:
    return workdir / f"c{i:05d}.wav"


def _chunk_ok(p: Path) -> bool:
    try:
        return p.exists() and sf.info(str(p)).frames > 0
    except Exception:
        return False


def render_chunks(units: List[Unit], v: Voice, speed: float, workdir: Path,
                  progress: Optional[ProgressCB] = None,
                  cancel: Optional[Callable[[], bool]] = None, stats: Optional[Stats] = None) -> Stats:
    st = stats or Stats()
    workdir.mkdir(parents=True, exist_ok=True)
    st.workdir = str(workdir)
    st.chunks = len(units)
    st.chars = sum(len(u.text) for u in units)
    done_chars = 0
    t_gen_chars = 0
    t0 = time.time()
    for i, u in enumerate(units):
        if cancel and cancel():
            raise Cancelled()
        p = _chunk_path(workdir, i)
        if _chunk_ok(p):
            st.reused += 1
            done_chars += len(u.text)
        else:
            ts = time.time()
            wav, sr = MANAGER.synth(u.text, v, speed)
            dur = len(wav) / sr if sr else 0
            if dur > len(u.text) / MIN_CPS + 2.0 or len(wav) == 0:      # trava contra anomalia (áudio longo demais/vazio)
                st.retries += 1
                wav2, sr2 = MANAGER.synth(u.text, v, speed)
                if 0 < len(wav2) / sr2 < dur or len(wav) == 0:
                    wav, sr, dur = wav2, sr2, len(wav2) / sr2
                if dur > len(u.text) / MIN_CPS + 2.0 or len(wav) == 0:
                    st.anomalies += 1
            tmp = p.with_name(p.name + ".tmp")
            sf.write(str(tmp), wav, sr, subtype="PCM_16", format="WAV")
            os.replace(tmp, p)
            el = time.time() - ts
            st.gen_seconds += el
            st.generated += 1
            done_chars += len(u.text)
            t_gen_chars += len(u.text)
        remaining = max(0, st.chars - done_chars)
        eta = (st.gen_seconds / t_gen_chars * remaining) if t_gen_chars else 0.0
        if progress:
            progress(i + 1, len(units), eta)
    st.total_seconds = time.time() - t0
    return st


def assemble(units: List[Unit], book: Book, starts: List[int], workdir: Path, wav_out: Path,
             stats: Stats) -> None:
    """Junta blocos + pausas num WAV PCM16 por streaming (RAM baixa)."""
    first = sf.info(str(_chunk_path(workdir, 0)))
    sr = first.samplerate
    stats.sample_rate = sr

    def silence(f, sec):
        n = int(sr * sec)
        if n > 0:
            f.write(np.zeros(n, dtype=np.int16))

    total = 0.0
    chapters: List[Tuple[str, float, float]] = []
    with sf.SoundFile(str(wav_out), "w", samplerate=sr, channels=1, subtype="PCM_16", format="WAV") as out:
        ch_start = 0.0
        cur_ch = units[0].chapter if units else 0
        for i, u in enumerate(units):
            if u.chapter != cur_ch:                    # novo capítulo
                chapters.append((book.chapters[cur_ch].title, ch_start, total))
                silence(out, GAP_CHAPTER); total += GAP_CHAPTER
                cur_ch, ch_start = u.chapter, total
            data, csr = sf.read(str(_chunk_path(workdir, i)), dtype="int16")
            if csr != sr:
                raise RuntimeError("Taxas de amostragem diferentes entre blocos (não esperado).")
            out.write(data); total += len(data) / sr
            silence(out, u.pause); total += u.pause
        chapters.append((book.chapters[cur_ch].title, ch_start, total))
    stats.audio_seconds = total
    stats.chapters = chapters


def render_book(book: Book, v: Voice, speed_mult: float, out_path: Path, fmt: Optional[str] = None,
                announce_titles: bool = True, progress: Optional[ProgressCB] = None,
                cancel: Optional[Callable[[], bool]] = None, persistent: bool = True,
                keep_work: bool = False, author: str = "") -> Stats:
    ensure_dirs()
    fmt = (fmt or out_path.suffix.lstrip(".") or "wav").lower()
    units, starts = textproc.book_to_units(book, announce_titles)
    if not units:
        raise ValueError("Não há texto legível para sintetizar.")
    speed = effective_speed(v, speed_mult)
    key = work_key(units, v, speed)
    workdir = (WORK_DIR / key) if persistent else Path(tempfile.mkdtemp(prefix="say-", dir=WORK_DIR))
    try:
        with MANAGER.job_lock, DirLock(workdir):
            t0 = time.time()
            stats = render_chunks(units, v, speed, workdir, progress, cancel)
            wav_out = workdir / "final.wav"
            assemble(units, book, starts, workdir, wav_out, stats)
            chapters = stats.chapters if len(book.chapters) > 1 or announce_titles else None
            audio.encode(wav_out, out_path, fmt, chapters=chapters, title=book.title, author=author or book.author)
            stats.total_seconds = time.time() - t0
            stats.peak_ram_mb = audio.peak_rss_mb()
    except BaseException:
        if not persistent:
            shutil.rmtree(workdir, ignore_errors=True)    # 'say' não retoma: não deixa lixo
        raise
    if not keep_work:
        shutil.rmtree(workdir, ignore_errors=True)
    return stats


def say_text(text: str, v: Voice, speed_mult: float, out_path: Path, fmt: Optional[str] = None,
             progress: Optional[ProgressCB] = None, cancel: Optional[Callable[[], bool]] = None) -> Stats:
    """Texto simples (sem capítulos, sem títulos falados)."""
    book = textproc.parse_markdown(text, default_title="Ragnarok")
    # para 'say' qualquer cabeçalho vira só texto: um único capítulo sem anúncio de título
    merged = textproc.Chapter(title="", paras=[], implicit=True)
    for ch in book.chapters:
        if ch.title and not ch.implicit:
            merged.paras.append(textproc.Para(ch.title, "sub"))
        merged.paras.extend(ch.paras)
    book.chapters = [merged]
    return render_book(book, v, speed_mult, out_path, fmt, announce_titles=False, progress=progress,
                       cancel=cancel, persistent=False)
