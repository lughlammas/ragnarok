"""Servidor local (127.0.0.1): interface web + API + endpoint compatível com /v1/audio/speech."""
import tempfile
import threading
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import __version__, audio, models, synth, voices as vc
from .engines import MANAGER
from .jobs import JobManager
from .paths import OUTPUT_DIR, WORK_DIR, ensure_dirs

WEB = Path(__file__).parent / "web"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
MAX_UPLOAD = 3 * 1024 * 1024
MAX_SPEECH_CHARS = 20000

app = FastAPI(title="Ragnarok", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
_jobs: Optional[JobManager] = None


def jobs() -> JobManager:
    global _jobs
    if _jobs is None:
        _jobs = JobManager()
    return _jobs


@app.middleware("http")
async def guard(request: Request, call_next):
    """Só aceita Host local (anti DNS-rebinding) e Origin local em requisições que alteram algo."""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0] if not (request.headers.get("host") or "").startswith("[") \
        else (request.headers.get("host") or "").split("]")[0] + "]"
    if host not in ALLOWED_HOSTS:
        return JSONResponse({"error": "host não permitido"}, status_code=400)
    origin = request.headers.get("origin")
    if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
        oh = urlparse(origin).hostname or ""
        if oh not in {"127.0.0.1", "localhost", "::1"}:
            return JSONResponse({"error": "origem não permitida"}, status_code=403)
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/api/voices")
def api_voices():
    return {"default": vc.default_voice_id(), "voices": [v.public() for v in vc.all_voices()]}


@app.get("/api/status")
def api_status():
    return {"version": __version__, "loaded_engine": MANAGER.loaded or None,
            "ram_peak_mb": round(audio.peak_rss_mb(), 1), "ram_now_mb": round(audio.current_rss_mb(), 1),
            "models": models.status(),
            "queue": sum(1 for j in jobs().list() if j.status in ("queued", "running"))}


def _job_dict(j):
    from dataclasses import asdict
    d = asdict(j)
    d["has_audio"] = j.status == "done" and (j.approved_audio_path if j.approved else j.out_path).exists()
    return d


