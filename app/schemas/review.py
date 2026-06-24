from pathlib import Path

from pydantic import BaseModel, Field


class FileChoice(BaseModel):
    index: int
    path: Path

    @property
    def display_name(self) -> str:
        return self.path.name


class ReviewRequest(BaseModel):
    subject: str
    knowledge_files: list[Path]
    exam_files: list[Path]
    target_score: int = Field(ge=0, le=100)


class ReviewResult(BaseModel):
    subject: str
    target_score: int
    output_path: Path

