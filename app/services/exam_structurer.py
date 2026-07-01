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
from app.services.document_loader import load_documents
from app.services.file_hash import hash_file
from app.services.semantic_splitter import SEMANTIC_SPLITTER_VERSION, semantic_chunks_for_file


QUESTION_STRUCTURER_VERSION = "question_structurer_v2"
QUESTION_BATCH_SIZE = 12


@dataclass
class QuestionProfile:
    question_id: str
    source_file: str
    chunk_id: str
    chapter: str | None
    assignment_title: str | None
    question_index: int | None
    question_type: str
    stem: str
    answer: str
    analysis_summary: str
    tested_points: list[str] = field(default_factory=list)
    trap_points: list[str] = field(default_factory=list)
    difficulty: str = "unknown"
    retrieval_keywords: list[str] = field(default_factory=list)


def build_structured_exam_profile(
    subject: str,
    target_score: int,
    exam_files: list[Path],
    chapter_hints: dict[Path, str] | None = None,
) -> str:
    profiles = extract_question_profiles(subject, exam_files, chapter_hints=chapter_hints)
    return format_exam_profile(subject, target_score, profiles)


def extract_question_profiles(
    subject: str,
    exam_files: list[Path],
    chapter_hints: dict[Path, str] | None = None,
) -> list[QuestionProfile]:
    chapter_hints = chapter_hints or {}
    questions = _exam_question_chunks(subject, exam_files, chapter_hints)
    profiles: list[QuestionProfile] = []
    missing: list[Document] = []

    for doc in questions:
        cached = _read_cached_profile(subject, doc)
        if cached is None:
            missing.append(doc)
        else:
            profiles.append(cached)

    if missing:
        for batch in _batches(missing, QUESTION_BATCH_SIZE):
            generated = _structure_question_batch(subject, batch)
            profiles.extend(generated)
            for doc, profile in zip(batch, generated):
                _write_cached_profile(subject, doc, profile)

    return sorted(
        profiles,
        key=lambda item: (
            item.chapter or "",
            item.source_file.lower(),
            item.question_index or 0,
            item.chunk_id,
        ),
    )


def format_exam_profile(subject: str, target_score: int, profiles: list[QuestionProfile]) -> str:
    if not profiles:
        return f"## 题目画像\n\n未提取到可用的单题结构化结果。\n\n学科：{subject}\n目标分数：{target_score}/100"

    by_chapter: dict[str, list[QuestionProfile]] = defaultdict(list)
    for profile in profiles:
        by_chapter[profile.chapter or "未归章"].append(profile)

    all_types = Counter(profile.question_type for profile in profiles if profile.question_type)
    all_points = Counter(point for profile in profiles for point in profile.tested_points)
    all_traps = Counter(point for profile in profiles for point in profile.trap_points)
    all_keywords = Counter(keyword for profile in profiles for keyword in profile.retrieval_keywords)

    lines = [
        "## 结构化题目画像",
        "",
        f"- 学科：{subject}",
        f"- 目标分数：{target_score}/100",
        f"- 已结构化题目数：{len(profiles)}",
        f"- 高频题型：{_counter_text(all_types, 6)}",
        f"- 高频考点：{_counter_text(all_points, 12)}",
        f"- 易错点：{_counter_text(all_traps, 10)}",
        f"- 知识库检索关键词：{_counter_text(all_keywords, 16)}",
        "",
    ]

    for chapter, items in sorted(by_chapter.items(), key=lambda pair: pair[0]):
        chapter_points = Counter(point for item in items for point in item.tested_points)
        chapter_traps = Counter(point for item in items for point in item.trap_points)
        chapter_keywords = Counter(keyword for item in items for keyword in item.retrieval_keywords)
        lines.extend(
            [
                f"### {chapter}",
                "",
                f"- 题目数量：{len(items)}",
                f"- 主要考点：{_counter_text(chapter_points, 10)}",
                f"- 常见失分点：{_counter_text(chapter_traps, 8)}",
                f"- 检索关键词：{_counter_text(chapter_keywords, 12)}",
                "- 代表题：",
            ]
        )
        for item in items[:8]:
            points = "、".join(item.tested_points[:3]) or "未识别"
            lines.append(
                f"  - {Path(item.source_file).name} 第{item.question_index or '?'}题："
                f"{item.question_type}；考点：{points}；答案：{item.answer or '未识别'}"
            )
        lines.append("")

    return "\n".join(lines).strip()


def _exam_question_chunks(
    subject: str,
    exam_files: list[Path],
    chapter_hints: dict[Path, str],
) -> list[Document]:
    questions: list[Document] = []
    for path in exam_files:
        documents = load_documents([path], subject=subject)
        chunks = semantic_chunks_for_file(
            subject,
            "exam",
            path,
            documents,
            chapter_hint=chapter_hints.get(path.resolve()),
        )
        questions.extend(chunk for chunk in chunks if chunk.metadata.get("chunk_kind") == "question")
    return questions


