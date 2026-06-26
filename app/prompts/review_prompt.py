from langchain_core.documents import Document


def build_review_prompt(
    subject: str,
    target_score: int,
    knowledge_files: list[str],
    exam_files: list[str],
    user_instruction: str,
    exam_profile: str,
    knowledge_docs: list[Document],
    exam_docs: list[Document],
) -> str:
    return f"""
你是一个高效复习规划助手。请基于知识库资料和出题参考资料，为用户生成 Markdown 复习方案。

学科：{subject}
目标分数：{target_score}/100

知识库资料：
{_bullet_list(knowledge_files)}

出题参考资料：
{_bullet_list(exam_files)}

用户本次额外要求：
{user_instruction or "无"}

出题风格画像：
{exam_profile or "未生成。"}

知识库检索片段：
{_format_docs(knowledge_docs)}

出题参考资料检索片段：
{_format_docs(exam_docs)}

请输出：
1. 资料分析
2. 出题风格画像摘要
3. 目标分数策略
4. 必须掌握知识点
5. 建议掌握知识点
6. 冲刺高分知识点
7. 当前目标下可暂缓内容
8. 每个重要知识点后附 2-4 道练习题

要求：
- 使用 Markdown。
- 优先满足“用户本次额外要求”，但不要把额外要求当作资料证据。
- 明确说明依据来自知识库还是出题参考资料。
- 不要承诺押题命中，只能表达高频、重点、建议掌握。
- 练习题要贴近出题风格画像，但不要照抄原题。
- 涉及数值计算、选择题或公式推导时，必须保证公式、代入、计算过程和最终答案一致。
- 如果计算结果与给定选项不一致，不要为了匹配选项强行改答案；应明确写出“按计算结果为 X，选项中没有匹配项，疑似题目或选项有误”。
- 如果发现前后结论冲突，必须以可复核的计算过程为准，并提示冲突来源。
- 内容要适合直接拿来复习。
""".strip()


def build_exam_profile_prompt(
    subject: str,
    target_score: int,
    exam_files: list[str],
    user_instruction: str,
    exam_docs: list[Document],
) -> str:
    return f"""
你是一个考试资料分析助手。请只基于“出题参考资料”检索片段，生成出题风格画像。

学科：{subject}
目标分数：{target_score}/100

出题参考资料：
{_bullet_list(exam_files)}

用户本次额外要求：
{user_instruction or "无"}

出题参考资料检索片段：
{_format_docs(exam_docs)}

请输出 Markdown，包含：
1. 高频题型
2. 高频知识点或章节线索
3. 难度分布和常见考法
4. 容易失分点
5. 目标分数下的优先级建议
6. 用于检索知识库的关键词列表

要求：
- 只能表达“根据资料显示/推测”，不要承诺押题命中。
- 如果资料不足，请明确写出不足。
- 关键词列表要使用中文为主，可补充必要英文术语。
- 分析题型时不要为了迎合资料中的答案或选项而改变计算结论；若题目答案与计算过程冲突，应把它标为疑似错题或选项异常。
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
