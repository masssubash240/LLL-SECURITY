"""
Simple RAG (retrieval-augmented generation) for the banking sandbox.

Loads plain-text policy documents from ./documents/ plus optional extra .txt paths
(e.g. project-root custemer.txt), splits them into chunks,
and scores relevance with a lightweight lexical overlap metric (beginner-friendly,
no ML dependencies).

This bot does NOT call external LLMs; the "generation" happens in main.py using
retrieved excerpts plus rules from your fake SQLite database.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path


def _tokenize(text: str) -> set[str]:
    """Lower-case tokens; strips punctuation-heavy edges."""
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", text.lower())
    return {w for w in cleaned.split() if len(w) > 1}


def _split_chunks(text: str, max_chars: int = 900) -> list[str]:
    """Split document text into paragraph-ish chunks capped for chat context."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for p in parts:
        if size + len(p) > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf = []
            size = 0
        buf.append(p)
        size += len(p) + 2
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


class SimpleBankRAG:
    """Loads document chunks once and retrieves top matches for a query."""

    def __init__(
        self,
        documents_dir: Path,
        extra_txt_files: Sequence[Path] | None = None,
    ) -> None:
        self.documents_dir = Path(documents_dir)
        self.extra_txt_files = [Path(p) for p in (extra_txt_files or [])]
        self._chunks: list[str] = []
        self._reload()

    def _reload(self) -> None:
        self._chunks = []
        to_read: list[tuple[Path, str]] = []

        if self.documents_dir.is_dir():
            for path in sorted(self.documents_dir.glob("*.txt")):
                to_read.append((path, path.name))

        for path in self.extra_txt_files:
            p = Path(path)
            if p.is_file():
                to_read.append((p, p.name))

        seen: set[Path] = set()
        for path, label in to_read:
            key = path.resolve()
            if key in seen:
                continue
            seen.add(key)
            raw = path.read_text(encoding="utf-8")
            labeled = f"[SOURCE: {label}]\n{raw}".strip()
            self._chunks.extend(_split_chunks(labeled))

    def retrieve(self, query: str, top_k: int = 3) -> list[tuple[str, float]]:
        """Returns (chunk_text, score) sorted by descending score."""
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        ranked: list[tuple[str, float]] = []
        for chunk in self._chunks:
            c_tokens = _tokenize(chunk)
            if not c_tokens:
                continue
            inter = len(q_tokens & c_tokens)
            if inter == 0:
                continue
            # Dice coefficient on token overlap (simple, predictable)
            score = (2 * inter) / (len(q_tokens) + len(c_tokens))
            ranked.append((chunk, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:top_k]

    def context_block(self, query: str, top_k: int = 2, max_chars: int = 1200) -> str:
        """Single string suitable to paste into a templated assistant answer."""
        hits = self.retrieve(query, top_k=top_k)
        if not hits:
            return ""

        assembled: list[str] = []
        used = 0
        for text, score in hits:
            line = f"--- excerpt (score {score:.3f}) ---\n{text}"
            if used + len(line) > max_chars:
                break
            assembled.append(line)
            used += len(line)
        return "\n\n".join(assembled).strip()


__all__ = ["SimpleBankRAG"]
