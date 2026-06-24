from langchain_core.documents import Document


def build_review_prompt(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    knowledge_docs: list[Document],
    exam_docs: list[Document],
) -> str:
    return f"""
你是一个高效复习规划助手。请基于知识库资料和本校出题参考资料，为用户生成 Markdown 复习方案。

学科：{subject}
目标分数：{target_score}/100

知识库资料：
{_bullet_list(knowledge_files)}

本校出题参考资料：
{_bullet_list(exam_files)}

知识库检索片段：
{_format_docs(knowledge_docs)}

本校出题参考资料检索片段：
{_format_docs(exam_docs)}

请输出：
1. 资料分析
2. 目标分数策略
3. 必须掌握知识点
4. 建议掌握知识点
5. 冲刺高分知识点
6. 当前目标下可暂缓内容
7. 每个重要知识点后附 2-4 道练习题

要求：
- 使用 Markdown。
- 明确说明依据来自知识库还是本校出题参考资料。
- 不要承诺押题命中，只能表达高频、重点、建议掌握。
- 内容要适合直接拿来复习。
""".strip()


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

