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

首次运行 `install.bat` 需要下载并安装依赖，可能耗时较长，但通常只需安装一次。后续使用时只需要运行 `run_api.bat` 打开本地网页，或运行 `run_cli.bat` 使用终端交互版。

安装脚本会在项目文件夹内创建本地虚拟环境 `.venv`，依赖和项目缓存也只会保存在当前项目目录范围内，不会污染你电脑上的其他应用或文件。

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

## HuggingFace 下载源

项目会使用本地 embedding 模型建立 Chroma 向量索引。首次生成时可能需要从 HuggingFace 下载或检查模型文件。

`.env.example` 默认使用国内镜像源：

```env
HF_ENDPOINT=https://hf-mirror.com
```

如果镜像源连接失败，并且你有可用的 VPN 或代理，可以在 `.env` 中切换为官方源：

```env
HF_ENDPOINT=https://huggingface.co
```

这个配置只影响本地 embedding 模型的下载和检查，不影响 `LLM_API_KEY` 对应的大模型服务。

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

## 分析流程

生成时会按以下顺序处理：

1. 检查所选资料能否提取到足够文字。
2. 先从作业、试卷、测验等出题参考资料中生成“出题风格画像”。
3. 用出题风格画像反向检索知识库资料，找出匹配的知识点、题型和易错点。
4. 生成包含目标分数策略、重点分层和练习题的 Markdown 复习方案。

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

系统会在生成前检查所选资料的文字提取情况。如果某些资料提取文字过少，网页会弹窗提示并询问是否继续，终端版也会列出问题文件并要求确认。默认低质量阈值可在 `.env` 中调整：

```env
MIN_EXTRACTED_CHARS=200
```

这个检查不会进行 OCR，只用于避免扫描件或解析失败的资料悄悄影响结果。

## 费用说明

Chroma、本地 embedding、文件解析和网页本身都在本地运行，不按量收费。可能产生费用的是 `LLM_API_KEY` 对应的大模型服务调用。
