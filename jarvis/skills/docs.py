"""Ask-my-documents: local folder Q&A without embeddings.

Scans the docs folder (JARVIS_DOCS_DIR, default <workspace>/docs) for
text-ish files, chunks them, and keyword-scores each chunk against the
question. Top chunks come back labelled with their file so the brain (or
the offline path) can quote the source. Zero network, zero ML deps.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List, Tuple

from . import skill
from ..config import config

_TEXTY = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".json", ".xml",
    ".yml", ".yaml", ".ini", ".cfg", ".toml", ".sql", ".tex",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".hpp", ".cs", ".go", ".rs", ".sh", ".bat", ".ps1", ".css", ".html",
}
_MAX_FILE = 350_000          # chars per file read
_MAX_TOTAL = 1_500_000       # total chars scanned per query
_CHUNK = 900                 # target chunk size (chars)

_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "does",
    "for", "from", "had", "has", "have", "how", "i", "in", "is", "it",
    "its", "me", "my", "of", "on", "or", "so", "that", "the", "this",
    "to", "was", "what", "when", "where", "which", "who", "why", "will",
    "with", "you", "your", "about", "say", "tell", "file", "files",
    "document", "documents", "doc", "docs",
}

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    toks = [t for t in _WORD.findall(text.lower()) if len(t) > 2 and t not in _STOP]
    out = []
    for t in toks:  # toy stemming: "permissions" -> "permission"
        out.append(t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t)
    return out


def _scan() -> Tuple[List[Tuple[Path, str]], List[Path]]:
    """Return ([(path, text)], consulted_files). Skips binaries/big files."""
    root = config.docs_dir
    docs: List[Tuple[Path, str]] = []
    consulted: List[Path] = []
    total = 0
    if not root.exists():
        return docs, consulted
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    for p in sorted(root.rglob("*")):
        if total >= _MAX_TOTAL:
            break
        if not p.is_file() or p.suffix.lower() not in _TEXTY:
            continue
        if any(part in skip_dirs or part.startswith(".") for part in p.parts):
            continue
        try:
            if p.stat().st_size > _MAX_FILE * 2:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")[:_MAX_FILE]
        except Exception:
            continue
        if "\x00" in text[:2000]:
            continue
        docs.append((p, text))
        consulted.append(p)
        total += len(text)
    return docs, consulted


def _chunks(text: str) -> List[str]:
    parts = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    out: List[str] = []
    buf = ""
    for part in parts:
        if len(buf) + len(part) > _CHUNK and buf:
            out.append(buf)
            buf = part
        else:
            buf = f"{buf}\n\n{part}" if buf else part
    if buf:
        out.append(buf)
    return out or ([text.strip()] if text.strip() else [])


def search_docs(question: str, top: int = 5) -> Tuple[List[Tuple[Path, str]], int]:
    """Return (top chunks as (path, chunk), files_scanned)."""
    docs, consulted = _scan()
    qtoks = _tokens(question)
    if not qtoks:
        return [], len(consulted)
    phrase = " ".join(t for t in _WORD.findall(question.lower()) if t not in _STOP)
    scored: List[Tuple[float, Path, str]] = []
    for path, text in docs:
        low_cache: Dict[str, float] = {}
        for chunk in _chunks(text):
            clow = chunk.lower()
            score = 0.0
            for tok in qtoks:
                c = low_cache.get(tok)
                if c is None:
                    c = clow.count(tok)
                    low_cache[tok] = c
                score += c
            if score == 0.0:
                continue
            score /= math.sqrt(len(chunk) / 120.0 + 1.0)   # tame big chunks
            if len(phrase) > 4 and phrase in clow:
                score *= 3.0
            scored.append((score, path, chunk))
        scored.sort(key=lambda t: -t[0])
        scored = scored  # noqa: PLW0127 (clarity)
    scored.sort(key=lambda t: -t[0])
    return [(p, c) for _, p, c in scored[:top]], len(consulted)


def _empty_folder_msg(root: Path) -> str:
    return (f"Your documents folder is empty. Drop text-ish files into\n{root}\n"
            "(or point the JARVIS_DOCS_DIR setting somewhere else) and ask again.")


@skill(
    "ask_documents",
    "Answer a question by searching the local documents folder (keyword search over text-ish files). Returns the most relevant passages with their file names.",
    {
        "type": "object",
        "properties": {"question": {"type": "string", "description": "What to look for in the documents"}},
        "required": ["question"],
    },
    triggers=["ask my documents {question}", "search my documents for {question}",
              "what do my documents say about {question}", "find in my documents {question}",
              "check my documents for {question}", "look in my documents for {question}"],
)
def ask_documents(question: str = "") -> str:
    q = (question or "").strip()
    if not q:
        return "What should I look for in your documents?"
    hits, scanned = search_docs(q)
    if scanned == 0:
        return _empty_folder_msg(config.docs_dir)
    if not hits:
        return (f"I scanned {scanned} file(s) in your documents folder but nothing "
                f"mentioned '{q}'. Different wording might catch it.")
    out = [f"From your documents ({scanned} file(s) scanned) — best matches for '{q}':"]
    for path, chunk in hits:
        rel = path.relative_to(config.docs_dir) if str(path).startswith(str(config.docs_dir)) else path.name
        snippet = " ".join(chunk.split())[:380]
        out.append(f"\n📄 {rel}\n   “{snippet}”")
    return "\n".join(out)


@skill(
    "list_documents",
    "List the files currently visible to the documents search (the docs folder).",
    {"type": "object", "properties": {}, "required": []},
    triggers=["what documents do you have", "list my documents", "what's in my documents folder",
              "show my documents folder"],
)
def list_documents() -> str:
    _, consulted = _scan()
    if not consulted:
        return _empty_folder_msg(config.docs_dir)
    lines = [f"{len(consulted)} searchable file(s) in {config.docs_dir}:"]
    total = 0
    for p in consulted[:25]:
        try:
            kb = max(1, p.stat().st_size // 1024)
        except Exception:
            kb = 0
        total += kb
        lines.append(f"  • {p.name} ({kb} KB)")
    if len(consulted) > 25:
        lines.append(f"  … plus {len(consulted) - 25} more")
    return "\n".join(lines)
