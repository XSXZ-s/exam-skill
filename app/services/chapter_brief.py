from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from hashlib import sha1
import json
from pathlib import Path
import re
from typing import Any

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from app.config import ROOT_DIR, settings
from app.prompts.review_prompt import MARKDOWN_FORMULA_RULES
from app.services.exam_structurer import (
    QUESTION_STRUCTURER_VERSION,
    QuestionProfile,
    extract_question_profiles,
)
from app.services.file_hash import hash_file
from app.services.semantic_splitter import SEMANTIC_SPLITTER_VERSION
from app.services.vectorstore import get_store


CHAPTER_BRIEF_VERSION = "chapter_brief_v1"
QUESTION_MATCH_TOP_K = 5
CHAPTER_EVIDENCE_LIMIT = 14


@dataclass
class KnowledgeEvidence:
    point: str
    query: str
    matched_chunk_ids: list[str] = field(default_factory=list)
    chapters: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    text_summary: str = ""


@dataclass
class ChapterBrief:
    subject: str
    chapter: str
    target_score: int
    source_files: dict[str, list[str]]
    question_count: int
    question_types: list[str]
    high_frequency_points: list[str]
    trap_points: list[str]
    retrieval_keywords: list[str]
    representative_questions: list[dict[str, Any]]
    knowledge_evidence: list[KnowledgeEvidence]
    review_markdown: str


def build_chapter_briefs(
    subject: str,
    target_score: int,
    knowledge_files: list[Path],
    exam_files: list[Path],
    user_instruction: str = "",
    chapter_hints: dict[Path, str] | None = None,
) -> list[ChapterBrief]:
    knowledge_hashes = [hash_file(path) for path in knowledge_files]
    profiles = extract_question_profiles(subject, exam_files, chapter_hints=chapter_hints)
    matches = _match_profiles_to_knowledge(subject, profiles, knowledge_hashes)
    grouped = _group_profiles_by_chapter(profiles, matches)
    briefs = []
    for chapter, chapter_profiles in sorted(grouped.items(), key=lambda item: item[0]):
        evidence_docs = _chapter_evidence_docs(chapter_profiles, matches)
        fingerprint = _brief_fingerprint(
            chapter,
            chapter_profiles,
            evidence_docs,
            knowledge_hashes,
            target_score,
            user_instruction,
        )
        cached = _read_cached_brief(subject, chapter, fingerprint)
        if cached is not None:
            briefs.append(cached)
            continue
        brief = _generate_chapter_brief(
            subject=subject,
            target_score=target_score,
            chapter=chapter,
            knowledge_files=knowledge_files,
            exam_files=exam_files,
            user_instruction=user_instruction,
            profiles=chapter_profiles,
            evidence_docs=evidence_docs,
        )
        _write_cached_brief(subject, brief, fingerprint)
        briefs.append(brief)
    return briefs


def chapter_briefs_markdown(briefs: list[ChapterBrief]) -> str:
    return "\n\n".join(_wrapped_brief_markdown(brief) for brief in briefs if brief.review_markdown.strip())


def _wrapped_brief_markdown(brief: ChapterBrief) -> str:
    title = _chapter_title(brief)
    body = _normalize_inner_headings(brief.review_markdown)
    meta = [
        f"- 题目数量：{brief.question_count}",
        f"- 高频题型：{_join_or_empty(brief.question_types)}",
        f"- 高频考点：{_join_or_empty(brief.high_frequency_points[:8])}",
    ]
    return "\n".join(
        [
            f"### {title}",
            "",
            *meta,
            "",
            body,
        ]
    ).strip()


def _chapter_title(brief: ChapterBrief) -> str:
    chapter = brief.chapter or "未归章"
    chapter_number = _chapter_number_from_key(chapter)
    if chapter_number is not None:
        return f"第{chapter_number}章方案"
    return f"{chapter} 方案"