class JobIn(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: float = 0.85
    format: str = "wav"
    title: str = ""
    kind: str = "auto"          # auto | say | book
    announce_titles: bool = True
    pronunciation: dict[str, str] = Field(default_factory=dict)


class ApprovedBookIn(BaseModel):
    chapter_ids: list[str]
    title: str
    author: str = ""


def _kind(text: str, kind: str) -> str:
    if kind in ("say", "book"):
        return kind
    import re
    return "book" if (re.search(r"^#{1,6}\s", text, re.M) or len(text) > 6000) else "say"


@app.post("/api/jobs")
def api_submit(j: JobIn):
    if len(j.text) > 2_000_000:
        raise HTTPException(413, "Texto grande demais (máx. 2 MB).")
    try:
        title = j.title or (" ".join(j.text.split())[:40] or "Texto")
        job = jobs().submit(j.text, _kind(j.text, j.kind), j.voice or vc.default_voice_id(),
                            j.speed, j.format, title, j.announce_titles, j.pronunciation)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _job_dict(job)


@app.post("/api/jobs/upload")
async def api_upload(file: UploadFile = File(...), voice: str = Form(""), speed: float = Form(0.85),
                     format: str = Form("m4b"), title: str = Form(""), announce_titles: bool = Form(True)):
    name = (file.filename or "").lower()
    if not name.endswith((".md", ".txt", ".markdown")):
        raise HTTPException(400, "Envie um arquivo .md ou .txt")
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Arquivo grande demais (máx. 3 MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    try:
        job = jobs().submit(text, "book", voice or vc.default_voice_id(), speed, format,
                            title or Path(file.filename).stem, announce_titles)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _job_dict(job)


@app.get("/api/jobs")
def api_list():
    return [_job_dict(j) for j in jobs().list()]


@app.get("/api/jobs/{jid}")
def api_job(jid: str):
    j = jobs().get(jid)
    if not j:
        raise HTTPException(404, "trabalho não encontrado")
    return _job_dict(j)


@app.get("/api/jobs/{jid}/audio")
def api_audio(jid: str, download: int = 0):
    j = jobs().get(jid)
    if not j or j.status != "done":
        raise HTTPException(404, "áudio não disponível")
    audio_path = j.approved_audio_path if j.approved else j.out_path
    if not audio_path.exists():
        raise HTTPException(404, "áudio não disponível")
    mt = audio.FORMATS[j.format][1]
    fname = "".join(c if c.isalnum() or c in " -_" else "_" for c in j.title).strip() or "ragnarok"
    return FileResponse(audio_path, media_type=mt, filename=f"{fname}.{j.format}" if download else None)


@app.post("/api/jobs/{jid}/approve")
def api_approve(jid: str):
    try:
        return _job_dict(jobs().approve(jid))
    except KeyError:
        raise HTTPException(404, "trabalho não encontrado")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/books/export-approved")
async def api_export_approved(book: ApprovedBookIn):
    if not book.title.strip():
        raise HTTPException(400, "Informe o título do audiobook.")
    try:
        selected = jobs().get_approved(book.chapter_ids)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in book.title).strip() or "audiobook"
        out = OUTPUT_DIR / f"{safe_title}-{__import__('uuid').uuid4().hex[:8]}.m4b"
        inputs = [(j.approved_audio_path, j.chapter_title or j.title) for j in selected]
        duration = await run_in_threadpool(audio.export_approved, inputs, out, book.title, book.author)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return FileResponse(out, media_type="audio/mp4", filename=f"{safe_title}.m4b",
                        headers={"X-Audiobook-Duration": f"{duration:.2f}",
                                 "X-Audiobook-Chapters": str(len(selected))})


@app.post("/api/jobs/{jid}/retry")
def api_retry(jid: str):
    try:
        return _job_dict(jobs().retry(jid))
    except KeyError:
        raise HTTPException(404, "trabalho não encontrado")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/jobs/{jid}")
def api_delete(jid: str):
    try:
        return {"result": jobs().delete(jid)}
    except KeyError:
        raise HTTPException(404, "trabalho não encontrado")
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------ /v1 (compatível com OpenAI)

class SpeechIn(BaseModel):
    model: str = "ragnarok"
    input: str
    voice: Optional[str] = None
    response_format: str = "mp3"
    speed: float = 0.85


_OPENAI_FORMATS = {"mp3": "mp3", "opus": "opus", "aac": "aac", "flac": "flac", "wav": "wav", "pcm": "pcm"}


@app.get("/v1/models")
def v1_models():
    return {"object": "list", "data": [{"id": "ragnarok", "object": "model", "owned_by": "local"}]}


@app.get("/v1/audio/voices")
def v1_voices():
    return {"voices": [{"id": v.id, "name": v.label, "language": v.lang} for v in vc.all_voices()]}


def _speech_sync(body: SpeechIn) -> Response:
    fmt = body.response_format.lower()
    if fmt not in _OPENAI_FORMATS:
        raise HTTPException(400, f"response_format inválido: {fmt}")
    name = body.voice
    if name and name.lower() in vc.openai_aliases():
        name = None                      # nomes da OpenAI (alloy, nova...) -> voz padrão
    try:
        v = vc.resolve(name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    ensure_dirs()
    tmpd = Path(tempfile.mkdtemp(prefix="v1-", dir=WORK_DIR))
    try:
        out = tmpd / ("out." + ("wav" if fmt == "pcm" else fmt))
        synth.say_text(body.input, v, body.speed, out, "wav" if fmt == "pcm" else fmt)
        data = out.read_bytes()
        if fmt == "pcm":                 # PCM16 mono cru (sem cabeçalho WAV)
            data = data[44:]
            mt = "audio/pcm"
        else:
            mt = audio.FORMATS[fmt][1]
        return Response(content=data, media_type=mt)
    finally:
        import shutil
        shutil.rmtree(tmpd, ignore_errors=True)


@app.post("/v1/audio/speech")
async def v1_speech(body: SpeechIn):
    if not body.input.strip():
        raise HTTPException(400, "input vazio")
    if len(body.input) > MAX_SPEECH_CHARS:
        raise HTTPException(413, f"input grande demais (máx. {MAX_SPEECH_CHARS} caracteres); use a fila (/api/jobs)")
    try:
        return await run_in_threadpool(_speech_sync, body)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    import uvicorn
    ensure_dirs()
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"AVISO: host {host} expõe o servidor fora desta máquina. O padrão seguro é 127.0.0.1.")
    jobs()
    url = f"http://{host}:{port}/"
    print(f"Ragnarok {__version__} em {url}  (Ctrl+C para sair). Nada é enviado para fora da máquina.")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
