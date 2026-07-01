import re

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from app.config import settings
from app.prompts.review_prompt import (
    MARKDOWN_FORMULA_RULES,
    REVIEW_ANSWER_RULES,
    REVIEW_PRACTICE_RULES,
    build_exam_profile_prompt,
    build_review_prompt,
)
from app.services.vectorstore import get_store


def retrieve_exam_context(
    subject: str,
    target_score: int,
    exam_hashes: list[str],
) -> list[Document]:
    base_query = (
        f"{subject} 目标{target_score}分 出题风格 常考题型 作业高频题 "
        "考试难度 高频知识点 易错点 基础题 综合题"
    )
    return get_store(subject, "exam").max_marginal_relevance_search(
        base_query,
        k=settings.retrieval_k,
        fetch_k=settings.retrieval_fetch_k,
        filter=_hash_filter(exam_hashes),
    )


def retrieve_knowledge_context(
    subject: str,
    target_score: int,
    exam_profile: str,
    knowledge_hashes: list[str],
) -> list[Document]:
    knowledge_query = _build_profile_guided_query(subject, target_score, exam_profile)
    return get_store(subject, "knowledge").max_marginal_relevance_search(
        knowledge_query,
        k=settings.retrieval_k,
        fetch_k=settings.retrieval_fetch_k,
        filter=_hash_filter(knowledge_hashes),
    )


def _hash_filter(content_hashes: list[str]) -> dict | None:
    if not content_hashes:
        return None
    unique_hashes = list(dict.fromkeys(content_hashes))
    if len(unique_hashes) == 1:
        return {"content_hash": unique_hashes[0]}
    return {"content_hash": {"$in": unique_hashes}}


def _build_profile_guided_query(
    subject: str,
    target_score: int,
    exam_profile: str,
) -> str:
    return (
        f"{subject} 目标{target_score}分。请检索与以下出题风格画像匹配的知识点、"
        f"概念、公式、例题、常见题型、易错点和综合题线索：\n{exam_profile[:2500]}"
    )


def generate_exam_profile(
    subject: str,
    target_score: int,
    exam_files: list[str],
    user_instruction: str,
    exam_docs: list[Document],
) -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for exam profile generation.")

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.chat_base_url,
        temperature=0.2,
    )
    prompt = build_exam_profile_prompt(
        subject=subject,
        target_score=target_score,
        exam_files=exam_files,
        user_instruction=user_instruction,
        exam_docs=exam_docs,
    )
    response = llm.invoke(prompt)
    return str(response.content)


def generate_markdown(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    user_instruction: str,
    exam_profile: str,
    knowledge_docs: list[Document],
    exam_docs: list[Document],
) -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for markdown generation.")

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.chat_base_url,
        temperature=0.2,
    )
    prompt = build_review_prompt(
        subject=subject,
        target_score=target_score,
        knowledge_files=knowledge_files,
        exam_files=exam_files,
        user_instruction=user_instruction,
        exam_profile=exam_profile,
        knowledge_docs=knowledge_docs,
        exam_docs=exam_docs,
    )
    response = llm.invoke(prompt)
    return str(response.content)


def generate_final_markdown_from_chapter_briefs(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    user_instruction: str,
    chapter_briefs_markdown: str,
) -> str:
    overview = _normalize_overview_headings(
        _generate_light_final_overview(
            subject,
            target_score,
            knowledge_files,
            exam_files,
            user_instruction,
            chapter_briefs_markdown,
        )
    )
    return "\n\n".join(
        part.strip()
        for part in [
            f"# {subject} 目标{target_score}分复习方案",
            "## 总览",
            overview,
            "## 单章复习方案",
            chapter_briefs_markdown or "未生成单章中间产物。",
        ]
        if part.strip()
    )


def generate_full_context_markdown(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    user_instruction: str,
    full_context: str,
) -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for full-context generation.")

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.chat_base_url,
        temperature=0.2,
    )
    prompt = f"""
你是高效复习规划助手。请基于给定的完整资料上下文，生成可直接复习使用的 Markdown 方案。

学科：{subject}
目标分数：{target_score}/100

知识资料：
{_bullet_list(knowledge_files)}

习题/出题参考：
{_bullet_list(exam_files)}

用户额外要求：
{user_instruction or "无"}

完整资料上下文：
{full_context}

请输出 Markdown，包含：
1. 资料分析
2. 出题画像与高频题型
3. 目标分数策略
4. 必须掌握
5. 建议掌握
6. 冲刺高分
7. 可暂缓
8. 练习建议与轻量练习题

{REVIEW_ANSWER_RULES}

{REVIEW_PRACTICE_RULES}

{MARKDOWN_FORMULA_RULES}

要求：
- 优先保留资料中的主线考点，不要为了简洁丢掉章节重点。
- 明确区分“知识资料直接给出”和“根据习题画像推断”。
- 不要承诺押题命中；只能表达高频、重点、建议掌握。
- 如果资料依据不足，请直接标注风险。
- 输出要适合直接复习，不要只写抽象建议。
- 不要输出“我将为您”“严格基于”“对应题目”“证据1/证据2”等过程性说明。
- 正文要像复习讲义，不要像审计报告。
- 可以输出标题，但最终系统会统一外层标题层级。
""".strip()
    response = llm.invoke(prompt)
    body = _normalize_full_context_headings(str(response.content))
    return "\n\n".join(
        part.strip()
        for part in [
            f"# {subject} 目标{target_score}分复习方案",
            body,
        ]
        if part.strip()
    )