def _normalize_inner_headings(markdown: str) -> str:
    lines = []
    for raw_line in markdown.strip().splitlines():
        line = raw_line.rstrip()
        if line.startswith("#"):
            if _looks_like_brief_title(line):
                continue
            stripped = line.lstrip("#").strip()
            original_level = len(line) - len(line.lstrip("#"))
            heading_text = _normalize_heading_text(stripped)
            level = _normalized_heading_level(original_level, heading_text)
            lines.append(f"{'#' * level} {heading_text}" if heading_text else line)
            continue
        lines.append(_clean_process_text(line))
    return "\n".join(lines).strip()


def _looks_like_brief_title(line: str) -> bool:
    text = _strip_heading_noise(line.lstrip("#").strip()).lower()
    return any(marker in text for marker in ("中间产物", "复习方案", "复习提纲", "单章", "方案", "提纲")) and (
        "ch" in text or "章" in text
    )


def _chapter_number_from_key(chapter: str) -> int | None:
    raw = str(chapter or "").strip().lower()
    if raw.startswith("ch") and raw[2:].isdigit():
        return int(raw[2:])
    digits = "".join(char for char in raw if char.isdigit())
    if digits:
        value = int(digits)
        return value if value > 0 else None
    return None


def _normalize_heading_text(text: str) -> str:
    text = _strip_heading_noise(text)
    text = _clean_process_text(text)
    compact = text.replace(" ", "")
    section_map = [
        ("题目画像", "题目画像"),
        ("必须掌握", "必须掌握"),
        ("建议掌握", "建议掌握"),
        ("冲刺高分", "冲刺高分"),
        ("可暂缓", "可暂缓"),
        ("练习策略", "练习策略"),
        ("练习建议", "练习策略"),
        ("补充掌握点", "补充掌握点"),
    ]
    for marker, normalized in section_map:
        if marker in compact:
            return normalized
    return text


def _normalized_heading_level(original_level: int, heading_text: str) -> int:
    fixed_sections = {"题目画像", "必须掌握", "建议掌握", "冲刺高分", "可暂缓", "练习策略", "补充掌握点"}
    if heading_text in fixed_sections:
        return 4
    return min(max(original_level + 2, 5), 6)


def _strip_heading_noise(text: str) -> str:
    text = text.strip().strip("*").strip()
    text = re.sub(r"^(?:\d+|[一二三四五六七八九十]+)[\s.、．]+", "", text)
    return text.strip().strip("*").strip()


def _clean_process_text(text: str) -> str:
    replacements = [
        r"（[^）]*(?:证据|对应题目|对应第|来源：|来源:|基于证据)[^）]*）",
        r"\([^)]*(?:证据|对应题目|对应第|来源：|来源:|基于证据)[^)]*\)",
        r"（证据[^）]*）",
        r"\(证据[^)]*\)",
        r"（直接对应[^）]*）",
        r"\(直接对应[^)]*\)",
        r"（对应[^）]*题[^）]*）",
        r"\(对应[^)]*题[^)]*\)",
    ]
    cleaned = text
    for pattern in replacements:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = cleaned.replace("证据材料", "资料").replace("证据", "资料依据")
    return cleaned.rstrip()


def _match_profiles_to_knowledge(
    subject: str,
    profiles: list[QuestionProfile],
    knowledge_hashes: list[str],
) -> dict[str, list[Document]]:
    if not profiles or not knowledge_hashes:
        return {}
    store = get_store(subject, "knowledge")
    result: dict[str, list[Document]] = {}
    for profile in profiles:
        query = _profile_query(profile)
        if not query:
            result[profile.question_id] = []
            continue
        docs = store.max_marginal_relevance_search(
            query,
            k=QUESTION_MATCH_TOP_K,
            fetch_k=max(settings.retrieval_fetch_k, QUESTION_MATCH_TOP_K * 4),
            filter=_hash_filter(knowledge_hashes),
        )
        result[profile.question_id] = docs
    return result


