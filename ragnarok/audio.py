"""ffmpeg, silêncio, codificação e medição de RAM."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

FORMATS = {
    # ext: (ffmpeg args de codec, media type)
    "wav": (None, "audio/wav"),
    "mp3": (["-c:a", "libmp3lame", "-q:a", "4"], "audio/mpeg"),
    "m4b": (["-c:a", "aac", "-b:a", "64k", "-f", "ipod"], "audio/mp4"),
    "m4a": (["-c:a", "aac", "-b:a", "96k", "-f", "ipod"], "audio/mp4"),
    "ogg": (["-c:a", "libvorbis", "-q:a", "3", "-f", "ogg"], "audio/ogg"),
    "opus": (["-c:a", "libopus", "-b:a", "48k", "-f", "ogg"], "audio/ogg"),
    "flac": (["-c:a", "flac", "-f", "flac"], "audio/flac"),
    "aac": (["-c:a", "aac", "-b:a", "96k", "-f", "adts"], "audio/aac"),
}


def ffmpeg_exe() -> str:
    env = os.environ.get("RAGNAROK_FFMPEG")
    if env:
        return env
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    p = shutil.which("ffmpeg")
    if p:
        return p
    raise RuntimeError("ffmpeg não encontrado. Rode install.ps1 / install.sh de novo (instala imageio-ffmpeg).")


def ffprobe_duration(path: Path) -> Optional[float]:
    """Duração via ffmpeg (sem ffprobe): lê 'Duration:' do stderr."""
    import re
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", r.stderr)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _ffmeta(chapters: List[Tuple[str, float, float]], title: str, author: str) -> str:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\n", " ")
    out = [";FFMETADATA1", f"title={esc(title)}"]
    if author:
        out.append(f"artist={esc(author)}")
        out.append(f"album_artist={esc(author)}")
    out.append(f"album={esc(title)}")
    out.append("genre=Audiobook")
    for t, a, b in chapters:
        out += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(a * 1000)}", f"END={int(b * 1000)}", f"title={esc(t)}"]
    return "\n".join(out) + "\n"


def encode(wav: Path, out: Path, fmt: str, chapters: Optional[List[Tuple[str, float, float]]] = None,
           title: str = "", author: str = "") -> None:
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Formato não suportado: {fmt}. Use: {', '.join(FORMATS)}")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    if fmt == "wav":
        shutil.copyfile(wav, tmp)
        os.replace(tmp, out)
        return
    args = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav)]
    meta = None
    if chapters and fmt in ("m4b", "m4a", "mp3"):
        meta = wav.with_suffix(".ffmeta")
        meta.write_text(_ffmeta(chapters, title, author), encoding="utf-8")
        args += ["-i", str(meta), "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1"]
    elif title:
        args += ["-metadata", f"title={title}"]
    codec = list(FORMATS[fmt][0])
    if fmt == "mp3":
        codec += ["-id3v2_version", "3", "-f", "mp3"]
    args += codec + [str(tmp)]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {r.stderr.strip()[-500:]}")
    os.replace(tmp, out)


def export_approved(chapter_files: List[Tuple[Path, str]], out: Path, title: str, author: str = "") -> float:
    """Build an M4B from approved audio files; this path never calls a TTS engine."""
    if not chapter_files:
        raise ValueError("Nenhum áudio aprovado foi selecionado.")
    durations = []
    for path, _chapter_title in chapter_files:
        duration = ffprobe_duration(path)
        if duration is None or duration <= 0:
            raise RuntimeError(f"Não foi possível verificar a duração de {path.name}.")
        durations.append(duration)
    chapters, cursor = [], 0.0
    for (_path, chapter_title), duration in zip(chapter_files, durations):
        chapters.append((chapter_title, cursor, cursor + duration))
        cursor += duration

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ragnarok-export-", dir=str(out.parent)) as temp_name:
        wav = Path(temp_name) / "approved-chapters.wav"
        args = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"]
        for path, _ in chapter_files:
            args += ["-i", str(path)]
        filters = []
        for index in range(len(chapter_files)):
            filters.append(f"[{index}:a:0]aresample=24000,aformat=sample_fmts=s16:channel_layouts=mono[a{index}]")
        inputs = "".join(f"[a{i}]" for i in range(len(chapter_files)))
        filters.append(f"{inputs}concat=n={len(chapter_files)}:v=0:a=1[outa]")
        args += ["-filter_complex", ";".join(filters), "-map", "[outa]", "-c:a", "pcm_s16le", str(wav)]
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Não foi possível concatenar os áudios aprovados: {result.stderr.strip()[-500:]}")
        encode(wav, out, "m4b", chapters=chapters, title=title, author=author)

    actual = ffprobe_duration(out)
    if actual is None or abs(actual - cursor) > max(2.0, cursor * 0.02):
        out.unlink(missing_ok=True)
        raise RuntimeError(f"Verificação de duração do audiobook falhou (esperado {cursor:.1f}s; encontrado {actual}).")
    probe = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(out), "-f", "ffmetadata", "-"],
                           capture_output=True)
    metadata = probe.stdout.decode("utf-8", errors="replace")
    found_titles = [line[6:] for line in metadata.splitlines() if line.startswith("title=")]
    expected_titles = [chapter_title for _path, chapter_title in chapter_files]
    if probe.returncode or found_titles[-len(expected_titles):] != expected_titles:
        out.unlink(missing_ok=True)
        raise RuntimeError("Verificação da ordem/metadados dos capítulos falhou.")
    return actual


# ---------------------------------------------------------------- memória


def _win_mem(field: str) -> float:
    """Windows: lê PeakWorkingSetSize/WorkingSetSize com assinaturas ctypes corretas (handle de 64 bits)."""
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    try:
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        fn = psapi.GetProcessMemoryInfo
    except (OSError, AttributeError):
        fn = k32.K32GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    fn.restype = wintypes.BOOL
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    if not fn(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
        return -1.0
    return getattr(pmc, field) / (1024 * 1024)


def peak_rss_mb() -> float:
    """Pico de memória do processo (MB). Linux/macOS: ru_maxrss. Windows: PeakWorkingSetSize."""
    try:
        if sys.platform == "win32":
            return _win_mem("PeakWorkingSetSize")
        import resource
        v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return v / (1024 * 1024) if sys.platform == "darwin" else v / 1024
    except Exception:
        return -1.0


def current_rss_mb() -> float:
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/self/statm") as f:
                pages = int(f.read().split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
        if sys.platform == "win32":
            return _win_mem("WorkingSetSize")
    except Exception:
        pass
    return -1.0
