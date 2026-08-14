"""
DocumentIngester — loads documents from disk and populates a KnowledgeStore.

Supported formats (zero external dependencies required for core formats):
- Plain text (.txt)
- Markdown (.md, .markdown)
- Python source (.py)  — useful for code knowledge bases
- PDF (.pdf)           — requires no extra dep; uses stdlib-only extraction
                         (basic text extraction; not layout-aware)
- DOCX (.docx)         — optional, requires python-docx if installed

The ingester chunks text into overlapping windows to preserve context
at chunk boundaries. Chunk size and overlap are configurable.

Usage::

    from aether.knowledge import KnowledgeStore, DocumentIngester

    store = KnowledgeStore(":memory:")
    ingester = DocumentIngester(store)
    ingester.ingest("./docs/")          # directory (recursive)
    ingester.ingest("./report.pdf")     # single file
    ingester.ingest("Hello world", source_name="inline-text")  # raw text
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator

from aether.knowledge.chunk import KnowledgeChunk
from aether.knowledge.store import KnowledgeStore


# ---------------------------------------------------------------------------
# Supported extensions
# ---------------------------------------------------------------------------

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".py", ".yaml", ".yml", ".json", ".csv"}
_PDF_EXTENSION = ".pdf"
_DOCX_EXTENSION = ".docx"

_DEFAULT_CHUNK_SIZE = 800       # characters per chunk
_DEFAULT_CHUNK_OVERLAP = 100    # characters of overlap between chunks


# ---------------------------------------------------------------------------
# Text splitting
# ---------------------------------------------------------------------------

def _split_into_chunks(
    text: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """
    Split *text* into overlapping chunks of roughly *chunk_size* characters.

    Tries to break at paragraph or sentence boundaries rather than mid-word.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Try to break at a paragraph boundary (\n\n) within the window
        window = text[start:end]
        last_para = window.rfind("\n\n")
        if last_para > chunk_size // 2:
            end = start + last_para
        else:
            # Fall back to last sentence end (. ! ?)
            last_sentence = max(
                window.rfind(". "),
                window.rfind("! "),
                window.rfind("? "),
            )
            if last_sentence > chunk_size // 2:
                end = start + last_sentence + 1
            else:
                # Fall back to last space
                last_space = window.rfind(" ")
                if last_space > 0:
                    end = start + last_space

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap  # overlap for context continuity
        if start < 0:
            start = 0

    return chunks


# ---------------------------------------------------------------------------
# Format-specific readers
# ---------------------------------------------------------------------------

