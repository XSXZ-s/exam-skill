# Exam Skill Agent Guide

This project builds a local RAG exam review planner.

Keep the runtime layout stable:

- `resources/<subject>/`: source files grouped by subject.
- `chroma_db/<subject>/knowledge/`: local Chroma store for textbooks, slides, notes, and other subject knowledge resources.
- `chroma_db/<subject>/exam/`: local Chroma store for homework, quizzes, past papers, review sheets, and other exam-style resources.
- `output/<subject>/`: generated Markdown review plans.

Application layout:

- `app/chains/`: LangChain and RAG generation logic.
- `app/prompts/`: prompt builders and reusable prompt text.
- `app/services/`: document loading, splitting, vector storage, Markdown writing, and orchestration.
- `app/schemas/`: Pydantic request and response models.

Keep `SKILL.md` in place because Codex skills require that exact filename for skill discovery. Use this `AGENT.md` as the project-level architecture guide.
