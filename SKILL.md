---
name: exam-skill
description: Build exam-oriented review Markdown from local subject resources using automatic material grouping, semantic chunking, structured exam profiles, chapter briefs, and final synthesis.
---

# Exam Review Planner

## Core Idea

This project is a local personal study tool. It turns selected subject resources into a target-score review plan through a staged workflow:

- identify material type and chapter range from selected files;
- split knowledge materials and exercises into semantic chunks;
- structure exercise chunks into question profiles;
- retrieve matching knowledge evidence from the knowledge store;
- generate chapter briefs as reusable intermediate artifacts;
- synthesize the final Markdown only from chapter briefs.

Generate final Markdown under `output/<subject>/`.

## Supported Materials

The built-in parser supports:

- `.md`
- `.txt`
- `.docx`
- `.pptx`
- text-extractable `.pdf`

Scans, screenshots, images, and image-only PDFs are not handled by built-in OCR. Ask users to convert those files into text-oriented materials before generation.

## Local Stores

Use separate local stores and caches by subject:

- `chroma_db/<subject>/knowledge`: semantic chunks from textbooks, slides, notes, and other knowledge materials.
- `chroma_db/<subject>/exam`: semantic chunks from homework, quizzes, past papers, and other exam-style references.
- `.cache/material_analysis/<subject>/`: material type and chapter grouping.
- `.cache/semantic_chunks/<subject>/`: full semantic chunks with metadata.
- `.cache/question_profiles/<subject>/`: structured exercise/question profiles.
- `.cache/chapter_briefs/<subject>/`: per-chapter intermediate outputs.

## Workflow

1. Let the user select any relevant files for a subject.
2. Analyze selected files and group them by material type and detected chapter.
3. Inspect selected files for extractable text and stop when files look too low-quality unless the user confirms continuation.
4. Split and index knowledge and exam files with chapter/file metadata.
5. Convert exercise chunks into structured question profiles.
6. Use the structured exam profile as the query signal to retrieve matching knowledge evidence.
7. Generate per-chapter briefs and cache them.
8. Generate the final review plan from chapter briefs.

## Output Requirements

Create a Markdown file named:

`output/<subject>/<subject-slug>-target<score>-review-<number>.md`

The final plan should be practical rather than just a short list of retrieved points. It should include:

- selected knowledge and exam reference files;
- target-score strategy;
- must-learn topics;
- recommended topics;
- high-score topics;
- deferrable topics for the current target;
- common question patterns and traps;
- practice suggestions tied to evidence from the selected materials.
