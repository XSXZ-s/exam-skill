from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from app.config import settings
from app.prompts.review_prompt import build_review_prompt
from app.services.vectorstore import get_store


def retrieve_review_context(
    subject: str,
    target_score: int,
    knowledge_hashes: list[str],
    exam_hashes: list[str],
) -> tuple[list[Document], list[Document]]:
    base_query = (
        f"{subject} target {target_score}/100 important topics common question types "
        "exam difficulty homework high-frequency topics must learn"
    )
    exam_docs = get_store(subject, "exam").max_marginal_relevance_search(
        base_query,
        k=settings.retrieval_k,
        fetch_k=settings.retrieval_fetch_k,
        filter=_hash_filter(exam_hashes),
    )
    knowledge_query = _build_exam_guided_query(subject, target_score, exam_docs)
    knowledge_docs = get_store(subject, "knowledge").max_marginal_relevance_search(
        knowledge_query,
        k=settings.retrieval_k,
        fetch_k=settings.retrieval_fetch_k,
        filter=_hash_filter(knowledge_hashes),
    )
    return knowledge_docs, exam_docs


def _hash_filter(content_hashes: list[str]) -> dict | None:
    if not content_hashes:
        return None
    unique_hashes = list(dict.fromkeys(content_hashes))
    if len(unique_hashes) == 1:
        return {"content_hash": unique_hashes[0]}
    return {"content_hash": {"$in": unique_hashes}}


def _build_exam_guided_query(
    subject: str,
    target_score: int,
    exam_docs: list[Document],
) -> str:
    exam_context = " ".join(
        doc.page_content.strip().replace("\n", " ")[:500] for doc in exam_docs[:5]
    )
    return (
        f"{subject} target {target_score}/100. Find knowledge points that match "
        f"these exam styles, homework patterns, common question types, and difficulty: "
        f"{exam_context}"
    )


def generate_markdown(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    knowledge_docs: list[Document],
    exam_docs: list[Document],
) -> str:
    if not settings.deepseek_api_key:
        return build_fallback_markdown(
            subject,
            target_score,
            knowledge_files,
            exam_files,
            knowledge_docs,
            exam_docs,
        )

    llm = ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.chat_base_url,
        temperature=0.2,
    )
    prompt = build_review_prompt(
        subject=subject,
        target_score=target_score,
        knowledge_files=knowledge_files,
        exam_files=exam_files,
        knowledge_docs=knowledge_docs,
        exam_docs=exam_docs,
    )
    response = llm.invoke(prompt)
    return str(response.content)


def build_fallback_markdown(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    knowledge_docs: list[Document],
    exam_docs: list[Document],
) -> str:
    return f"""# {subject} 目标{target_score}分复习方案

## 资料分析

### 知识库资料
{_bullet_list(knowledge_files)}

### 本校出题参考资料
{_bullet_list(exam_files)}

## 目标分数策略

{_score_strategy(target_score)}

## 检索到的知识库线索

{_format_docs(knowledge_docs)}

## 检索到的本校出题风格线索

{_format_docs(exam_docs)}

## 下一步

当前环境没有检测到 `DEEPSEEK_API_KEY`，因此已完成本地 Chroma 索引和证据片段汇总。配置模型后重新运行，可生成完整的知识点分层、复习建议和配套练习题。
"""


def _score_strategy(target_score: int) -> str:
    if target_score < 70:
        return "以过线为核心，优先掌握定义、公式、基础例题和作业中反复出现的常规题。"
    if target_score < 85:
        return "基础题必须稳定，中等题尽量覆盖，暂时放弃少量高难综合题。"
    if target_score < 95:
        return "基础和中等题都要稳定，重点训练本校高频综合题和易错题型。"
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