def _group_profiles_by_chapter(
    profiles: list[QuestionProfile],
    matches: dict[str, list[Document]],
) -> dict[str, list[QuestionProfile]]:
    grouped: dict[str, list[QuestionProfile]] = defaultdict(list)
    for profile in profiles:
        chapter = profile.chapter or _primary_matched_chapter(matches.get(profile.question_id, [])) or "未归章"
        grouped[chapter].append(profile)
    return grouped


def _primary_matched_chapter(docs: list[Document]) -> str | None:
    counter = Counter(str(doc.metadata.get("chapter") or "") for doc in docs)
    counter.pop("", None)
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _chapter_evidence_docs(
    profiles: list[QuestionProfile],
    matches: dict[str, list[Document]],
) -> list[Document]:
    docs_by_id: dict[str, Document] = {}
    for profile in profiles:
        for doc in matches.get(profile.question_id, []):
            chunk_id = str(doc.metadata.get("chunk_id") or doc.metadata.get("source") or id(doc))
            docs_by_id.setdefault(chunk_id, doc)
    return list(docs_by_id.values())[:CHAPTER_EVIDENCE_LIMIT]


def _generate_chapter_brief(
    subject: str,
    target_score: int,
    chapter: str,
    knowledge_files: list[Path],
    exam_files: list[Path],
    user_instruction: str,
    profiles: list[QuestionProfile],
    evidence_docs: list[Document],
) -> ChapterBrief:
    question_types = _top_values(profile.question_type for profile in profiles)
    points = _top_values((point for profile in profiles for point in profile.tested_points), limit=12)
    traps = _top_values((point for profile in profiles for point in profile.trap_points), limit=10)
    keywords = _top_values((keyword for profile in profiles for keyword in profile.retrieval_keywords), limit=16)
    representative = [_representative_question(profile) for profile in profiles[:10]]
    evidence = _knowledge_evidence(profiles, evidence_docs)

    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for chapter brief generation.")

    review_markdown = _generate_chapter_markdown_with_llm(
        subject,
        target_score,
        chapter,
        user_instruction,
        profiles,
        evidence_docs,
    )

    return ChapterBrief(
        subject=subject,
        chapter=chapter,
        target_score=target_score,
        source_files={
            "knowledge": [path.name for path in knowledge_files],
            "exam": [path.name for path in exam_files],
        },
        question_count=len(profiles),
        question_types=question_types,
        high_frequency_points=points,
        trap_points=traps,
        retrieval_keywords=keywords,
        representative_questions=representative,
        knowledge_evidence=evidence,
        review_markdown=review_markdown,
    )


def _generate_chapter_markdown_with_llm(
    subject: str,
    target_score: int,
    chapter: str,
    user_instruction: str,
    profiles: list[QuestionProfile],
    evidence_docs: list[Document],
) -> str:
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.chat_base_url,
        temperature=0.2,
    )
    response = llm.invoke(
        _chapter_prompt(subject, target_score, chapter, user_instruction, profiles, evidence_docs)
    )
    return _clean_review_markdown(str(response.content))