def _read_text_file(path: Path) -> str:
    """Read a plain-text or Markdown file."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _read_pdf(path: Path) -> str:
    """
    Extract text from a PDF using Python's stdlib only.

    This is a best-effort extraction: it reads raw bytes and strips
    binary content, keeping printable ASCII/UTF-8 runs. For well-formed
    PDFs this works well; for scanned/image PDFs the result is minimal.

    No external dependencies required.
    """
    try:
        raw = path.read_bytes()
        # Decode ignoring binary garbage
        text_candidate = raw.decode("latin-1", errors="replace")
        # Extract runs of text between stream delimiters
        # PDF streams contain compressed binary; we find the text operators
        # BT...ET blocks contain text. For simple PDFs this heuristic works.
        streams = re.findall(r"stream(.*?)endstream", text_candidate, re.DOTALL)
        parts: list[str] = []
        for stream in streams:
            # Keep printable ASCII runs of length >= 4
            printable_runs = re.findall(r"[ -~]{4,}", stream)
            parts.extend(printable_runs)
        return "\n".join(parts)
    except OSError:
        return ""


def _read_docx(path: Path) -> str:
    """
    Extract text from a DOCX file.

    Requires python-docx (optional dependency). Returns empty string if
    not installed.
    """
    try:
        import docx  # type: ignore[import]

        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        # python-docx not installed — try raw XML extraction as fallback
        return _read_docx_raw(path)
    except Exception:
        return ""


def _read_docx_raw(path: Path) -> str:
    """Fallback DOCX reader using stdlib zipfile + XML parsing."""
    try:
        import zipfile
        import xml.etree.ElementTree as ET

        with zipfile.ZipFile(str(path)) as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            xml_bytes = zf.read("word/document.xml")

        root = ET.fromstring(xml_bytes)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        texts: list[str] = []
        for elem in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
            if elem.text:
                texts.append(elem.text)
        return " ".join(texts)
    except Exception:
        return ""


def _read_file(path: Path) -> str | None:
    """Dispatch to the correct reader based on file extension."""
    ext = path.suffix.lower()
    if ext in _TEXT_EXTENSIONS:
        return _read_text_file(path)
    if ext == _PDF_EXTENSION:
        return _read_pdf(path)
    if ext == _DOCX_EXTENSION:
        return _read_docx(path)
    return None  # unsupported extension


# ---------------------------------------------------------------------------
# Ingester
# ---------------------------------------------------------------------------

class DocumentIngester:
    """
    Ingests documents into a :class:`~aether.knowledge.store.KnowledgeStore`.

    Parameters
    ----------
    store:
        The knowledge store to populate.
    chunk_size:
        Target character count per chunk.
    chunk_overlap:
        Character overlap between consecutive chunks.
    """

    def __init__(
        self,
        store: KnowledgeStore,
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self._store = store
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        source: str | Path,
        *,
        source_name: str | None = None,
        recursive: bool = True,
        scope: str = "workspace",
    ) -> int:
        """
        Ingest a file, directory, or raw text string into the store.

        Parameters
        ----------
        source:
            A file path, directory path, or a raw text string.
        source_name:
            Override the source label stored in the chunk. When *source*
            is a raw string, this becomes its identifier (required if the
            source isn't a path).
        recursive:
            When *source* is a directory, whether to walk subdirectories.
        scope:
            Knowledge scope ('workspace' or 'system').

        Returns
        -------
        int
            The number of chunks added.
        """
        path = Path(source) if isinstance(source, (str, Path)) else None

        if path and path.is_dir():
            return self._ingest_directory(path, recursive=recursive, scope=scope)
        if path and path.is_file():
            return self._ingest_file(path, source_name=source_name, scope=scope)
        if isinstance(source, str) and not Path(source).exists():
            # Treat as raw text
            label = source_name or "<inline>"
            return self._ingest_text(source, label, scope=scope)
        return 0

    def ingest_text(self, text: str, source_name: str, scope: str = "workspace") -> int:
        """
        Ingest a raw text string with an explicit source label.

        Returns the number of chunks added.
        """
        return self._ingest_text(text, source_name, scope=scope)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ingest_directory(self, directory: Path, *, recursive: bool, scope: str = "workspace") -> int:
        total = 0
        pattern = "**/*" if recursive else "*"
        for path in sorted(directory.glob(pattern)):
            if path.is_file():
                total += self._ingest_file(path, scope=scope)
        return total

    def _ingest_file(self, path: Path, *, source_name: str | None = None, scope: str = "workspace") -> int:
        text = _read_file(path)
        if text is None:
            return 0  # unsupported format — skip silently
        label = source_name or str(path)
        return self._ingest_text(text, label, scope=scope)

    def _ingest_text(self, text: str, source: str, scope: str = "workspace") -> int:
        """Chunk *text* and add all chunks to the store."""
        raw_chunks = _split_into_chunks(
            text,
            chunk_size=self._chunk_size,
            overlap=self._chunk_overlap,
        )
        if not raw_chunks:
            return 0

        chunks = [
            KnowledgeChunk(
                content=chunk_text,
                source=source,
                chunk_index=idx,
                scope=scope,
            )
            for idx, chunk_text in enumerate(raw_chunks)
        ]
        self._store.add_many(chunks)
        return len(chunks)

    # ------------------------------------------------------------------
    # Convenience: iterate chunks without storing
    # ------------------------------------------------------------------

    def preview_chunks(
        self,
        source: str | Path,
        *,
        source_name: str | None = None,
    ) -> list[KnowledgeChunk]:
        """
        Return the chunks that *would* be created without storing them.
        Useful for inspecting chunking behaviour.
        """
        path = Path(source) if isinstance(source, (str, Path)) else None
        if path and path.is_file():
            text = _read_file(path) or ""
            label = source_name or str(path)
        else:
            text = str(source)
            label = source_name or "<inline>"

        raw_chunks = _split_into_chunks(text, self._chunk_size, self._chunk_overlap)
        return [
            KnowledgeChunk(content=c, source=label, chunk_index=i)
            for i, c in enumerate(raw_chunks)
        ]
