# Exam Skill

Exam Skill 是一个本地 RAG 复习方案生成工具。它会读取 `resources/` 下的课件、教材、讲义、作业、试卷和额外需求，结合目标分数生成 Markdown 复习方案，并支持在本地网页中预览结果和继续追问。

## 快速开始

1. 安装 Python 3.10 或更高版本。
2. 解压项目。
3. 双击 `install.bat` 安装环境，或使用你自己的 Python/conda 环境安装依赖。
4. 在 `.env` 中填写模型配置。
5. 把资料放入 `resources/<subject>/`。
6. 双击 `run_api.bat` 打开本地网页，或双击 `run_cli.bat` 使用终端交互版。

如果默认安装源较慢，可双击 `install_cn.bat` 使用清华 PyPI 镜像源。

## 模型配置

默认使用 OpenAI-compatible API：

```env
LLM_API_KEY=your_api_key
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
```

本地 embedding 模型用于 Chroma 向量索引。首次生成时可能需要下载或检查模型文件：

```env
HF_ENDPOINT=https://hf-mirror.com
```

如果镜像源不可用，可改为：

```env
HF_ENDPOINT=https://huggingface.co
```

## 支持格式

推荐资料格式：

- `.md`
- `.txt`
- `.docx`
- `.pptx`
- 可搜索文本型 `.pdf`

图片、截图、扫描件、图片型 PDF 不再由项目内置 OCR 处理。请先使用系统工具、WPS、微信、浏览器插件或其他 OCR 工具手动转为 Markdown、TXT、Word 或可搜索 PDF 后再放入 `resources/`。

## 目录约定

```text
resources/
  JavaWeb/
    ch03-knowledge.pdf
    test03.md
    add.txt
```

`output/` 保存生成的 Markdown 复习方案。  
`chroma_db/` 保存本地向量库缓存。  
`.cache/` 保存资料识别、语义拆分、题目结构化和单章中间产物缓存。

## 使用建议

可以只选择某一章，也可以选择多章或整门课程资料。系统会自动识别：

- 知识资料：课件、教材、讲义、笔记
- 出题参考：习题、作业、试卷、测验
- 额外需求：`add.txt`、说明、老师口头重点等

如果文件名不明显，建议在文档开头写明资料归属，例如：

```text
这是第3章 Servlet 的课件。
这是第3章 JSP 的习题。
这是 JavaWeb 期末复习的额外要求。
```

这类说明放在文档开头最有效，可以帮助系统更快、更准地识别章节和资料类型。

## 生成流程

当前第一版优化后的主流程为：

1. 检查所选资料能否提取到足够文字。
2. 自动识别资料类型和章节范围。
3. 缓存资料识别结果。
4. 对知识资料做语义拆分，保留章节、标题路径、来源文件等 metadata。
5. 对习题资料按单题拆分，保留题号、作业标题、来源文件等 metadata。
6. 将语义 chunk 写入 Chroma 双库：`knowledge` 和 `exam`。
7. 对题目 chunk 批量生成结构化题目画像，并缓存 question profile。
8. 用题目画像拼接 query，反向检索知识库原文 chunk。
9. 按章节生成单章中间产物，并缓存 `brief.json` 和 `brief.md`。
10. 最终方案只综合单章中间产物，不再直接吞大段原文。

语义拆分缓存：

```text
.cache/semantic_chunks/<subject>/<knowledge|exam>/<文件内容hash>/chunks.json
```

题目结构化缓存：

```text
.cache/question_profiles/<subject>/<文件内容hash>/<题目chunk_id>.json
```

单章中间产物缓存：

```text
.cache/chapter_briefs/<subject>/<chapter>/brief.json
.cache/chapter_briefs/<subject>/<chapter>/brief.md
```

## 额外需求

额外需求文件只支持 `.txt` / `.md`，会作为本次生成的 prompt 指令传给模型，不进入 Chroma，也不会被拆分或 embedding。适合写：

- 本次输出要求
- 老师口头提示
- 复习偏好
- 需要重点关注的题型

## 扫描件和图片资料

项目已移除内置本地 OCR。这样可以保持个人工具更轻量、依赖更清爽，也避免 PaddleOCR 等大包带来的安装、缓存和稳定性问题。

如果选择的资料提取文字过少，网页会提示可能是扫描件、图片型 PDF 或格式解析失败。请先手动转为文本类资料后再生成。

低质量阈值可在 `.env` 中调整：

```env
MIN_EXTRACTED_CHARS=200
```

## 本地网页

双击 `run_api.bat` 后打开：

```text
http://127.0.0.1:8000/
```

网页支持：

- 选择学科和资料
- 生成复习方案
- 选择并预览历史输出
- 在预览 / 源码之间切换
- 基于当前输出继续追问

接口文档：

```text
http://127.0.0.1:8000/docs
```

## 常用脚本

- `install.bat`：安装环境，创建 `.venv` 并安装依赖
- `install_cn.bat`：使用清华 PyPI 镜像源安装
- `run_api.bat`：启动本地网页
- `run_cli.bat`：启动终端交互版
- `reset.bat`：删除 `.venv`、`.cache`、`chroma_db`，重置本地生成状态

`reset.bat` 不会删除 `resources`、`output`、`.env` 或项目代码。

## 费用说明

Chroma、本地 embedding、文件解析和网页本身都在本地运行，不按量收费。可能产生费用的是 `LLM_API_KEY` 对应的大模型服务调用。

当前流程的主要 LLM 消耗来自：

- 题目结构化解析
- 单章中间产物生成
- 最终总方案生成
- 继续追问

embedding 和向量检索通常不消耗模型 API 额度；如果未来改用云端 embedding API，则会产生对应费用。
