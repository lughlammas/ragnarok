"""Markdown -> capítulos -> parágrafos -> frases -> blocos seguros para o TTS."""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

MAX_CHARS = 220        # alvo de tamanho de bloco (caracteres)
HARD_MAX = 300         # nenhum bloco passa disso
PAUSE_PARAGRAPH = 0.8
PAUSE_TITLE = 1.2
PAUSE_LIST = 0.5
PAUSE_ELLIPSIS = 0.7
PAUSE_STRONG = 0.45    # ! ?
PAUSE_PERIOD = 0.4
PAUSE_SOFT = 0.25      # , ; : (cortes dentro de frases longas) e frases sem pontuação final

ABBR = {"sr", "sra", "srta", "dr", "dra", "prof", "profa", "mr", "mrs", "ms", "st", "vs", "nº", "cap",
        "fig", "ex", "av", "cf", "pág", "pag", "jr", "sto", "sta", "art", "obs", "ed"}


@dataclass
class Para:
    text: str
    kind: str = "p"          # p | li | sub


@dataclass
class Chapter:
    title: str
    paras: List[Para] = field(default_factory=list)
    implicit: bool = False      # sem cabeçalho no texto: o título NÃO é lido em voz alta


@dataclass
class Book:
    title: str
    author: str = ""
    chapters: List[Chapter] = field(default_factory=list)


@dataclass
class Unit:
    chapter: int
    text: str
    pause: float
    kind: str = "body"       # body | title


# ---------------------------------------------------------------- limpeza

