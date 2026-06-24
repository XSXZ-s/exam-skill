from pathlib import Path

from app.config import OUTPUT_DIR


def write_review_markdown(subject: str, target_score: int, markdown: str) -> Path:
    subject_dir = OUTPUT_DIR / subject
    subject_dir.mkdir(parents=True, exist_ok=True)
    output_path = _next_output_path(subject_dir, subject, target_score)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def _next_output_path(subject_dir: Path, subject: str, target_score: int) -> Path:
    index = 1
    while True:
        output_path = subject_dir / f"{subject}-目标{target_score}分-复习方案{index}.md"
        if not output_path.exists():
            return output_path
        index += 1
