from pathlib import Path
from hashlib import sha1
import re

from app.config import OUTPUT_DIR
from app.services.markdown_formula import normalize_markdown_formulas


def write_review_markdown(subject: str, target_score: int, markdown: str) -> Path:
    subject_dir = OUTPUT_DIR / subject
    subject_dir.mkdir(parents=True, exist_ok=True)
    output_path = _next_output_path(subject_dir, subject, target_score)
    markdown = normalize_markdown_formulas(markdown)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def _next_output_path(subject_dir: Path, subject: str, target_score: int) -> Path:
    subject_slug = _subject_slug(subject)
    index = 1
    while True:
        output_path = subject_dir / f"{subject_slug}-target{target_score}-review-{index}.md"
        if not output_path.exists():
            return output_path
        index += 1


def _subject_slug(subject: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", subject).strip("-").lower()
    if slug:
        return slug[:48]
    digest = sha1(subject.encode("utf-8")).hexdigest()[:8]
    return f"subject-{digest}"