_FRONT = re.compile(r"\A\ufeff?---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)


def _front_matter(text: str) -> Tuple[dict, str]:
    m = _FRONT.match(text)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip().strip("\"'")
        text = text[m.end():]
    return meta, text


def clean_inline(s: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)                  # imagens
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)               # links [t](u) -> t
    s = re.sub(r"<(https?://[^>]+)>", "", s)                      # autolinks
    s = re.sub(r"\[\^[^\]]+\]", "", s)                            # notas de rodapé
    s = re.sub(r"<[^>\n]+>", "", s)                               # html
    s = re.sub(r"`([^`]*)`", r"\1", s)                            # código inline
    s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)                     # negrito
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)   # itálico *
    s = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"\1", s)     # itálico _
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    s = s.replace("\\", "") if re.search(r"\\[*_#`\[\]()>~-]", s) else s
    s = s.replace("|", ", ")
    s = re.sub(r"\.{3,}", "…", s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    return s.strip()


_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LI = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+(.*)$")
_HR = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def parse_markdown(text: str, default_title: str = "Texto", intro_title: str = "Início") -> Book:
    meta, text = _front_matter(text.replace("\r\n", "\n").replace("\r", "\n"))
    # 1) linhas -> blocos tipados
    blocks = []  # (kind, level, text)
    para: List[str] = []
    in_fence = False

    def flush():
        if para:
            t = clean_inline(" ".join(x.strip() for x in para))
            if t:
                blocks.append(("p", 0, t))
            para.clear()

    for raw in text.split("\n"):
        if _FENCE.match(raw):
            flush(); in_fence = not in_fence
            continue
        if in_fence:
            continue                       # blocos de código não são lidos
        line = raw.rstrip()
        if not line.strip():
            flush(); continue
        if _HR.match(line):
            flush(); continue
        m = _HEAD.match(line)
        if m:
            flush()
            t = clean_inline(m.group(2))
            if t:
                blocks.append(("h", len(m.group(1)), t))
            continue
        m = _LI.match(line)
        if m:
            flush()
            t = clean_inline(m.group(1))
            if t:
                blocks.append(("li", 0, t))
            continue
        if re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", line):   # separador de tabela
            continue
        line = re.sub(r"^\s*>+\s?", "", line)                   # citações
        para.append(line)
    flush()

    levels = [lvl for k, lvl, _ in blocks if k == "h"]
    chap_level = min(levels) if levels else None
    title = meta.get("title") or default_title
    book = Book(title=title, author=meta.get("author", ""))
    cur: Optional[Chapter] = None
    for kind, lvl, t in blocks:
        if kind == "h" and lvl == chap_level:
            cur = Chapter(title=t)
            book.chapters.append(cur)
            continue
        if cur is None:
            cur = Chapter(title=intro_title if chap_level is not None else default_title, implicit=True)
            book.chapters.append(cur)
        if kind == "h":
            cur.paras.append(Para(t, "sub"))
        else:
            cur.paras.append(Para(t, kind))
    # capítulo "Início" sem texto nenhum não existe (só criamos se houver bloco)
    book.chapters = [c for c in book.chapters if c.paras or c.title]
    return book


# ---------------------------------------------------------------- frases / blocos

_SENT_END = re.compile(r"(?<=[.!?…])([\"'”’»)\]]*)\s+")


def split_sentences(par: str) -> List[str]:
    parts: List[str] = []
    pos = 0
    for m in _SENT_END.finditer(par):
        parts.append(par[pos:m.start() + len(m.group(1))])
        pos = m.end()
    parts.append(par[pos:])
    parts = [p.strip() for p in parts if p.strip()]
    # recoloca abreviações / iniciais / ordinais ("Sr.", "J.", "3.")
    merged: List[str] = []
    for p in parts:
        if merged:
            prev = merged[-1]
            last = re.sub(r"[^\wº°ªáéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]", "", prev.split()[-1]).lower()
            if prev.endswith(".") and (last in ABBR or (len(last) == 1 and last.isalpha()) or last.isdigit()):
                merged[-1] = prev + " " + p
                continue
        merged.append(p)
    return merged


def _split_long(s: str, limit: int = MAX_CHARS) -> List[str]:
    """Quebra frase longa em pedaços <= limit, preferindo ; : , — e depois espaços."""
    if len(s) <= limit:
        return [s]
    out, cur = [], ""
    pieces = re.split(r"(?<=[;:,—–])\s+", s)
    for pc in pieces:
        if len(pc) > limit:                       # pedaço ainda gigante: corta em espaços
            if cur:
                out.append(cur); cur = ""
            words, buf = pc.split(" "), ""
            for w in words:
                if len(w) > limit:                # palavra absurda: corte duro
                    if buf:
                        out.append(buf); buf = ""
                    for i in range(0, len(w), limit):
                        out.append(w[i:i + limit])
                    continue
                if buf and len(buf) + 1 + len(w) > limit:
                    out.append(buf); buf = w
                else:
                    buf = (buf + " " + w).strip()
            if buf:
                out.append(buf)
            continue
        if cur and len(cur) + 1 + len(pc) > limit:
            out.append(cur); cur = pc
        else:
            cur = (cur + " " + pc).strip()
    if cur:
        out.append(cur)
    return out


def pause_for(text: str) -> float:
    t = text.rstrip("\"'”’»)] ")
    if t.endswith("…"):
        return PAUSE_ELLIPSIS
    if t.endswith(("!", "?")):
        return PAUSE_STRONG
    if t.endswith("."):
        return PAUSE_PERIOD
    return PAUSE_SOFT


def _speakable(t: str) -> bool:
    return bool(re.search(r"\w", t, re.U))


def chunk_paragraph(par: str, max_chars: int = MAX_CHARS) -> List[Tuple[str, float]]:
    """Parágrafo -> [(bloco, pausa_depois)]. Frases curtas são agrupadas com a vizinha."""
    sents: List[str] = []
    for s in split_sentences(par):
        sents.extend(_split_long(s, max_chars))
    chunks: List[str] = []
    for s in sents:
        if chunks and len(chunks[-1]) + 1 + len(s) <= max_chars and (len(chunks[-1]) < 50 or len(s) < 40):
            chunks[-1] = chunks[-1] + " " + s
        else:
            chunks.append(s)
    return [(c, pause_for(c)) for c in chunks if _speakable(c)]


def book_to_units(book: Book, announce_titles: bool = True, max_chars: int = MAX_CHARS):
    """Devolve (units, chapter_first_unit_index)."""
    units: List[Unit] = []
    starts: List[int] = []
    for ci, ch in enumerate(book.chapters):
        starts.append(len(units))
        if announce_titles and not ch.implicit and ch.title and _speakable(ch.title):
            units.append(Unit(ci, ch.title, PAUSE_TITLE, "title"))
        for p in ch.paras:
            cks = chunk_paragraph(p.text, max_chars)
            for i, (c, ps) in enumerate(cks):
                last = i == len(cks) - 1
                if last:
                    ps = max(ps, {"p": PAUSE_PARAGRAPH, "li": PAUSE_LIST, "sub": PAUSE_TITLE}[p.kind])
                units.append(Unit(ci, c, ps))
    return units, starts


def plain_book(text: str, title: str = "Texto") -> Book:
    """Texto simples (sem cabeçalhos): trata como Markdown de um capítulo só."""
    return parse_markdown(text, default_title=title)
