from pathlib import Path

from app.chains.review_chain import (
    generate_final_markdown_from_chapter_briefs,
    generate_full_context_markdown,
)
from app.schemas import ReviewRequest, ReviewResult
from app.services.chapter_brief import build_chapter_briefs, chapter_briefs_markdown
from app.services.index_manifest import ensure_files_indexed
from app.services.markdown_writer import write_review_markdown
from app.services.review_auditor import audit_and_patch_markdown, build_audit_context
from app.services.review_strategy import (
    FULL_CONTEXT,
    choose_generation_plan,
    collect_material_texts,
    format_full_context,
)


def run_review(request: ReviewRequest) -> ReviewResult:
    chapter_hints = _chapter_hints(
        request.material_groups,
        request.knowledge_files + request.exam_files,
    )
    ensure_files_indexed(request.subject, "knowledge", request.knowledge_files, chapter_hints=chapter_hints)
    ensure_files_indexed(request.subject, "exam", request.exam_files, chapter_hints=chapter_hints)

    user_instruction = _read_instruction_files(request.instruction_files)
    materials = collect_material_texts(
        request.knowledge_files,
        request.exam_files,
        user_instruction,
        subject=request.subject,
    )
    generation_plan = choose_generation_plan(materials)
    audit_context = build_audit_context(
        request.subject,
        request.knowledge_files,
        request.exam_files,
        chapter_hints=chapter_hints,
    )

    if generation_plan.strategy == FULL_CONTEXT:
        markdown = generate_full_context_markdown(
            subject=request.subject,
            target_score=request.target_score,
            knowledge_files=[p.name for p in request.knowledge_files],
            exam_files=[p.name for p in request.exam_files],
            user_instruction=user_instruction,
            full_context=format_full_context(materials),
        )
        markdown = _with_generation_note(markdown, generation_plan)
        markdown = audit_and_patch_markdown(
            request.subject,
            request.target_score,
            markdown,
            audit_context,
        )
    else:
        briefs = build_chapter_briefs(
            subject=request.subject,
            target_score=request.target_score,
            knowledge_files=request.knowledge_files,
            exam_files=request.exam_files,
            user_instruction=user_instruction,
            chapter_hints=chapter_hints,
        )
        for brief in briefs:
            brief.review_markdown = audit_and_patch_markdown(
                request.subject,
                request.target_score,
                brief.review_markdown,
                audit_context,
                chapter=brief.chapter,
            )
        markdown = generate_final_markdown_from_chapter_briefs(
            subject=request.subject,
            target_score=request.target_score,
            knowledge_files=[p.name for p in request.knowledge_files],
            exam_files=[p.name for p in request.exam_files],
            user_instruction=user_instruction,
            chapter_briefs_markdown=chapter_briefs_markdown(briefs),
        )
        markdown = _with_generation_note(markdown, generation_plan)
        markdown = audit_and_patch_markdown(
            request.subject,
            request.target_score,
            markdown,
            audit_context,
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


def _with_generation_note(markdown: str, generation_plan) -> str:
    note = "\n".join(
        [
            "<!-- generation-plan",
            f"strategy: {generation_plan.strategy}",
            f"estimated_tokens: {generation_plan.estimated_tokens}",
            f"full_context_limit: {generation_plan.full_context_limit}",
            f"reason: {generation_plan.reason}",
            "-->",
        ]
    )
    return f"{note}\n\n{markdown}"


def _chapter_hints(material_groups: list[dict], paths) -> dict:
    if not material_groups:
        return {}

    by_relative: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for group in material_groups:
        chapter = group.get("chapter") if isinstance(group, dict) else None
        if not chapter:
            continue
        files = []
        for key in ("knowledge_files", "exam_files"):
            values = group.get(key, []) if isinstance(group, dict) else []
            if isinstance(values, list):
                files.extend(values)
        for file in files:
            relative = str(file).replace("\\", "/").lower()
            by_relative[relative] = str(chapter)
            by_name[Path(relative).name.lower()] = str(chapter)

    hints = {}
    for path in paths:
        normalized = str(path).replace("\\", "/").lower()
        name = path.name.lower()
        chapter = None
        for relative, value in by_relative.items():
            if normalized.endswith(relative):
                chapter = value
                break
        if chapter is None:
            chapter = by_name.get(name)
        if chapter:
            hints[path.resolve()] = chapter
    return hints
