from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import RESOURCES_DIR
from app.schemas import ReviewRequest
from app.services.document_loader import discover_files, discover_subjects
from app.services.review_service import run_review


app = FastAPI(title="Exam Skill RAG API")


class AnalyzePayload(BaseModel):
    knowledge_files: list[str]
    exam_files: list[str]
    target_score: int


@app.get("/subjects")
def list_subjects() -> dict[str, list[str]]:
    return {"subjects": discover_subjects(RESOURCES_DIR)}


@app.get("/subjects/{subject}/files")
def list_subject_files(subject: str) -> dict[str, list[str]]:
    subject_dir = RESOURCES_DIR / subject
    if not subject_dir.exists():
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"files": [str(p.relative_to(subject_dir)) for p in discover_files(subject_dir)]}


@app.post("/subjects/{subject}/analyze")
def analyze_subject(subject: str, payload: AnalyzePayload) -> dict[str, str]:
    subject_dir = RESOURCES_DIR / subject
    if not subject_dir.exists():
        raise HTTPException(status_code=404, detail="Subject not found")

    request = ReviewRequest(
        subject=subject,
        knowledge_files=[_resolve_subject_file(subject_dir, p) for p in payload.knowledge_files],
        exam_files=[_resolve_subject_file(subject_dir, p) for p in payload.exam_files],
        target_score=payload.target_score,
    )
    result = run_review(request)
    return {"output_path": str(result.output_path)}


def _resolve_subject_file(subject_dir: Path, relative_path: str) -> Path:
    path = (subject_dir / relative_path).resolve()
    if subject_dir.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail=f"Invalid path: {relative_path}")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
    return path


def run() -> None:
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    run()
