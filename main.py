from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import OUTPUT_DIR, RESOURCES_DIR
from app.services.document_loader import SUPPORTED_EXTENSIONS


app = FastAPI(title="Exam Skill RAG API")
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


class AnalyzePayload(BaseModel):
    knowledge_files: list[str]
    exam_files: list[str]
    instruction_files: list[str] = Field(default_factory=list)
    material_groups: list[dict] = Field(default_factory=list)
    target_score: int
    allow_low_quality: bool = False


class MaterialAnalyzePayload(BaseModel):
    files: list[str] = Field(default_factory=list)
    include_all: bool = False


class ChatPayload(BaseModel):
    question: str
    output_file: str
    knowledge_files: list[str] = Field(default_factory=list)
    exam_files: list[str] = Field(default_factory=list)
    instruction_files: list[str] = Field(default_factory=list)
    target_score: int = 85


class OutputUpdatePayload(BaseModel):
    markdown: str


@app.get("/")
def index() -> FileResponse:
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(index_path)


@app.get("/subjects")
def list_subjects() -> dict[str, list[str]]:
    return {"subjects": _discover_subjects(RESOURCES_DIR)}


@app.get("/subjects/{subject}/files")
def list_subject_files(subject: str) -> dict[str, list[str]]:
    subject_dir = RESOURCES_DIR / subject
    if not subject_dir.exists():
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"files": [str(p.relative_to(subject_dir)) for p in _discover_files(subject_dir)]}


@app.post("/subjects/{subject}/materials/analyze")
def analyze_subject_materials(subject: str, payload: MaterialAnalyzePayload) -> dict:
    from app.services.material_analyzer import analyze_materials

    subject_dir = RESOURCES_DIR / subject
    if not subject_dir.exists():
        raise HTTPException(status_code=404, detail="Subject not found")
    if payload.include_all:
        files = _discover_files(subject_dir)
    else:
        files = [_resolve_subject_file(subject_dir, p) for p in payload.files]
    return analyze_materials(subject, subject_dir, files)


@app.post("/subjects/{subject}/analyze")
def analyze_subject(subject: str, payload: AnalyzePayload) -> dict:
    from app.schemas import ReviewRequest
    from app.services.document_quality import inspect_files, low_quality_files
    from app.services.review_service import run_review

    subject_dir = RESOURCES_DIR / subject
    if not subject_dir.exists():
        raise HTTPException(status_code=404, detail="Subject not found")

    knowledge_files = [_resolve_subject_file(subject_dir, p) for p in payload.knowledge_files]
    exam_files = [_resolve_subject_file(subject_dir, p) for p in payload.exam_files]
    instruction_files = [_resolve_instruction_file(subject_dir, p) for p in payload.instruction_files]
    quality_reports = inspect_files(knowledge_files + exam_files, subject=subject)
    low_quality = low_quality_files(quality_reports)
    if low_quality and not payload.allow_low_quality:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "部分资料提取到的文字过少，可能影响分析准确性。请确认是否继续。",
                "files": [report.to_dict(subject_dir) for report in low_quality],
            },
        )

    request = ReviewRequest(
        subject=subject,
        knowledge_files=knowledge_files,
        exam_files=exam_files,
        instruction_files=instruction_files,
        material_groups=payload.material_groups,
        target_score=payload.target_score,
    )
    result = run_review(request)
    return {
        "output_path": str(result.output_path),
        "output_file": result.output_path.name,
        "markdown": result.output_path.read_text(encoding="utf-8"),
        "quality_reports": [report.to_dict(subject_dir) for report in quality_reports],
    }


@app.get("/subjects/{subject}/outputs")
def list_subject_outputs(subject: str) -> dict[str, list[str]]:
    subject_dir = _resolve_output_subject_dir(subject)
    return {"files": sorted(p.name for p in subject_dir.glob("*.md"))}


@app.get("/subjects/{subject}/outputs/{filename}")
def read_subject_output(subject: str, filename: str) -> dict[str, str]:
    path = _resolve_output_file(subject, filename)
    return {"filename": path.name, "markdown": path.read_text(encoding="utf-8")}


@app.put("/subjects/{subject}/outputs/{filename}")
def update_subject_output(subject: str, filename: str, payload: OutputUpdatePayload) -> dict[str, str]:
    path = _resolve_output_file(subject, filename)
    path.write_text(payload.markdown, encoding="utf-8")
    return {"filename": path.name, "markdown": payload.markdown}


@app.post("/subjects/{subject}/chat")
def chat_subject(subject: str, payload: ChatPayload) -> dict[str, str]:
    from app.chains.review_chain import answer_question, retrieve_exam_context, retrieve_knowledge_context
    from app.services.index_manifest import file_hashes
    from app.services.review_service import read_instruction_files

    subject_dir = RESOURCES_DIR / subject
    if not subject_dir.exists():
        raise HTTPException(status_code=404, detail="Subject not found")
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    knowledge_files = [_resolve_subject_file(subject_dir, p) for p in payload.knowledge_files]
    exam_files = [_resolve_subject_file(subject_dir, p) for p in payload.exam_files]
    instruction_text = read_instruction_files(
        [_resolve_instruction_file(subject_dir, p) for p in payload.instruction_files]
    )
    output_markdown = _resolve_output_file(subject, payload.output_file).read_text(encoding="utf-8")
    if instruction_text:
        output_markdown = f"{output_markdown}\n\n## 用户额外需求\n{instruction_text}"

    if knowledge_files and exam_files:
        exam_docs = retrieve_exam_context(
            subject=subject,
            target_score=payload.target_score,
            exam_hashes=file_hashes(exam_files),
        )
        knowledge_docs = retrieve_knowledge_context(
            subject=subject,
            target_score=payload.target_score,
            exam_profile=output_markdown,
            knowledge_hashes=file_hashes(knowledge_files),
        )
    else:
        knowledge_docs, exam_docs = [], []
    answer = answer_question(
        subject=subject,
        question=payload.question,
        output_markdown=output_markdown,
        knowledge_docs=knowledge_docs,
        exam_docs=exam_docs,
    )
    return {"answer": answer}


def _resolve_subject_file(subject_dir: Path, relative_path: str) -> Path:
    path = (subject_dir / relative_path).resolve()
    if subject_dir.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail=f"Invalid path: {relative_path}")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
    return path


def _discover_subjects(resources_dir: Path) -> list[str]:
    if not resources_dir.exists():
        return []
    return sorted(p.name for p in resources_dir.iterdir() if p.is_dir())


def _discover_files(subject_dir: Path) -> list[Path]:
    if not subject_dir.exists():
        return []
    files = [
        p
        for p in subject_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files, key=lambda p: str(p).lower())


def _resolve_instruction_file(subject_dir: Path, relative_path: str) -> Path:
    path = _resolve_subject_file(subject_dir, relative_path)
    if path.suffix.lower() not in {".txt", ".md"}:
        raise HTTPException(status_code=400, detail=f"Instruction file must be txt or md: {relative_path}")
    return path


def _resolve_output_subject_dir(subject: str) -> Path:
    path = (OUTPUT_DIR / subject).resolve()
    if OUTPUT_DIR.resolve() not in path.parents and path != OUTPUT_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid output subject")
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_output_file(subject: str, filename: str) -> Path:
    subject_dir = _resolve_output_subject_dir(subject)
    path = (subject_dir / filename).resolve()
    if subject_dir.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail=f"Invalid output file: {filename}")
    if path.suffix.lower() != ".md" or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Output file not found: {filename}")
    return path


def run() -> None:
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
