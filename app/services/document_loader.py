from pathlib import Path

from langchain_core.documents import Document


SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".txt", ".md"}


def discover_subjects(resources_dir: Path) -> list[str]:
    if not resources_dir.exists():
        return []
    return sorted(p.name for p in resources_dir.iterdir() if p.is_dir())


def discover_files(subject_dir: Path) -> list[Path]:
    if not subject_dir.exists():
        return []
    files = [
        path
        for path in subject_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files, key=lambda path: str(path).lower())


def load_documents(paths: list[Path], subject: str | None = None) -> list[Document]:
    documents: list[Document] = []
    for path in paths:
        documents.extend(_load_one(path))
    return documents


def _load_one(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from langchain_community.document_loaders import PyPDFLoader

        return PyPDFLoader(str(path)).load()
    if suffix == ".pptx":
        from langchain_community.document_loaders import UnstructuredPowerPointLoader

        return UnstructuredPowerPointLoader(str(path)).load()
    if suffix == ".docx":
        from langchain_community.document_loaders import Docx2txtLoader

        return Docx2txtLoader(str(path)).load()
    if suffix in {".txt", ".md"}:
        from langchain_community.document_loaders import TextLoader

        return TextLoader(str(path), encoding="utf-8", autodetect_encoding=True).load()
    return []