def _structure_question_batch(subject: str, docs: list[Document]) -> list[QuestionProfile]:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for question profile extraction.")

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.chat_base_url,
        temperature=0.1,
    )
    prompt = _build_question_structure_prompt(subject, docs)
    response = llm.invoke(prompt)
    parsed = _parse_profiles_json(str(response.content))
    by_id = {str(item.get("question_id")): item for item in parsed if isinstance(item, dict)}

    profiles = []
    for doc in docs:
        question_id = _question_id(doc)
        raw = by_id.get(question_id)
        if raw is None:
            profiles.append(_baseline_profile(doc))
        else:
            profiles.append(_profile_from_llm(doc, raw))
    return profiles


def _build_question_structure_prompt(subject: str, docs: list[Document]) -> str:
    blocks = []
    for doc in docs:
        metadata = doc.metadata
        blocks.append(
            "\n".join(
                [
                    f"question_id: {_question_id(doc)}",
                    f"source_file: {metadata.get('source_file') or metadata.get('source') or ''}",
                    f"chapter: {metadata.get('chapter') or ''}",
                    f"assignment_title: {metadata.get('assignment_title') or ''}",
                    f"question_index: {metadata.get('question_index') or ''}",
                    "text:",
                    doc.page_content[:1800],
                ]
            )
        )
    question_blocks = "\n".join(f"-----\n{block}" for block in blocks)
    return f"""
你是考试题目结构化分析助手。请只基于给定题目文本，把每道题整理为 JSON。

学科：{subject}

输出要求：
- 只输出 JSON，不要 Markdown。
- 顶层格式必须是数组。
- 每个对象必须包含：
  question_id, question_type, stem, answer, analysis_summary,
  tested_points, trap_points, difficulty, retrieval_keywords
- tested_points/trap_points/retrieval_keywords 必须是中文字符串数组。
- difficulty 只能是 foundation / medium / hard / unknown。
- 不确定答案或考点时写空字符串或空数组，不要编造资料外细节。
- retrieval_keywords 用于检索知识库，优先提炼概念、公式、术语、题型关键词。

题目：
{question_blocks}
""".strip()


def _profile_from_llm(doc: Document, raw: dict[str, Any]) -> QuestionProfile:
    baseline = _baseline_profile(doc)
    return QuestionProfile(
        question_id=baseline.question_id,
        source_file=baseline.source_file,
        chunk_id=baseline.chunk_id,
        chapter=baseline.chapter,
        assignment_title=baseline.assignment_title,
        question_index=baseline.question_index,
        question_type=_clean_str(raw.get("question_type")) or baseline.question_type,
        stem=_clean_str(raw.get("stem")) or baseline.stem,
        answer=_clean_str(raw.get("answer")) or baseline.answer,
        analysis_summary=_clean_str(raw.get("analysis_summary")) or baseline.analysis_summary,
        tested_points=_clean_list(raw.get("tested_points")) or baseline.tested_points,
        trap_points=_clean_list(raw.get("trap_points")) or baseline.trap_points,
        difficulty=_difficulty(raw.get("difficulty")) or baseline.difficulty,
        retrieval_keywords=_clean_list(raw.get("retrieval_keywords")) or baseline.retrieval_keywords,
    )


def _baseline_profile(doc: Document) -> QuestionProfile:
    metadata = doc.metadata
    text = doc.page_content.strip()
    question_type = _detect_question_type(text)
    answer = _extract_answer(text)
    stem = _extract_stem(text)
    keywords = _baseline_keywords(text)
    return QuestionProfile(
        question_id=_question_id(doc),
        source_file=str(metadata.get("source_file") or metadata.get("source") or ""),
        chunk_id=str(metadata.get("chunk_id") or ""),
        chapter=str(metadata.get("chapter") or "") or None,
        assignment_title=str(metadata.get("assignment_title") or "") or None,
        question_index=_int_or_none(metadata.get("question_index")),
        question_type=question_type,
        stem=stem,
        answer=answer,
        analysis_summary=_extract_analysis_summary(text),
        tested_points=keywords[:5],
        trap_points=[],
        difficulty="unknown",
        retrieval_keywords=keywords[:8],
    )


