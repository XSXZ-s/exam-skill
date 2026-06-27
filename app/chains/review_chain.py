from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from app.config import settings
from app.prompts.review_prompt import (
    REVIEW_ANSWER_RULES,
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
        return build_fallback_exam_profile(subject, target_score, exam_files, user_instruction, exam_docs)

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
        return build_fallback_markdown(
            subject,
            target_score,
            knowledge_files,
            exam_files,
            user_instruction,
            exam_profile,
            knowledge_docs,
            exam_docs,
        )

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


def answer_question(
    subject: str,
    question: str,
    output_markdown: str,
    knowledge_docs: list[Document],
    exam_docs: list[Document],
) -> str:
    if not settings.llm_api_key:
        return "当前环境没有检测到 `LLM_API_KEY`，无法进行追问。请配置模型后重新运行。"

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


def build_fallback_markdown(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    user_instruction: str,
    exam_profile: str,
    knowledge_docs: list[Document],
    exam_docs: list[Document],
) -> str:
    return f"""# {subject} 目标{target_score}分复习方案
## 资料分析

### 知识库资料
{_bullet_list(knowledge_files)}

### 出题参考资料
{_bullet_list(exam_files)}

### 用户本次额外要求
{user_instruction or "无"}

## 出题风格画像

{exam_profile or "未生成。"}

## 目标分数策略

{_score_strategy(target_score)}

## 检索到的知识库线索

{_format_docs(knowledge_docs)}

## 检索到的出题风格线索
{_format_docs(exam_docs)}

## 下一步
当前环境没有检测到 `LLM_API_KEY`，因此已完成本地 Chroma 索引和证据片段汇总。配置模型后重新运行，可生成完整的知识点分层、复习建议和配套练习题。"""


def build_fallback_exam_profile(
    subject: str,
    target_score: int,
    exam_files: list[str],
    user_instruction: str,
    exam_docs: list[Document],
) -> str:
    return f"""## 出题风格画像

### 分析范围

学科：{subject}
目标分数：{target_score}/100

出题参考资料：
{_bullet_list(exam_files)}

用户本次额外要求：
{user_instruction or "无"}

### 检索到的出题参考线索

{_format_docs(exam_docs)}

### 说明

当前环境没有检测到 `LLM_API_KEY`，因此这里只汇总检索线索。配置模型后可生成高频题型、难度分布、易错点和知识库检索关键词。"""


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
