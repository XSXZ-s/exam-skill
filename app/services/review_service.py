from app.chains.review_chain import (
    generate_exam_profile,
    generate_markdown,
    retrieve_exam_context,
    retrieve_knowledge_context,
)
from app.schemas import ReviewRequest, ReviewResult
from app.services.index_manifest import ensure_files_indexed, file_hashes
from app.services.markdown_writer import write_review_markdown


def run_review(request: ReviewRequest) -> ReviewResult:
    ensure_files_indexed(request.subject, "knowledge", request.knowledge_files)
    ensure_files_indexed(request.subject, "exam", request.exam_files)

    user_instruction = _read_instruction_files(request.instruction_files)
    exam_docs = retrieve_exam_context(
        request.subject,
        request.target_score,
        exam_hashes=file_hashes(request.exam_files),
    )
    exam_profile = generate_exam_profile(
        subject=request.subject,
        target_score=request.target_score,
        exam_files=[p.name for p in request.exam_files],
        user_instruction=user_instruction,
        exam_docs=exam_docs,
    )
    knowledge_docs = retrieve_knowledge_context(
        request.subject,
        request.target_score,
        exam_profile=exam_profile,
        knowledge_hashes=file_hashes(request.knowledge_files),
    )

    markdown = generate_markdown(
        subject=request.subject,
        target_score=request.target_score,
        knowledge_files=[p.name for p in request.knowledge_files],
        exam_files=[p.name for p in request.exam_files],
        user_instruction=user_instruction,
        exam_profile=exam_profile,
        knowledge_docs=knowledge_docs,
        exam_docs=exam_docs,
    )
    output_path = write_review_markdown(
        request.subject,
        request.target_score,
        markdown,
    )
    return ReviewResult(
        subject=request.subject,
        target_score=request.target_score,
        output_path=output_path,
    )


def _read_instruction_files(paths) -> str:
    parts = []
    for path in paths:
        text = path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"## {path.name}\n{text}")
    return "\n\n".join(parts)


def read_instruction_files(paths) -> str:
    return _read_instruction_files(paths)
