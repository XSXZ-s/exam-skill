from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha1
import json
from pathlib import Path
import re
from typing import Any

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from app.config import ROOT_DIR, settings
from app.prompts.review_prompt import MARKDOWN_FORMULA_RULES
from app.services.exam_structurer import QuestionProfile, extract_question_profiles
from app.services.file_hash import hash_file
from app.services.vectorstore import get_store


AUDIT_VERSION = "review_audit_v1"


@dataclass
class AuditCandidate:
    point: str
    count: int
    evidence_docs: list[Document]


@dataclass
class AuditContext:
    subject: str
    profiles: list[QuestionProfile]
    knowledge_hashes: list[str]


def build_audit_context(
    subject: str,
    knowledge_files: list[Path],
    exam_files: list[Path],
    chapter_hints: dict[Path, str] | None = None,
) -> AuditContext:
    return AuditContext(
        subject=subject,
        profiles=extract_question_profiles(subject, exam_files, chapter_hints=chapter_hints),
        knowledge_hashes=[hash_file(path) for path in knowledge_files],
    )


def audit_and_patch_markdown(
    subject: str,
    target_score: int,
    markdown: str,
    audit_context: AuditContext,
    chapter: str | None = None,
) -> str:
    if settings.audit_missing_point_limit <= 0:
        return markdown
    candidates = _missing_candidates(subject, markdown, audit_context, chapter=chapter)
    if not candidates:
        return markdown
    cache_key = _audit_cache_key(subject, target_score, markdown, candidates, chapter)
    cached = _read_cached_patch(subject, cache_key)
    if cached is None:
        patches = _generate_patches(subject, target_score, markdown, candidates, chapter=chapter)
        _write_cached_patch(subject, cache_key, patches)
    else:
        patches = cached
    return _apply_patches(markdown, patches, candidates)


def _missing_candidates(
    subject: str,
    markdown: str,
    audit_context: AuditContext,
    chapter: str | None = None,
) -> list[AuditCandidate]:
    profiles = _profiles_for_chapter(audit_context.profiles, chapter)
    counter = Counter(point for profile in profiles for point in profile.tested_points if point.strip())
    candidates: list[AuditCandidate] = []
    for point, count in counter.most_common(settings.audit_missing_point_limit * 2):
        if _point_covered(markdown, point):
            continue
        docs = _retrieve_evidence(subject, point, audit_context.knowledge_hashes)
        candidates.append(AuditCandidate(point=point, count=count, evidence_docs=docs))
        if len(candidates) >= settings.audit_missing_point_limit:
            break
    return candidates


def _profiles_for_chapter(profiles: list[QuestionProfile], chapter: str | None) -> list[QuestionProfile]:
    if not chapter:
        return profiles
    return [profile for profile in profiles if profile.chapter == chapter]


def _point_covered(markdown: str, point: str) -> bool:
    compact_markdown = "".join(markdown.split()).lower()
    compact_point = "".join(point.split()).lower()
    if not compact_point:
        return True
    return compact_point in compact_markdown


def _retrieve_evidence(subject: str, point: str, knowledge_hashes: list[str]) -> list[Document]:
    if not knowledge_hashes:
        return []
    try:
        return get_store(subject, "knowledge").max_marginal_relevance_search(
            point,
            k=3,
            fetch_k=max(settings.retrieval_fetch_k, 12),
            filter=_hash_filter(knowledge_hashes),
        )
    except Exception:
        return []


def _generate_patches(
    subject: str,
    target_score: int,
    markdown: str,
    candidates: list[AuditCandidate],
    chapter: str | None = None,
) -> list[dict[str, Any]]:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for review audit.")
    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.chat_base_url,
        temperature=0.1,
    )
    response = llm.invoke(_audit_prompt(subject, target_score, markdown, candidates, chapter=chapter))
    parsed = _parse_json(str(response.content))
    if not parsed:
        return []
    patches = parsed.get("patches") if isinstance(parsed, dict) else parsed
    if not isinstance(patches, list):
        return []
    cleaned = []
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        point = str(patch.get("point") or "").strip()
        text = str(patch.get("patch") or "").strip()
        if point and text:
            cleaned.append(
                {
                    "chapter": str(patch.get("chapter") or chapter or "").strip(),
                    "section": str(patch.get("section") or "覆盖审核补充").strip(),
                    "point": point,
                    "reason": str(patch.get("reason") or "题目画像高频出现，但方案未充分覆盖。").strip(),
                    "patch": text,
                }
            )
    return cleaned