def _parse_profiles_json(content: str) -> list[dict[str, Any]]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    match = re.search(r"\[[\s\S]*\]", stripped)
    if match:
        stripped = match.group(0)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _read_cached_profile(subject: str, doc: Document) -> QuestionProfile | None:
    path = _profile_cache_file(subject, doc)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("fingerprint") != _profile_fingerprint(doc):
            return None
        return QuestionProfile(**data["profile"])
    except (OSError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _write_cached_profile(subject: str, doc: Document, profile: QuestionProfile) -> None:
    path = _profile_cache_file(subject, doc)
    if not settings.llm_api_key and path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": QUESTION_STRUCTURER_VERSION,
                "model": settings.chat_model,
                "fingerprint": _profile_fingerprint(doc),
                "profile": asdict(profile),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _profile_cache_file(subject: str, doc: Document) -> Path:
    source_hash = str(doc.metadata.get("content_hash") or hash_file(Path(doc.metadata.get("source_file", ""))))
    chunk_id = str(doc.metadata.get("chunk_id") or _question_id(doc))
    return _profile_cache_dir(subject, source_hash) / f"{_safe_name(chunk_id)}.json"


def _profile_cache_dir(subject: str, source_hash: str) -> Path:
    return ROOT_DIR / ".cache" / "question_profiles" / _safe_name(subject) / source_hash


def _profile_fingerprint(doc: Document) -> str:
    raw = "|".join(
        [
            QUESTION_STRUCTURER_VERSION,
            SEMANTIC_SPLITTER_VERSION,
            settings.chat_model,
            str(doc.metadata.get("chunk_id") or ""),
            doc.page_content,
        ]
    )
    return sha1(raw.encode("utf-8")).hexdigest()


def _question_id(doc: Document) -> str:
    metadata = doc.metadata
    source = Path(str(metadata.get("source_file") or metadata.get("source") or "unknown")).name
    question_index = metadata.get("question_index") or "?"
    chunk_id = metadata.get("chunk_id") or _hash_text(doc.page_content)[:12]
    return f"{source}#q{question_index}#{chunk_id}"


def _detect_question_type(text: str) -> str:
    if re.search(r"(单选|选择题|A[\.、\s].*B[\.、\s].*C[\.、\s].*D[\.、\s])", text, re.S):
        return "单选题"
    if "判断" in text or re.search(r"(正确|错误|对|错)", text):
        return "判断题"
    if re.search(r"____|_{2,}|填空", text):
        return "填空题"
    if re.search(r"(计算|求|证明|推导)", text):
        return "计算题"
    if re.search(r"(简述|说明|分析)", text):
        return "简答题"
    return "未知题型"


def _extract_answer(text: str) -> str:
    patterns = [
        r"(?:正确答案|答案)\s*[:：]\s*([A-DＡ-Ｄ]|正确|错误|对|错|[^\n。；;]{1,80})",
        r"\*\*(?:正确答案|答案)\s*[:：]\s*([^*\n]{1,80})\*\*",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _extract_stem(text: str) -> str:
    text = re.sub(r"^#{1,6}\s*第\s*\d+\s*[题題].*?\n", "", text.strip(), count=1)
    match = re.search(r"(?:题干|题目)\s*[:：]\s*([\s\S]{1,500})", text)
    if match:
        stem = match.group(1)
    else:
        stem = text[:500]
    stem = re.split(r"\n\s*(?:A[\.、\s]|答案\s*[:：]|正确答案\s*[:：])", stem, maxsplit=1)[0]
    return " ".join(stem.split())[:300]


def _extract_analysis_summary(text: str) -> str:
    match = re.search(r"(?:解析|解答过程)\s*[:：]?\s*([\s\S]{1,500})", text)
    if not match:
        return ""
    return " ".join(match.group(1).split())[:300]


def _baseline_keywords(text: str) -> list[str]:
    cleaned = re.sub(r"[A-D][\.、\s][^\n]{0,80}", " ", text)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_+\-/]{1,}|[\u4e00-\u9fff]{2,10}", cleaned)
    stopwords = {
        "ch01",
        "ch02",
        "ch03",
        "ch04",
        "ch05",
        "ch06",
        "ch07",
        "ch08",
        "ch09",
        "ch10",
        "题目",
        "题干",
        "答案",
        "解析",
        "正确答案",
        "下列",
        "的是",
        "属于",
        "进行",
        "计算机",
    }
    counter = Counter(
        token
        for token in tokens
        if token not in stopwords
        and not re.fullmatch(r"第[一二三四五六七八九十0-9]+次作业题?", token)
        and not re.fullmatch(r"第[0-9]+题", token)
    )
    return [word for word, _ in counter.most_common(12)]


def _counter_text(counter: Counter, limit: int) -> str:
    if not counter:
        return "未识别"
    return "、".join(f"{item}({count})" for item, count in counter.most_common(limit))


def _clean_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _difficulty(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in {"foundation", "medium", "hard", "unknown"} else "unknown"


def _int_or_none(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _batches(items: list[Document], size: int) -> list[list[Document]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value) or "_"


def _hash_text(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()