def _chapter_prompt(
    subject: str,
    target_score: int,
    chapter: str,
    user_instruction: str,
    profiles: list[QuestionProfile],
    evidence_docs: list[Document],
) -> str:
    return f"""
你是考试复习资料分析助手。请把“结构化题目画像”和“命中的知识原文证据”转化为学生可直接阅读的本章复习提纲。

学科：{subject}
章节：{chapter}
目标分数：{target_score}/100
用户额外要求：{user_instruction or "无"}

结构化题目画像：
{_profiles_text(profiles)}

后台证据材料（只用于核对，不要在正文暴露证据编号）：
{_docs_text(evidence_docs)}

请输出 Markdown，必须包含：
1. 本章题目画像
2. 必须掌握
3. 建议掌握
4. 冲刺高分
5. 可暂缓
6. 练习策略

{MARKDOWN_FORMULA_RULES}

要求：
- 这是单章中间产物，不要写全局复习计划。
- 必须保留题目画像里出现的主线考点，不要为了简洁丢掉重点。
- 知识解释必须有资料依据，但正文不要写“证据1/证据2/对应题目第x题/根据题目答案”等过程性说明。
- 不要输出开场白、承诺语、分隔线或“我将为您生成”之类的话；直接从 Markdown 标题开始。
- 复习方案要像可直接背诵的讲义：先给结论、定义、辨析、易错点和练习策略。
- 证据不足时只在必要处写“资料依据不足，建议人工核对”，不要展开证据判断过程。
- 不要重新发明题目答案；优先压缩、整理原题和原文证据为复习语言。
""".strip()


def _clean_review_markdown(markdown: str) -> str:
    lines = []
    for raw_line in markdown.strip().splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            lines.append(line)
            continue
        if stripped in {"---", "----", "------"}:
            continue
        if _is_process_line(stripped):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _is_process_line(line: str) -> bool:
    process_markers = (
        "作为您的",
        "我将",
        "我会",
        "好的，",
        "以下是",
        "严格基于",
        "资料依据说明",
        "对应题目",
        "对应第",
        "**证据**",
        "证据：",
        "证据1",
        "证据2",
        "证据3",
        "根据题目第",
    )
    return any(marker in line for marker in process_markers)



def _knowledge_evidence(profiles: list[QuestionProfile], evidence_docs: list[Document]) -> list[KnowledgeEvidence]:
    docs = evidence_docs[:CHAPTER_EVIDENCE_LIMIT]
    evidence = []
    for point in _top_values((point for profile in profiles for point in profile.tested_points), limit=10):
        evidence.append(
            KnowledgeEvidence(
                point=point,
                query=point,
                matched_chunk_ids=[str(doc.metadata.get("chunk_id") or "") for doc in docs[:5]],
                chapters=sorted({str(doc.metadata.get("chapter") or "") for doc in docs if doc.metadata.get("chapter")}),
                sources=sorted({Path(str(doc.metadata.get("source") or "")).name for doc in docs if doc.metadata.get("source")}),
                text_summary=" ".join(doc.page_content.strip().replace("\n", " ")[:120] for doc in docs[:2]),
            )
        )
    return evidence


def _read_cached_brief(subject: str, chapter: str, fingerprint: str) -> ChapterBrief | None:
    path = _brief_json_path(subject, chapter)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("fingerprint") != fingerprint:
            return None
        brief = data["brief"]
        brief["knowledge_evidence"] = [KnowledgeEvidence(**item) for item in brief.get("knowledge_evidence", [])]
        return ChapterBrief(**brief)
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _write_cached_brief(subject: str, brief: ChapterBrief, fingerprint: str) -> None:
    json_path = _brief_json_path(subject, brief.chapter)
    md_path = _brief_md_path(subject, brief.chapter)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": CHAPTER_BRIEF_VERSION,
        "model": settings.chat_model,
        "fingerprint": fingerprint,
        "brief": asdict(brief),
    }
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_wrapped_brief_markdown(brief), encoding="utf-8")


def _brief_json_path(subject: str, chapter: str) -> Path:
    return _brief_dir(subject, chapter) / "brief.json"


def _brief_md_path(subject: str, chapter: str) -> Path:
    return _brief_dir(subject, chapter) / "brief.md"


def _brief_dir(subject: str, chapter: str) -> Path:
    return ROOT_DIR / ".cache" / "chapter_briefs" / _safe_name(subject) / _safe_name(chapter)


