from hashlib import sha1
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import CHROMA_DIR, settings


def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=settings.embedding_model)


def get_store(subject: str, store_type: str) -> Chroma:
    persist_dir = get_store_dir(subject, store_type)
    persist_dir.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=_collection_name(subject, store_type),
        persist_directory=str(persist_dir),
        embedding_function=get_embeddings(),
    )


def get_store_dir(subject: str, store_type: str) -> Path:
    if store_type not in {"knowledge", "exam"}:
        raise ValueError("store_type must be 'knowledge' or 'exam'")
    return CHROMA_DIR / subject / store_type


def index_documents(
    subject: str,
    store_type: str,
    documents: list[Document],
    ids: list[str] | None = None,
) -> int:
    if not documents:
        return 0
    store = get_store(subject, store_type)
    if ids is None:
        ids = [
            _document_id(store_type, doc.metadata.get("source", "unknown"), i)
            for i, doc in enumerate(documents)
        ]
    store.add_documents(documents, ids=ids)
    return len(documents)


def delete_documents(subject: str, store_type: str, ids: list[str]) -> None:
    if not ids:
        return
    get_store(subject, store_type).delete(ids=ids)


def _collection_name(subject: str, store_type: str) -> str:
    digest = sha1(f"{subject}:{store_type}".encode("utf-8")).hexdigest()[:16]
    return f"exam_skill_{store_type}_{digest}"


def _document_id(store_type: str, source: str, index: int) -> str:
    digest = sha1(f"{store_type}:{source}:{index}".encode("utf-8")).hexdigest()
    return f"{store_type}_{digest}"