def _generate_light_final_overview(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    user_instruction: str,
    chapter_briefs_markdown: str,
) -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for final overview generation.")

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.chat_base_url,
        temperature=0.2,
    )
    prompt = f"""
你是复习方案编辑助手。请只基于单章中间产物生成最终方案的“总览部分”，不要重写各章重点。

学科：{subject}
目标分数：{target_score}/100

知识资料：
{_bullet_list(knowledge_files)}

习题/出题参考：
{_bullet_list(exam_files)}

用户额外要求：
{user_instruction or "无"}

单章中间产物概览：
{_chapter_overview_context(chapter_briefs_markdown) or "无"}

请输出 Markdown，只包含：
1. 资料分析
2. 跨章节出题画像
3. 目标分数策略
4. 总优先级建议

要求：
- 不要重新生成或删减单章复习内容。
- 只做连接、排序、去重和跨章关系分析。
- 章节细节会由程序按“第x章方案”稳定拼接在后面。
- 不要输出总标题。
- 不要输出“我将为您”“严格基于”“对应题目”“证据1/证据2”等过程性说明。
""".strip()
    response = llm.invoke(prompt)
    return str(response.content)


def _chapter_overview_context(chapter_briefs_markdown: str) -> str:
    chapters: list[tuple[str, list[str]]] = []
    current_title = ""
    current_lines: list[str] = []

    for raw_line in chapter_briefs_markdown.splitlines():
        line = raw_line.strip()
        chapter_heading = re.match(r"^###\s+(第\d+章方案|.+?\s+方案)\s*$", line)
        if chapter_heading:
            if current_title:
                chapters.append((current_title, current_lines))
            current_title = chapter_heading.group(1)
            current_lines = []
            continue
        if not current_title:
            continue
        if line.startswith("- 题目数量：") or line.startswith("- 高频题型：") or line.startswith("- 高频考点："):
            current_lines.append(line)
            continue
        if line.startswith("#### "):
            current_lines.append(line)
            continue
        if line.startswith("##### ") and len([item for item in current_lines if item.startswith("##### ")]) < 8:
            current_lines.append(line)

    if current_title:
        chapters.append((current_title, current_lines))

    blocks = []
    for title, lines in chapters:
        useful_lines = lines[:18]
        blocks.append("\n".join([f"### {title}", *useful_lines]))
    return "\n\n".join(blocks)[:14000]


def _normalize_overview_headings(markdown: str) -> str:
    lines = []
    for raw_line in markdown.strip().splitlines():
        line = raw_line.rstrip()
        if not line.startswith("#"):
            lines.append(line)
            continue
        text = line.lstrip("#").strip()
        if _looks_like_document_title(text):
            continue
        lines.append(f"### {_strip_heading_number(text)}")
    return "\n".join(lines).strip()


def _normalize_full_context_headings(markdown: str) -> str:
    lines = []
    for raw_line in markdown.strip().splitlines():
        line = raw_line.rstrip()
        if not line.startswith("#"):
            lines.append(line)
            continue
        level = len(line) - len(line.lstrip("#"))
        text = line.lstrip("#").strip()
        if _looks_like_document_title(text):
            continue
        normalized_level = min(max(level + 1, 2), 6)
        lines.append(f"{'#' * normalized_level} {_strip_heading_number(text)}")
    return "\n".join(lines).strip()


def _looks_like_document_title(text: str) -> bool:
    compact = text.replace(" ", "")
    title_markers = ("复习方案", "总复习", "最终方案")
    section_markers = ("资料分析", "题画像", "目标分数", "必须掌握")
    return any(marker in compact for marker in title_markers) and not any(
        marker in compact for marker in section_markers
    )


def _strip_heading_number(text: str) -> str:
    text = text.strip().strip("*").strip()
    text = re.sub(r"^(?:\d+|[一二三四五六七八九十]+)[\s.、：:]+", "", text)
    return text.strip().strip("*").strip()


def answer_question(
    subject: str,
    question: str,
    output_markdown: str,
    knowledge_docs: list[Document],
    exam_docs: list[Document],
) -> str:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required for chat answers.")

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.chat_base_url,
        temperature=0.2,
    )
    prompt = f"""
你是一个复习答疑助手。请基于当前复习方案、知识库片段和出题参考片段回答用户问题。

学科：{subject}

用户问题：
{question}

当前复习方案：
{output_markdown[:6000]}

知识库相关片段：
{_format_docs(knowledge_docs)}

出题参考相关片段：
{_format_docs(exam_docs)}

{REVIEW_ANSWER_RULES}

要求：
- 优先基于资料回答，不要凭空扩展。
- 如果资料不足，请明确说明。
- 回答要适合复习场景，可以给例子、记忆方法或练习建议。
""".strip()
    response = llm.invoke(prompt)
    return str(response.content)


def _score_strategy(target_score: int) -> str:
    if target_score < 70:
        return "以过线为核心，优先掌握定义、公式、基础例题和作业中反复出现的常规题。"
    if target_score < 85:
        return "基础题必须稳定，中等题尽量覆盖，暂时放弃少量高难综合题。"
    if target_score < 95:
        return "基础和中等题都要稳定，重点训练高频综合题和易错题型。"
    return "追求完整覆盖，除核心题型外，还需要处理冷门知识点、高难变式和综合压轴题。"


def _bullet_list(items: list[str]) -> str:
    if not items:
        return "- 未选择"
    return "\n".join(f"- {item}" for item in items)


def _format_docs(docs: list[Document]) -> str:
    if not docs:
        return "未检索到相关片段。"
    blocks = []
    for i, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        text = doc.page_content.strip().replace("\n", " ")
        blocks.append(f"### 片段 {i}\n来源：{source}\n\n{text[:900]}")
    return "\n\n".join(blocks)
