from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
import json
from pathlib import Path
import re
from typing import Any

from langchain_core.documents import Document

from app.config import ROOT_DIR, settings
from app.services.file_hash import hash_file


SEMANTIC_SPLITTER_VERSION = "semantic_splitter_v4"
CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
SECTION_PATTERNS = [
    re.compile(r"^\s*#{1,6}\s+(.+?)\s*$"),
    re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,4})[\.、\s]+(.{1,80})$"),
    re.compile(r"^\s*([一二三四五六七八九十]+)[、.．]\s*(.{1,80})$"),
]
QUESTION_PATTERNS = [
    re.compile(r"^\s*#{0,6}\s*第\s*([0-9]{1,3})\s*[题題]\s*(.*)$", re.IGNORECASE),
    re.compile(r"^\s*#{0,6}\s*第\s*([一二两三四五六七八九十百]{1,6})\s*[题題]\s*(.*)$", re.IGNORECASE),
    re.compile(r"^\s*#{1,6}\s*([0-9]{1,3})[\.、]\s*(?:题目|选择题|填空题|判断题|简答题|计算题|综合题)?\s*(.*)$", re.IGNORECASE),
]
ASSIGNMENT_PATTERNS = [
    re.compile(r"^\s*#{0,6}\s*第\s*[0-9一二两三四五六七八九十百]+\s*次\s*(?:作业|练习|习题|测试|测验|考试).*?$"),
    re.compile(r"^\s*#{0,6}\s*(?:作业|练习|习题|测试|测验|考试)\s*[0-9一二两三四五六七八九十百]+.*?$"),
]
CHAPTER_PATTERNS = [
    re.compile(r"第\s*([0-9]{1,2})\s*章\s*(.{0,80})", re.IGNORECASE),
    re.compile(r"第\s*([一二两三四五六七八九十]{1,4})\s*章\s*(.{0,80})", re.IGNORECASE),
    re.compile(r"\bchapter\s*0?(\d{1,2})\b\s*(.{0,80})", re.IGNORECASE),
    re.compile(r"\bch[-_ ]?0?(\d{1,2})\b\s*(.{0,80})", re.IGNORECASE),
]
FILENAME_CHAPTER_PATTERNS = [
    re.compile(r"(?:^|[/\\\s_-])ch[-_ ]?0?(\d{1,2})(?:\D|$)", re.IGNORECASE),
    re.compile(r"(?:chapter|chap)[-_ ]?0?(\d{1,2})(?:\D|$)", re.IGNORECASE),
    re.compile(r"第\s*([0-9]{1,2})\s*章", re.IGNORECASE),
    re.compile(r"第\s*([一二两三四五六七八九十]{1,4})\s*章", re.IGNORECASE),
]


@dataclass
class SemanticChunk:
    chunk_id: str
    text: str
    source_file: str
    store_type: str
    content_hash: str
    chapter: str | None
    heading_path: list[str]
    semantic_index: int
    source_pages: list[int]
    char_count: int
    splitter_version: str
    confidence: float
    chunk_kind: str = "section"
    question_index: int | None = None
    assignment_title: str | None = None


def semantic_chunks_for_file(
    subject: str,
    store_type: str,
    path: Path,
    documents: list[Document],
    chapter_hint: str | None = None,
) -> list[Document]:
    file_hash = hash_file(path)
    fingerprint = _fingerprint(store_type, file_hash, chapter_hint)
    cache_dir = _cache_dir(subject, store_type, file_hash)
    chunks_file = cache_dir / "chunks.json"
    manifest_file = cache_dir / "manifest.json"

    cached = _read_cached_chunks(chunks_file, manifest_file, fingerprint)
    if cached is not None:
        return [_document_from_chunk(chunk) for chunk in cached]

    chunks = _build_semantic_chunks(store_type, path, file_hash, documents, chapter_hint=chapter_hint)
    _write_cache(cache_dir, chunks_file, manifest_file, fingerprint, chunks, chapter_hint=chapter_hint)
    return [_document_from_chunk(chunk) for chunk in chunks]


