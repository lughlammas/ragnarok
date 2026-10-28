"""Fila de trabalhos (um por vez), histórico em disco."""
import json
import queue
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from . import audio, synth, textproc, voices as vc
from .paths import JOBS_DIR, OUTPUT_DIR, DATA_DIR, ensure_dirs

HISTORY = DATA_DIR / "history.json"
MAX_HISTORY = 200


@dataclass
class Job:
    id: str
    kind: str                 # say | book
    title: str
    voice: str
    speed: float
    format: str
    chars: int
    status: str = "queued"    # queued | running | done | error | cancelled | interrupted
    done: int = 0
    total: int = 0
    eta: float = 0.0
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    error: str = ""
    audio_seconds: float = 0.0
    total_seconds: float = 0.0
    rtf: float = 0.0
    peak_ram_mb: float = 0.0
    chapters: int = 0
    reused: int = 0
    anomalies: int = 0
    announce_titles: bool = True

    @property
    def out_path(self) -> Path:
        return OUTPUT_DIR / f"{self.id}.{self.format}"


class JobManager:
    def __init__(self):
        ensure_dirs()
        self.jobs: Dict[str, Job] = {}
        self.q: "queue.Queue[str]" = queue.Queue()
        self.cancel_flags: Dict[str, bool] = {}
        self.lock = threading.Lock()
        self._load()
        self.worker = threading.Thread(target=self._run, daemon=True, name="ragnarok-worker")
        self.worker.start()

    # ---- persistência
    def _load(self):
        if HISTORY.exists():
            try:
                for d in json.loads(HISTORY.read_text(encoding="utf-8")):
                    j = Job(**d)
                    if j.status in ("queued", "running"):
                        j.status = "interrupted"
                        j.error = "O programa foi fechado durante este trabalho. Use 'Retomar'."
                    self.jobs[j.id] = j
            except Exception:
                pass

    def _save(self):
        items = sorted(self.jobs.values(), key=lambda j: j.created)[-MAX_HISTORY:]
        tmp = HISTORY.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(j) for j in items], ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(HISTORY)

    # ---- API
    def submit(self, text: str, kind: str, voice_id: str, speed: float, fmt: str, title: str,
               announce_titles: bool = True) -> Job:
        v = vc.resolve(voice_id)
        fmt = fmt.lower()
        if fmt not in audio.FORMATS:
            raise ValueError(f"Formato não suportado: {fmt}")
        if not text.strip():
            raise ValueError("Texto vazio.")
        jid = uuid.uuid4().hex[:12]
        d = JOBS_DIR / jid
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.txt").write_text(text, encoding="utf-8")
        job = Job(id=jid, kind=kind, title=title or ("Texto" if kind == "say" else "Livro"), voice=v.id,
                  speed=speed, format=fmt, chars=len(text), announce_titles=announce_titles)
        with self.lock:
            self.jobs[jid] = job
            self._save()
        self.q.put(jid)
        return job

    def get(self, jid: str) -> Optional[Job]:
        return self.jobs.get(jid)

    def list(self) -> List[Job]:
        return sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)

    def retry(self, jid: str) -> Job:
        j = self.jobs[jid]
        if j.status in ("queued", "running"):
            raise ValueError("Trabalho em andamento.")
        if not (JOBS_DIR / jid / "input.txt").exists():
            raise ValueError("Texto original não está mais disponível.")
        j.status, j.error, j.done, j.eta = "queued", "", 0, 0.0
        self.cancel_flags.pop(jid, None)
        self._save()
        self.q.put(jid)
        return j

    def delete(self, jid: str) -> str:
        import shutil
        j = self.jobs.get(jid)
        if not j:
            raise KeyError(jid)
        if j.status in ("queued", "running"):
            self.cancel_flags[jid] = True
            return "cancelando"
        j.out_path.unlink(missing_ok=True)
        shutil.rmtree(JOBS_DIR / jid, ignore_errors=True)
        with self.lock:
            self.jobs.pop(jid, None)
            self._save()
        return "removido"

    # ---- worker
    def _run(self):
        while True:
            jid = self.q.get()
            j = self.jobs.get(jid)
            if not j or j.status != "queued":
                continue
            if self.cancel_flags.pop(jid, False):
                j.status = "cancelled"; self._save(); continue
            j.status = "running"
            self._save()
            try:
                text = (JOBS_DIR / jid / "input.txt").read_text(encoding="utf-8")
                v = vc.resolve(j.voice)

                def prog(done, total, eta, j=j):
                    j.done, j.total, j.eta = done, total, eta

                cancel = lambda jid=jid: self.cancel_flags.get(jid, False)
                if j.kind == "book":
                    book = textproc.parse_markdown(text, default_title=j.title)
                    st = synth.render_book(book, v, j.speed, j.out_path, j.format, announce_titles=j.announce_titles,
                                           progress=prog, cancel=cancel)
                else:
                    st = synth.say_text(text, v, j.speed, j.out_path, j.format, progress=prog, cancel=cancel)
                j.status, j.audio_seconds, j.total_seconds = "done", st.audio_seconds, st.total_seconds
                j.rtf, j.peak_ram_mb, j.chapters = st.rtf, st.peak_ram_mb, len(st.chapters)
                j.reused, j.anomalies = st.reused, st.anomalies
            except synth.Cancelled:
                j.status = "cancelled"
            except Exception as e:
                j.status, j.error = "error", f"{type(e).__name__}: {e}"
                traceback.print_exc()
            finally:
                self.cancel_flags.pop(jid, None)
                j.finished = time.time()
                j.eta = 0.0
                self._save()
