import json
from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any

from app.config import CHROMA_DIR, settings
from app.services.document_loader import load_documents
from app.services.file_hash import hash_file
from app.services.semantic_splitter import SEMANTIC_SPLITTER_VERSION, semantic_chunks_for_file
from app.services.vectorstore import delete_documents, index_documents


@dataclass
class IndexStats:
    indexed_files: int = 0
    skipped_files: int = 0
    indexed_chunks: int = 0


def ensure_files_indexed(
    subject: str,
    store_type: str,
    paths: list[Path],
    chapter_hints: dict[Path, str] | None = None,
) -> IndexStats:
    manifest = _load_manifest(subject)
    stats = IndexStats()
    chapter_hints = chapter_hints or {}

    for path in paths:
        chapter_hint = chapter_hints.get(path.resolve())
        file_hash = hash_file(path)
        file_key = _file_key(store_type, path)
        fingerprint = _fingerprint(store_type, file_hash, chapter_hint)
        existing = manifest["files"].get(file_key)

        if existing and existing.get("fingerprint") == fingerprint:
            stats.skipped_files += 1
            continue

        reusable = _find_reusable_entry(manifest, store_type, fingerprint)
        if reusable:
            manifest["files"][file_key] = {
                **reusable,
                "path": str(path),
                "reused_from": reusable.get("path"),
            }
            stats.skipped_files += 1
            continue

        if existing:
            delete_documents(subject, store_type, existing.get("chunk_ids", []))

        documents = load_documents([path], subject=subject)
        chunks = semantic_chunks_for_file(subject, store_type, path, documents, chapter_hint=chapter_hint)
        chunk_ids = [str(chunk.metadata.get("chunk_id") or _chunk_id(store_type, file_hash, i)) for i, chunk in enumerate(chunks)]
        for i, chunk in enumerate(chunks):
            chunk.metadata.update(
                {
                    "store_type": store_type,
                    "content_hash": file_hash,
                    "chunk_index": i,
                    "splitter_version": SEMANTIC_SPLITTER_VERSION,
                }
            )

        index_documents(subject, store_type, chunks, ids=chunk_ids)
        manifest["files"][file_key] = {
            "path": str(path),
            "store_type": store_type,
            "content_hash": file_hash,
            "fingerprint": fingerprint,
            "chunk_ids": chunk_ids,
            "chunk_count": len(chunks),
            "embedding_model": settings.embedding_model,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "splitter_version": SEMANTIC_SPLITTER_VERSION,
            "chapter_hint": chapter_hint,
        }
        stats.indexed_files += 1
        stats.indexed_chunks += len(chunks)

    _save_manifest(subject, manifest)
    return stats


def file_hashes(paths: list[Path]) -> list[str]:
    return [hash_file(path) for path in paths]


def _manifest_path(subject: str) -> Path:
    return CHROMA_DIR / subject / "manifest.json"


def _load_manifest(subject: str) -> dict[str, Any]:
    path = _manifest_path(subject)
    if not path.exists():
        return {"version": 1, "files": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(subject: str, manifest: dict[str, Any]) -> None:
    path = _manifest_path(subject)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _file_key(store_type: str, path: Path) -> str:
    resolved = str(path.resolve()).lower()
    return sha1(f"{store_type}:{resolved}".encode("utf-8")).hexdigest()


def _fingerprint(store_type: str, file_hash: str, chapter_hint: str | None = None) -> str:
    raw = "|".join(
        [
            store_type,
            file_hash,
            settings.embedding_model,
            str(settings.chunk_size),
            str(settings.chunk_overlap),
            SEMANTIC_SPLITTER_VERSION,
            chapter_hint or "",
        ]
    )
    return sha1(raw.encode("utf-8")).hexdigest()


def _find_reusable_entry(
    manifest: dict[str, Any],
    store_type: str,
    fingerprint: str,
) -> dict[str, Any] | None:
    for entry in manifest["files"].values():
        if entry.get("store_type") == store_type and entry.get("fingerprint") == fingerprint:
            return entry
    return None


def _chunk_id(store_type: str, file_hash: str, index: int) -> str:
    return f"{store_type}_{file_hash[:24]}_{index}"