def split_documents(documents: list[Document]) -> list[Document]:
    """Compatibility wrapper for callers that do not have a source file path."""
    chunks = _build_semantic_chunks("unknown", Path("unknown"), "unknown", documents)
    return [_document_from_chunk(chunk) for chunk in chunks]


def _build_semantic_chunks(
    store_type: str,
    path: Path,
    file_hash: str,
    documents: list[Document],
    chapter_hint: str | None = None,
) -> list[SemanticChunk]:
    if store_type == "exam":
        return _build_exam_chunks(store_type, path, file_hash, documents, chapter_hint=chapter_hint)

    fallback_chapter = chapter_hint or _chapter_from_filename(str(path))
    state = {
        "chapter": fallback_chapter,
        "chapter_title": f"{fallback_chapter}" if fallback_chapter else None,
        "section_title": None,
        "confidence": 0.65 if fallback_chapter else 0.35,
    }
    units = _document_units(documents)
    chunks: list[SemanticChunk] = []
    buffer: list[str] = []
    buffer_pages: set[int] = set()
    buffer_chapter = state["chapter"]
    buffer_heading_path = _heading_path(state)
    buffer_confidence = state["confidence"]

    def flush() -> None:
        nonlocal buffer, buffer_pages, buffer_chapter, buffer_heading_path, buffer_confidence
        body = "\n\n".join(part.strip() for part in buffer if part.strip()).strip()
        if not body:
            buffer = []
            buffer_pages = set()
            return
        heading_prefix = "\n".join(buffer_heading_path).strip()
        text = f"{heading_prefix}\n\n{body}".strip() if heading_prefix else body
        for piece in _split_long_text(text, settings.chunk_size):
            index = len(chunks)
            chunks.append(
                SemanticChunk(
                    chunk_id=_chunk_id(store_type, file_hash, index),
                    text=piece,
                    source_file=str(path),
                    store_type=store_type,
                    content_hash=file_hash,
                    chapter=buffer_chapter,
                    heading_path=buffer_heading_path,
                    semantic_index=index,
                    source_pages=sorted(buffer_pages),
                    char_count=len(piece),
                    splitter_version=SEMANTIC_SPLITTER_VERSION,
                    confidence=buffer_confidence,
                )
            )
        buffer = []
        buffer_pages = set()

    for unit in units:
        heading = _classify_heading(unit["text"])
        if heading and heading["kind"] == "chapter":
            flush()
            state["chapter"] = heading["chapter"]
            state["chapter_title"] = heading["title"]
            state["section_title"] = None
            state["confidence"] = 0.95
            continue
        elif heading and heading["kind"] == "section":
            flush()
            state["section_title"] = heading["title"]
            state["confidence"] = max(float(state["confidence"]), 0.75)
            continue

        next_heading_path = _heading_path(state)
        next_chapter = state["chapter"]
        if buffer and (
            next_chapter != buffer_chapter
            or next_heading_path != buffer_heading_path
            or _buffer_size(buffer) + len(unit["text"]) > settings.chunk_size
        ):
            flush()

        buffer_chapter = next_chapter
        buffer_heading_path = next_heading_path
        buffer_confidence = float(state["confidence"])
        buffer.append(unit["text"])
        if unit["page"] is not None:
            buffer_pages.add(unit["page"])

    flush()
    return chunks


