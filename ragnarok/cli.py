"""Linha de comando: say, book, web, voices, models, doctor."""
import argparse
import sys
import time
from pathlib import Path

from . import __version__, audio, voices as vc
from .paths import ensure_dirs


def _read_text(path: str) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _fmt_t(s: float) -> str:
    s = int(max(0, s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


class Bar:
    def __init__(self, label: str):
        self.label, self.t0, self.tty = label, time.time(), sys.stderr.isatty()

    def __call__(self, done: int, total: int, eta: float):
        pct = done / total if total else 1
        n = int(pct * 30)
        line = (f"\r{self.label} [{'#' * n}{'-' * (30 - n)}] {pct * 100:5.1f}% {done}/{total} blocos  "
                f"decorrido {_fmt_t(time.time() - self.t0)}  restante ~{_fmt_t(eta)}  RAM pico {audio.peak_rss_mb():.0f} MB")
        if self.tty:
            sys.stderr.write(line + "   ")
            sys.stderr.flush()
        elif done == total or done % 10 == 0:
            sys.stderr.write(line.lstrip("\r") + "\n")

    def end(self):
        if self.tty:
            sys.stderr.write("\n")


def _summary(st, out: Path):
    print(f"\nPronto: {out}")
    print(f"  áudio: {_fmt_t(st.audio_seconds)} ({st.audio_seconds:.1f} s) | blocos: {st.chunks} "
          f"(gerados {st.generated}, reaproveitados {st.reused}) | caracteres: {st.chars}")
    print(f"  tempo total: {st.total_seconds:.1f} s | RTF (total/áudio): {st.rtf:.3f} | "
          f"síntese nesta execução: {st.gen_seconds:.1f} s")
    print(f"  RAM pico do processo: {st.peak_ram_mb:.0f} MB | anomalias detectadas: {st.anomalies} (retentativas {st.retries})")
    if len(st.chapters) > 1:
        for i, (t, a, b) in enumerate(st.chapters, 1):
            print(f"  cap. {i}: {t}  [{_fmt_t(a)} - {_fmt_t(b)}]")


def cmd_say(a):
    from . import synth
    ensure_dirs()
    text = " ".join(a.text) if a.text else ""
    if a.file:
        text = (_read_text(a.file) if a.file != "-" else sys.stdin.read())
    if not text.strip():
        print("Nada para ler. Use: ragnarok say \"texto\"  ou  --file arquivo.txt", file=sys.stderr)
        return 2
    v = vc.resolve(a.voice)
    out = Path(a.out)
    bar = Bar("say")
    st = synth.say_text(text, v, a.speed, out, progress=bar)
    bar.end()
    _summary(st, out)
    return 0


def cmd_book(a):
    from . import synth, textproc
    ensure_dirs()
    src = Path(a.file)
    if not src.exists():
        print(f"Arquivo não encontrado: {src}", file=sys.stderr)
        return 2
    v = vc.resolve(a.voice)
    out = Path(a.out) if a.out else src.with_suffix(".m4b")
    book = textproc.parse_markdown(_read_text(str(src)), default_title=a.title or src.stem)
    if a.title:
        book.title = a.title
    if not book.chapters:
        print("Nenhum texto legível.", file=sys.stderr)
        return 2
    print(f"Livro: {book.title} | capítulos: {len(book.chapters)} | voz: {v.label} | saída: {out}")
    bar = Bar("book")
    try:
        st = synth.render_book(book, v, a.speed, out, announce_titles=not a.no_titles, progress=bar,
                               keep_work=a.keep_work, author=a.author or "")
    except KeyboardInterrupt:
        bar.end()
        print("\nInterrompido. Rode o mesmo comando de novo para RETOMAR de onde parou.", file=sys.stderr)
        return 130
    bar.end()
    _summary(st, out)
    return 0


def cmd_web(a):
    from .server import run
    run(host=a.host, port=a.port, open_browser=not a.no_browser)
    return 0


def cmd_voices(a):
    for v in vc.all_voices():
        print(f"{v.id:12s} {v.label:28s} [{v.engine}/{v.lang}, base {v.speed}]  {v.description}")
    return 0


def cmd_models(a):
    from . import models
    models.ensure_all(kokoro_only=a.kokoro)
    return 0


def cmd_doctor(a):
    import platform
    ok = True
    print(f"Ragnarok {__version__} | Python {platform.python_version()} | {platform.platform()}")
    if sys.version_info < (3, 11):
        print("  [ERRO] Python 3.11+ é necessário"); ok = False
    if sys.version_info >= (3, 14):
        print("  [AVISO] Python 3.14+: kokoro-onnx 0.6.1 declara <3.14")
    for mod in ("numpy", "soundfile", "onnxruntime", "kokoro_onnx", "fastapi", "uvicorn", "multipart"):
        try:
            m = __import__(mod)
            print(f"  [ok] {mod} {getattr(m, '__version__', '')}")
        except Exception as e:
            print(f"  [ERRO] {mod}: {e}"); ok = False
    try:
        print(f"  [ok] ffmpeg: {audio.ffmpeg_exe()}")
    except Exception as e:
        print(f"  [ERRO] ffmpeg: {e}"); ok = False
    from . import models
    model_status = models.status()
    required_engine = vc.resolve(None).engine
    for engine, name in (("kokoro", "Kokoro"), ("supertonic", "Supertonic")):
        if engine == required_engine:
            print(f"  [{'ok' if model_status[engine] else 'FALTA'}] modelo {name} (necessário para {vc.default_voice_id()})")
            ok = ok and model_status[engine]
        else:
            print(f"  [{'ok' if model_status[engine] else 'opcional'}] modelo {name} (engine alternativo)")
    if a.full and ok:
        from . import synth
        ensure_dirs()
        import tempfile
        for vid in ("alex-pt", "sabio-en"):
            v = vc.resolve(vid)
            out = Path(tempfile.gettempdir()) / f"ragnarok-doctor-{vid}.wav"
            t = time.time()
            st = synth.say_text("Teste rápido do Ragnarok.", v, 1.0, out)
            print(f"  [ok] {v.label}: {st.audio_seconds:.1f}s de áudio em {time.time() - t:.1f}s | RAM pico {st.peak_ram_mb:.0f} MB")
    print("TUDO OK" if ok else "HÁ PROBLEMAS (veja acima)")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ragnarok", description="Ragnarok - texto para voz local (CPU), uso pessoal.")
    p.add_argument("--version", action="version", version=f"ragnarok {__version__}")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("say", help="ler um texto em voz alta e salvar em arquivo")
    s.add_argument("text", nargs="*", help="texto (ou use --file)")
    s.add_argument("--file", "-f", help="arquivo .txt/.md ('-' = stdin)")
    s.add_argument("--voice", "-v", default=None, help="id da voz (veja: ragnarok voices)")
    s.add_argument("--speed", "-s", type=float, default=0.85, help="multiplicador de velocidade (0.5-2.0), padrão 0.85")
    s.add_argument("--out", "-o", default="ragnarok.wav", help="arquivo de saída (.wav .mp3 .m4a .ogg .opus .flac)")
    s.set_defaults(fn=cmd_say)

    b = sub.add_parser("book", help="converter um .md/.txt em audiolivro com capítulos")
    b.add_argument("file")
    b.add_argument("--voice", "-v", default=None)
    b.add_argument("--speed", "-s", type=float, default=0.85)
    b.add_argument("--out", "-o", default=None, help="saída (.m4b ou .mp3); padrão: <arquivo>.m4b")
    b.add_argument("--title", help="título do livro (metadados)")
    b.add_argument("--author", help="autor (metadados)")
    b.add_argument("--no-titles", action="store_true", help="não ler os títulos dos capítulos em voz alta")
    b.add_argument("--keep-work", action="store_true", help="mantém os blocos intermediários")
    b.set_defaults(fn=cmd_book)

    w = sub.add_parser("web", help="abrir a interface web local")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8765)
    w.add_argument("--no-browser", action="store_true")
    w.set_defaults(fn=cmd_web)

    sub.add_parser("voices", help="listar vozes").set_defaults(fn=cmd_voices)
    m = sub.add_parser("models", help="baixar/verificar modelos")
    m.add_argument("--kokoro", action="store_true", help="instala apenas Kokoro, necessário para a voz Alex")
    m.set_defaults(fn=cmd_models)
    d = sub.add_parser("doctor", help="diagnóstico da instalação")
    d.add_argument("--full", action="store_true", help="também gera uma frase de teste em 2 vozes")
    d.set_defaults(fn=cmd_doctor)

    a = p.parse_args(argv)
    if not getattr(a, "fn", None):
        p.print_help()
        return 0
    try:
        return a.fn(a)
    except ValueError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1
