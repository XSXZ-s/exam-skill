from app.chains.review_chain import generate_markdown, retrieve_review_context
from app.schemas import ReviewRequest, ReviewResult
from app.services.index_manifest import ensure_files_indexed
from app.services.markdown_writer import write_review_markdown


def run_review(request: ReviewRequest) -> ReviewResult:
    ensure_files_indexed(request.subject, "knowledge", request.knowledge_files)
    ensure_files_indexed(request.subject, "exam", request.exam_files)

    knowledge_docs, exam_docs = retrieve_review_context(
        request.subject,
        request.target_score,
    )

    markdown = generate_markdown(
        subject=request.subject,
        target_score=request.target_score,
        knowledge_files=[p.name for p in request.knowledge_files],
        exam_files=[p.name for p in request.exam_files],
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