def _build_exam_chunks(
    store_type: str,
    path: Path,
    file_hash: str,
    documents: list[Document],
    chapter_hint: str | None = None,
) -> list[SemanticChunk]:
    fallback_chapter = chapter_hint or _chapter_from_filename(str(path))
    state = {
        "chapter": fallback_chapter,
        "chapter_title": f"{fallback_chapter}" if fallback_chapter else None,
        "assignment_title": None,
        "confidence": 0.65 if fallback_chapter else 0.35,
    }
    chunks: list[SemanticChunk] = []
    buffer: list[str] = []
    buffer_pages: set[int] = set()
    buffer_chapter = state["chapter"]
    buffer_heading_path = _exam_heading_path(state)
    buffer_confidence = state["confidence"]
    buffer_question_index: int | None = None

    def flush() -> None:
        nonlocal buffer, buffer_pages, buffer_chapter, buffer_heading_path, buffer_confidence, buffer_question_index
        body = "\n\n".join(part.strip() for part in buffer if part.strip()).strip()
        if not body:
            buffer = []
            buffer_pages = set()
            buffer_question_index = None
            return
        heading_prefix = "\n".join(buffer_heading_path).strip()
        text = f"{heading_prefix}\n\n{body}".strip() if heading_prefix else body
        for piece in _split_long_text(text, settings.chunk_size):
            index = len(chunks)
            chunks.append(
                SemanticChunk(
                    chunk_id=_chunk_id(store_type, file_hash, index),
                    text=piece,
                    source_file=str(path),
                    store_type=store_type,
                    content_hash=file_hash,
                    chapter=buffer_chapter,
                    heading_path=buffer_heading_path,
                    semantic_index=index,
                    source_pages=sorted(buffer_pages),
                    char_count=len(piece),
                    splitter_version=SEMANTIC_SPLITTER_VERSION,
                    confidence=buffer_confidence,
                    chunk_kind="question" if buffer_question_index is not None else "exam_block",
                    question_index=buffer_question_index,
                    assignment_title=state["assignment_title"],
                )
            )
        buffer = []
        buffer_pages = set()
        buffer_question_index = None

    for unit in _document_units(documents):
        text = unit["text"]
        assignment_title = _assignment_title(text)
        if assignment_title:
            flush()
            state["assignment_title"] = assignment_title
            continue

        chapter = _chapter_from_text(text)
        if chapter:
            flush()
            state["chapter"] = chapter
            state["chapter_title"] = text.strip()
            state["confidence"] = 0.95
            continue

        question_index = _question_index(text)
        if question_index is not None:
            flush()
            buffer_question_index = question_index
        elif buffer_question_index is None and not buffer:
            buffer_question_index = None

        next_heading_path = _exam_heading_path(state)
        next_chapter = state["chapter"]
        if buffer and (
            next_chapter != buffer_chapter
            or next_heading_path != buffer_heading_path
            or _buffer_size(buffer) + len(text) > settings.chunk_size
        ):
            flush()

        buffer_chapter = next_chapter
        buffer_heading_path = next_heading_path
        buffer_confidence = float(state["confidence"])
        buffer.append(text)
        if unit["page"] is not None:
            buffer_pages.add(unit["page"])

    flush()
    return chunks