def _brief_fingerprint(
    chapter: str,
    profiles: list[QuestionProfile],
    evidence_docs: list[Document],
    knowledge_hashes: list[str],
    target_score: int,
    user_instruction: str = "",
) -> str:
    raw = json.dumps(
        {
            "version": CHAPTER_BRIEF_VERSION,
            "question_version": QUESTION_STRUCTURER_VERSION,
            "splitter_version": SEMANTIC_SPLITTER_VERSION,
            "model": settings.chat_model,
            "chapter": chapter,
            "target_score": target_score,
            "user_instruction_hash": sha1(user_instruction.encode("utf-8")).hexdigest(),
            "profiles": [
                {
                    "id": profile.question_id,
                    "points": profile.tested_points,
                    "traps": profile.trap_points,
                    "keywords": profile.retrieval_keywords,
                }
                for profile in profiles
            ],
            "evidence": [
                {
                    "id": doc.metadata.get("chunk_id"),
                    "hash": doc.metadata.get("content_hash"),
                    "text_hash": sha1(doc.page_content.encode("utf-8")).hexdigest(),
                }
                for doc in evidence_docs
            ],
            "knowledge_hashes": knowledge_hashes,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha1(raw.encode("utf-8")).hexdigest()


def _profile_query(profile: QuestionProfile) -> str:
    parts = []
    parts.extend(profile.tested_points)
    parts.extend(profile.trap_points)
    parts.extend(profile.retrieval_keywords)
    if profile.stem:
        parts.append(profile.stem[:220])
    return " ".join(dict.fromkeys(part for part in parts if part))


def _representative_question(profile: QuestionProfile) -> dict[str, Any]:
    return {
        "question_id": profile.question_id,
        "source_file": Path(profile.source_file).name,
        "question_index": profile.question_index,
        "question_type": profile.question_type,
        "stem": profile.stem,
        "answer": profile.answer,
        "tested_points": profile.tested_points,
        "trap_points": profile.trap_points,
    }


def _profiles_text(profiles: list[QuestionProfile]) -> str:
    lines = []
    for profile in profiles:
        lines.append(
            "\n".join(
                [
                    f"- 题目：{Path(profile.source_file).name} 第{profile.question_index or '?'}题",
                    f"  - 题型：{profile.question_type}",
                    f"  - 题干：{profile.stem[:220]}",
                    f"  - 答案：{profile.answer[:160] if profile.answer else '未识别'}",
                    f"  - 考点：{_join_or_empty(profile.tested_points)}",
                    f"  - 易错点：{_join_or_empty(profile.trap_points)}",
                    f"  - 检索关键词：{_join_or_empty(profile.retrieval_keywords)}",
                ]
            )
        )
    return "\n".join(lines) if lines else "无"


def _docs_text(docs: list[Document]) -> str:
    if not docs:
        return "未检索到知识证据。"
    blocks = []
    for index, doc in enumerate(docs, start=1):
        source = Path(str(doc.metadata.get("source") or doc.metadata.get("source_file") or "unknown")).name
        chapter = doc.metadata.get("chapter") or ""
        chunk_id = doc.metadata.get("chunk_id") or ""
        text = doc.page_content.strip().replace("\n", " ")
        blocks.append(f"证据{index} | {source} | {chapter} | {chunk_id}\n{text[:900]}")
    return "\n\n".join(blocks)


def _top_values(values, limit: int = 8) -> list[str]:
    counter = Counter(str(value).strip() for value in values if str(value).strip())
    return [item for item, _ in counter.most_common(limit)]


def _hash_filter(content_hashes: list[str]) -> dict | None:
    unique_hashes = list(dict.fromkeys(content_hashes))
    if not unique_hashes:
        return None
    if len(unique_hashes) == 1:
        return {"content_hash": unique_hashes[0]}
    return {"content_hash": {"$in": unique_hashes}}


def _join_or_empty(items: list[str]) -> str:
    return "、".join(items) if items else "未识别"


def _bullet_lines(items: list[str]) -> str:
    if not items:
        return "- 暂无"
    return "\n".join(f"- {item}" for item in items)


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value) or "_"
