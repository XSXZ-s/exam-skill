# Exam Skill

Exam Skill 是一个本地 RAG 复习方案生成工具。它会读取 `resources/` 下的课件、教材、讲义、作业、试卷和额外需求描述，结合目标分数生成 Markdown 复习方案，并支持在本地网页中预览结果和继续追问。

## 快速开始

1. 安装 Python 3.10 或更高版本。
2. 解压项目。
3. 双击 `install.bat` 安装环境。
4. 在 `.env` 中填写模型配置。
5. 把资料放入 `resources/<subject>/`。
6. 双击 `run_api.bat` 打开本地网页，或双击 `run_cli.bat` 使用终端交互版。

如果默认安装源较慢，可双击 `install_cn.bat` 使用清华 PyPI 镜像源。

## 模型配置

默认使用 DeepSeek 的 OpenAI-compatible API：

```env
LLM_API_KEY=your_api_key
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
```

如需使用其他 OpenAI-compatible 模型服务，只需要改这三项：

```env
LLM_API_KEY=your_api_key
LLM_MODEL=your_model_name
LLM_BASE_URL=https://your-provider-base-url
```

例如本地模型服务如果提供 OpenAI-compatible 接口，也可以这样配置：

```env
LLM_API_KEY=not-needed
LLM_MODEL=qwen2.5:7b
LLM_BASE_URL=http://127.0.0.1:11434/v1
```

不同服务商的模型名和 base URL 不同，请以对应服务商文档为准。

## 目录约定

```text
resources/
  JavaWeb/
    ch03-knowledge.pdf
    test03.md
    add.txt
```

支持的资料类型：

- `.pdf`
- `.pptx`
- `.docx`
- `.txt`
- `.md`

`output/` 会保存生成的 Markdown 复习方案。`chroma_db/` 是本地向量库缓存，可以删除后重新生成。

## 使用建议

建议优先按章节生成复习方案。每章选择对应课件/教材作为知识库资料，选择对应作业/试卷/测验作为出题参考资料。章节复习方案生成后，可复制到新的 `resources/<subject>_summary/` 目录，再把这些 Markdown 作为知识库输入，配合总复习题或历年试卷，生成全书级重点汇总。

## 额外需求描述

终端和网页中都有“额外需求描述”这一类输入。

这类文件只支持 `.txt` / `.md`，会原样作为本次 prompt 指令传给模型，不会进入 Chroma，也不会被拆分或 embedding。适合放：

- 本次输出要求
- 老师口头提示
- 复习偏好
- 需要重点关注的题型

## 本地网页

双击 `run_api.bat` 后会打开：

```text
http://127.0.0.1:8000/
```

网页支持：

- 选择学科和资料
- 生成复习方案
- 选择并预览历史输出
- 在“预览 / 源码”之间切换
- 基于当前输出继续追问

接口文档仍可访问：

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

## 扫描版 PDF

如果 PDF 是截图或扫描版，系统可能只能读取到页码或极少文字。请先用 OCR 工具转成可搜索 PDF 或 Markdown，再放入 `resources/`。

## 费用说明

Chroma、本地 embedding、文件解析和网页本身都在本地运行，不按量收费。可能产生费用的是 `LLM_API_KEY` 对应的大模型服务调用。
