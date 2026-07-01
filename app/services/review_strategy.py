from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import settings


FULL_CONTEXT = "full_context"
CHAPTER_CONTEXT = "chapter_context"


@dataclass
class MaterialText:
    path: Path
    role: str
    text: str


@dataclass
class GenerationPlan:
    strategy: str
    estimated_tokens: int
    full_context_limit: int
    reason: str


def collect_material_texts(
    knowledge_files: list[Path],
    exam_files: list[Path],
    instruction_text: str,
    subject: str,
) -> list[MaterialText]:
    from app.services.document_loader import load_documents

    materials: list[MaterialText] = []
    for role, paths in (("knowledge", knowledge_files), ("exam", exam_files)):
        for path in paths:
            documents = load_documents([path], subject=subject)
            text = "\n\n".join(doc.page_content.strip() for doc in documents if doc.page_content.strip())
            if text:
                materials.append(MaterialText(path=path, role=role, text=text))
    if instruction_text.strip():
        materials.append(MaterialText(path=Path("user_instruction"), role="instruction", text=instruction_text.strip()))
    return materials


def format_full_context(materials: list[MaterialText]) -> str:
    blocks = []
    for material in materials:
        blocks.append(
            "\n".join(
                [
                    f"===== {material.role.upper()} | {material.path.name} =====",
                    material.text.strip(),
                ]
            )
        )
    return "\n\n".join(blocks)


def choose_generation_plan(materials: list[MaterialText]) -> GenerationPlan:
    text = format_full_context(materials)
    estimated = estimate_tokens(text)
    usable = max(
        settings.context_window_tokens - settings.output_token_reserve - settings.audit_token_reserve,
        settings.context_window_tokens // 3,
    )
    full_limit = max(1, usable * settings.full_context_ratio_percent // 100)
    if estimated <= full_limit:
        return GenerationPlan(
            strategy=FULL_CONTEXT,
            estimated_tokens=estimated,
            full_context_limit=full_limit,
            reason="资料规模适合全文直读，生成阶段优先保留完整语境。",
        )
    return GenerationPlan(
        strategy=CHAPTER_CONTEXT,
        estimated_tokens=estimated,
        full_context_limit=full_limit,
        reason="资料规模超过全文直读阈值，改用章节产物生成并轻量组装。",
    )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return int(non_ascii_chars / 1.2 + ascii_chars / 3.5) + 1