def _audit_prompt(
    subject: str,
    target_score: int,
    markdown: str,
    candidates: list[AuditCandidate],
    chapter: str | None = None,
) -> str:
    return f"""
你是复习方案覆盖率审核员。请只基于“缺口候选”和“原文证据”判断是否需要给当前方案补丁。

学科：{subject}
目标分数：{target_score}/100
审核范围：{chapter or "全局方案"}

当前方案摘录：
{markdown[:7000]}

缺口候选与证据：
{_candidates_text(candidates)}

请只输出 JSON，不要 Markdown。格式：
{{
  "patches": [
    {{
      "chapter": "ch03 或空",
      "section": "必须掌握/建议掌握/冲刺高分/补充掌握点",
      "point": "考点名",
      "reason": "为什么需要补充",
      "patch": "- 可直接插入复习方案的一条或多条 Markdown bullet"
    }}
  ]
}}

{MARKDOWN_FORMULA_RULES}

要求：
- 只补充确实被题目画像反复考到、且证据能支持的内容。
- 不要重写整篇方案。
- 不要发明资料外内容；证据不足时不要强行补。
- patch 要短而具体，适合直接追加到方案中。
- patch 正文不要写“证据1/证据2/对应题目/根据检索/审核发现/补充原因”等过程性说明。
- patch 要像复习讲义内容：直接给定义、辨析、易错点或记忆方式。
""".strip()


def _candidates_text(candidates: list[AuditCandidate]) -> str:
    blocks = []
    for index, candidate in enumerate(candidates, start=1):
        blocks.append(
            "\n".join(
                [
                    f"候选{index}: {candidate.point} | 题目画像出现 {candidate.count} 次",
                    _docs_text(candidate.evidence_docs),
                ]
            )
        )
    return "\n\n".join(blocks)


def _docs_text(docs: list[Document]) -> str:
    if not docs:
        return "证据：未检索到"
    lines = []
    for index, doc in enumerate(docs, start=1):
        source = Path(str(doc.metadata.get("source") or doc.metadata.get("source_file") or "unknown")).name
        chapter = doc.metadata.get("chapter") or ""
        chunk_id = doc.metadata.get("chunk_id") or ""
        text = doc.page_content.strip().replace("\n", " ")[:500]
        lines.append(f"证据{index} | {source} | {chapter} | {chunk_id}\n{text}")
    return "\n".join(lines)


def _apply_patches(markdown: str, patches: list[dict[str, Any]], candidates: list[AuditCandidate]) -> str:
    useful = [patch for patch in patches if str(patch.get("patch") or "").strip()]
    if not useful:
        return markdown
    lines = [
        "",
        "## 补充掌握点",
        "",
        "以下内容用于补足首轮方案中可能遗漏、但复习时值得掌握的高频点。",
        "",
    ]
    for patch in useful:
        point = str(patch.get("point") or "").strip()
        body = str(patch.get("patch") or "").strip()
        clean_body = _clean_patch_text(body)
        if clean_body.startswith("-"):
            bullet = clean_body[1:].strip()
        else:
            bullet = clean_body
        prefix = f"**{point}**：" if point else ""
        lines.append(f"- {prefix}{bullet}")
        lines.append("")
    return f"{markdown.rstrip()}\n\n" + "\n".join(lines).strip()


def _clean_patch_text(text: str) -> str:
    cleaned = []
    banned = ("证据", "对应题目", "根据检索", "审核发现", "补充原因")
    for line in text.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(marker in stripped for marker in banned):
            continue
        cleaned.append(line.rstrip())
    return "\n".join(cleaned).strip()


def _parse_json(content: str) -> Any:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        stripped = stripped[start : end + 1]
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _hash_filter(content_hashes: list[str]) -> dict | None:
    unique_hashes = list(dict.fromkeys(content_hashes))
    if not unique_hashes:
        return None
    if len(unique_hashes) == 1:
        return {"content_hash": unique_hashes[0]}
    return {"content_hash": {"$in": unique_hashes}}


def _audit_cache_key(
    subject: str,
    target_score: int,
    markdown: str,
    candidates: list[AuditCandidate],
    chapter: str | None,
) -> str:
    raw = json.dumps(
        {
            "version": AUDIT_VERSION,
            "subject": subject,
            "target_score": target_score,
            "chapter": chapter,
            "model": settings.chat_model,
            "markdown_hash": sha1(markdown.encode("utf-8")).hexdigest(),
            "candidates": [
                {
                    "point": candidate.point,
                    "count": candidate.count,
                    "evidence": [
                        doc.metadata.get("chunk_id") or sha1(doc.page_content.encode("utf-8")).hexdigest()
                        for doc in candidate.evidence_docs
                    ],
                }
                for candidate in candidates
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha1(raw.encode("utf-8")).hexdigest()


def _audit_cache_file(subject: str, cache_key: str) -> Path:
    return ROOT_DIR / ".cache" / "review_audits" / _safe_name(subject) / f"{cache_key}.json"


def _read_cached_patch(subject: str, cache_key: str) -> list[dict[str, Any]] | None:
    path = _audit_cache_file(subject, cache_key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != AUDIT_VERSION:
            return None
        patches = data.get("patches")
        return patches if isinstance(patches, list) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_cached_patch(subject: str, cache_key: str, patches: list[dict[str, Any]]) -> None:
    path = _audit_cache_file(subject, cache_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": AUDIT_VERSION, "patches": patches}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-").lower()
    return safe or sha1(value.encode("utf-8")).hexdigest()[:12]