def _document_units(documents: list[Document]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for doc in documents:
        page = _page_number(doc.metadata)
        for unit in _text_units(doc.page_content):
            units.append({"text": unit, "page": page})
    return units


def _text_units(text: str) -> list[str]:
    units: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        joined = "\n".join(paragraph).strip()
        if joined:
            units.append(joined)
        paragraph = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if _classify_heading(line):
            flush_paragraph()
            units.append(line)
            continue
        paragraph.append(line)
    flush_paragraph()
    return units


def _classify_heading(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if len(stripped) > 120:
        return None
    chapter = _chapter_from_text(stripped)
    if chapter:
        return {"kind": "chapter", "chapter": chapter, "title": stripped}
    if _looks_like_section(stripped):
        return {"kind": "section", "title": stripped}
    return None


def _chapter_from_text(text: str) -> str | None:
    for pattern in CHAPTER_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        number = _chapter_number(match.group(1))
        if number is not None:
            return f"ch{number:02d}"
    return None


def _chapter_from_filename(value: str) -> str | None:
    for pattern in FILENAME_CHAPTER_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        number = _chapter_number(match.group(1))
        if number is not None:
            return f"ch{number:02d}"
    return None


def _looks_like_section(text: str) -> bool:
    if _question_index(text) is not None or _assignment_title(text):
        return True
    return any(pattern.match(text) for pattern in SECTION_PATTERNS)


def _chapter_number(raw: str) -> int | None:
    raw = raw.strip()
    if raw.isdigit():
        value = int(raw)
        return value if 0 < value < 100 else None
    if raw == "十":
        return 10
    if "十" in raw:
        tens, _, ones = raw.partition("十")
        tens_value = CHINESE_DIGITS.get(tens, 1) if tens else 1
        ones_value = CHINESE_DIGITS.get(ones, 0) if ones else 0
        value = tens_value * 10 + ones_value
        return value if 0 < value < 100 else None
    return CHINESE_DIGITS.get(raw)


def _heading_path(state: dict[str, Any]) -> list[str]:
    values = [state.get("chapter_title"), state.get("section_title")]
    return [str(value) for value in values if value]


def _exam_heading_path(state: dict[str, Any]) -> list[str]:
    values = [state.get("chapter_title"), state.get("assignment_title")]
    return [str(value) for value in values if value]


def _assignment_title(text: str) -> str | None:
    stripped = text.strip()
    if len(stripped) > 120:
        return None
    if any(pattern.match(stripped) for pattern in ASSIGNMENT_PATTERNS):
        return stripped
    return None


def _question_index(text: str) -> int | None:
    stripped = text.strip()
    if len(stripped) > 160:
        return None
    for pattern in QUESTION_PATTERNS:
        match = pattern.match(stripped)
        if not match:
            continue
        number = _chapter_number(match.group(1))
        if number is not None and 0 < number < 1000:
            return number
    return None


def _buffer_size(buffer: list[str]) -> int:
    return sum(len(part) for part in buffer)


def _split_long_text(text: str, max_size: int) -> list[str]:
    if len(text) <= max_size:
        return [text]
    pieces: list[str] = []
    start = 0
    step = max(max_size - settings.chunk_overlap, max_size // 2)
    while start < len(text):
        end = min(start + max_size, len(text))
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start += step
    return [piece for piece in pieces if piece]


def _page_number(metadata: dict[str, Any]) -> int | None:
    raw = metadata.get("page")
    if raw is None:
        raw = metadata.get("page_number")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _document_from_chunk(chunk: SemanticChunk) -> Document:
    metadata = asdict(chunk)
    text = metadata.pop("text")
    heading_path = metadata.pop("heading_path", [])
    source_pages = metadata.pop("source_pages", [])
    metadata["chapter"] = metadata.get("chapter") or ""
    metadata["source"] = metadata.get("source_file") or "unknown"
    metadata["heading_path"] = " > ".join(heading_path)
    metadata["heading_path_json"] = json.dumps(heading_path, ensure_ascii=False)
    metadata["source_pages"] = ",".join(str(page) for page in source_pages)
    metadata["question_index"] = metadata.get("question_index") or ""
    metadata["assignment_title"] = metadata.get("assignment_title") or ""
    return Document(page_content=text, metadata=metadata)


def _read_cached_chunks(
    chunks_file: Path,
    manifest_file: Path,
    fingerprint: str,
) -> list[SemanticChunk] | None:
    if not chunks_file.exists() or not manifest_file.exists():
        return None
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest.get("fingerprint") != fingerprint:
            return None
        data = json.loads(chunks_file.read_text(encoding="utf-8"))
        return [SemanticChunk(**item) for item in data.get("chunks", [])]
    except (OSError, TypeError, json.JSONDecodeError):
        return None


def _write_cache(
    cache_dir: Path,
    chunks_file: Path,
    manifest_file: Path,
    fingerprint: str,
    chunks: list[SemanticChunk],
    chapter_hint: str | None = None,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    chunks_file.write_text(
        json.dumps({"chunks": [asdict(chunk) for chunk in chunks]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest_file.write_text(
        json.dumps(
            {
                "version": SEMANTIC_SPLITTER_VERSION,
                "fingerprint": fingerprint,
                "chunk_count": len(chunks),
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "chapter_hint": chapter_hint,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _cache_dir(subject: str, store_type: str, file_hash: str) -> Path:
    return ROOT_DIR / ".cache" / "semantic_chunks" / _safe_subject(subject) / store_type / file_hash


def _safe_subject(subject: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in subject)
    return safe or "_global"


def _fingerprint(store_type: str, file_hash: str, chapter_hint: str | None = None) -> str:
    raw = "|".join(
        [
            SEMANTIC_SPLITTER_VERSION,
            store_type,
            file_hash,
            str(settings.chunk_size),
            str(settings.chunk_overlap),
            chapter_hint or "",
        ]
    )
    return sha1(raw.encode("utf-8")).hexdigest()


def _chunk_id(store_type: str, file_hash: str, index: int) -> str:
    return f"{store_type}_{file_hash[:24]}_sem_{index}"
