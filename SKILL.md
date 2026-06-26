---
name: exam-skill
description: Build efficient exam review Markdown from subject resources using local RAG with LangChain, Chroma, and FastAPI. Use when the user wants to split a subject knowledge base and exam-style reference materials, index them by subject, choose a target score, and generate prioritized study notes with practice questions.
---

# Exam Review Planner

## Core Idea

Use two separate local Chroma stores for each subject:

- `chroma_db/<subject>/knowledge`: textbooks, lecture slides, notes, and other materials defining the subject knowledge scope.
- `chroma_db/<subject>/exam`: homework, quizzes, past papers, review sheets, and other materials showing exam style, difficulty, and topic preference.

Generate final Markdown under `output/<subject>/`.

## Workflow

1. Scan `resources/` and ask the user to select a subject by number.
2. Scan all files under `resources/<subject>/`.
3. Ask the user to select knowledge base files.
4. Ask the user to select exam-style reference files.
5. Ask for a target score out of 100.
6. Inspect selected files for extractable text and warn when files look like scanned/image-only materials.
7. Ask whether to continue if low-quality files are detected.
8. Extract, split, embed, and persist selected files into the matching Chroma stores.
9. Retrieve from the `exam` store first and generate an exam style profile.
10. Use the exam style profile to retrieve matching knowledge points from the `knowledge` store.
11. Generate a Markdown review plan that separates must-learn, recommended, high-score, and deferrable topics.

## Terminology

Use "出题参考资料" for resources that reveal exam direction. Explain it as:

> 这些资料用于分析出题风格、常考题型、难度水平和重点偏好。推荐选择课后作业、历年试卷、平时测验、复习题、老师重点题。

## Output Requirements

Create a Markdown file named:

`output/<subject>/<subject>-目标<score>分-复习方案<number>.md`

Include:

- selected knowledge base files
- selected exam-style reference files
- an exam style profile summary
- target score strategy
- required topics
- recommended topics
- high-score topics
- topics that can be deferred for the current score target
- practice questions after each important topic
- brief evidence from retrieved resources whenever possible
