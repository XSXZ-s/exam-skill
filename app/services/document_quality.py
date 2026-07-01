from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services.document_loader import load_documents
from app.services.semantic_splitter import split_documents


@dataclass
class FileQuality:
    path: Path
    extracted_chars: int
    chunk_count: int
    is_low_quality: bool
    message: str

    def to_dict(self, base_dir: Path | None = None) -> dict:
        display_path = self.path
        if base_dir is not None:
            try:
                display_path = self.path.relative_to(base_dir)
            except ValueError:
                display_path = self.path
        return {
            "path": str(display_path),
            "extracted_chars": self.extracted_chars,
            "chunk_count": self.chunk_count,
            "is_low_quality": self.is_low_quality,
            "message": self.message,
        }


def inspect_files(paths: list[Path], subject: str | None = None) -> list[FileQuality]:
    return [_inspect_one(path, subject=subject) for path in paths]


def low_quality_files(reports: list[FileQuality]) -> list[FileQuality]:
    return [report for report in reports if report.is_low_quality]


def _inspect_one(path: Path, subject: str | None = None) -> FileQuality:
    try:
        documents = load_documents([path], subject=subject)
        extracted_chars = sum(len(doc.page_content.strip()) for doc in documents)
        chunk_count = len(split_documents(documents)) if documents else 0
    except Exception as exc:
        return FileQuality(
            path=path,
            extracted_chars=0,
            chunk_count=0,
            is_low_quality=True,
            message=f"读取失败：{exc}",
        )

    if extracted_chars <= 0 or chunk_count <= 0:
        return FileQuality(
            path=path,
            extracted_chars=extracted_chars,
            chunk_count=chunk_count,
            is_low_quality=True,
            message="未提取到有效文字，可能是扫描件、图片型 PDF 或格式解析失败。",
        )
    if extracted_chars < settings.min_extracted_chars:
        return FileQuality(
            path=path,
            extracted_chars=extracted_chars,
            chunk_count=chunk_count,
            is_low_quality=True,
            message=(
                f"仅提取到 {extracted_chars} 个字符，低于阈值 "
                f"{settings.min_extracted_chars}，分析结果可能不可靠。"
            ),
        )
    return FileQuality(
        path=path,
        extracted_chars=extracted_chars,
        chunk_count=chunk_count,
        is_low_quality=False,
        message="文字提取正常。",
    )
