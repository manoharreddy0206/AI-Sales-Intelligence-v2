"""Simple lexical retrieval over the checked-in metrics glossary.

Entries are split on ``## Title {#id}`` headings. Scoring is token overlap with
extra weight for the title and aliases. This is deliberately simple: the
glossary is small, and the stable IDs make every citation checkable.
"""
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "glossary" / "metrics_glossary.md"
HEADING = re.compile(r"^## (.+?) \{#([a-z0-9-]+)\}\s*$", re.M)
TOKEN = re.compile(r"[a-z0-9]+")
STOP = set(
    "a an the is are was were be been of to in on for and or how what which who why when do does did "
    "we our my i you your it its this that by with as at from define defined definition mean means "
    "meaning explain tell me about calculated calculate computed compute".split()
)
MIN_SCORE = 3.0


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    aliases: tuple[str, ...]
    source: str
    text: str


def _tokens(text: str) -> list[str]:
    out = []
    for tok in TOKEN.findall(text.lower()):
        if tok in STOP:
            continue
        if len(tok) > 3 and tok.endswith("s"):
            tok = tok[:-1]
        out.append(tok)
    return out


def glossary_path() -> Path:
    return Path(os.environ.get("GLOSSARY_PATH", str(DEFAULT_PATH)))


@lru_cache(maxsize=8)
def load(path: str | None = None) -> tuple[Entry, ...]:
    raw = Path(path or glossary_path()).read_text(encoding="utf-8")
    matches = list(HEADING.finditer(raw))
    entries = []
    for i, m in enumerate(matches):
        body = raw[m.end(): matches[i + 1].start() if i + 1 < len(matches) else len(raw)].strip()
        aliases, source, lines = (), "", []
        for line in body.splitlines():
            if line.startswith("Aliases:"):
                aliases = tuple(a.strip() for a in line[8:].split(",") if a.strip())
            elif line.startswith("Source:"):
                source = line[7:].strip()
            elif line.strip():
                lines.append(line.strip())
        entries.append(Entry(m.group(2), m.group(1).strip(), aliases, source, " ".join(lines)))
    return tuple(entries)


def search(query: str, k: int = 2, path: str | None = None) -> list[dict]:
    q = set(_tokens(query))
    if not q:
        return []
    scored = []
    for e in load(path):
        head = set(_tokens(e.title + " " + " ".join(e.aliases)))
        body = set(_tokens(e.text))
        phrase_bonus = sum(3.0 for a in e.aliases if a.lower() in query.lower())
        score = 3.0 * len(q & head) + 0.5 * len(q & body) + phrase_bonus
        if score >= MIN_SCORE:
            scored.append((score, e))
    scored.sort(key=lambda s: (-s[0], s[1].id))
    # Keep secondary passages only when they score close to the best match.
    scored = [s for s in scored if s[0] >= 0.6 * scored[0][0]] if scored else []
    return [
        {"source_id": e.id, "title": e.title, "source": e.source, "text": e.text, "score": round(s, 2)}
        for s, e in scored[:k]
    ]
