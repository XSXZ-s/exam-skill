from pathlib import Path
import sys

from app.config import RESOURCES_DIR
from app.schemas import ReviewRequest
from app.services.document_loader import discover_files, discover_subjects
from app.services.review_service import run_review


def main() -> None:
    _configure_stdio()
    subjects = discover_subjects(RESOURCES_DIR)
    if not subjects:
        print("未在 resources/ 下发现学科文件夹。请先创建例如 resources/高数 并放入资料。")
        return

    subject = _choose_one("发现以下学科资源：", subjects)
    subject_dir = RESOURCES_DIR / subject
    files = discover_files(subject_dir)
    if not files:
        print(f"已选择：{subject}")
        print("该学科目录下没有发现支持的资料文件。支持：pdf、pptx、docx、txt、md。")
        return

    print(f"\n已选择：{subject}")
    knowledge_files = _choose_many(
        title="\n请选择作为【知识库】的资料编号，可多选，用逗号分隔。",
        hint="知识库用于确定本学科需要掌握的完整知识范围，例如教材、课件、讲义、笔记。",
        files=files,
    )
    exam_files = _choose_many(
        title="\n请选择作为【本校出题参考资料】的资料编号，可多选，用逗号分隔。",
        hint="这些资料用于分析本校出题风格、常考题型、难度水平和重点偏好。推荐选择课后作业、历年试卷、平时测验、复习题、老师重点题。",
        files=files,
    )
    target_score = _ask_score()

    print("\n复习任务配置如下：")
    print(f"学科：{subject}")
    print("知识库资料：")
    for path in knowledge_files:
        print(f"- {path.name}")
    print("本校出题参考资料：")
    for path in exam_files:
        print(f"- {path.name}")
    print(f"目标分数：{target_score}")

    confirm = input("\n是否开始分析？Y/n: ").strip().lower()
    if confirm not in {"", "y", "yes"}:
        print("已取消。")
        return

    result = run_review(
        ReviewRequest(
            subject=subject,
            knowledge_files=knowledge_files,
            exam_files=exam_files,
            target_score=target_score,
        )
    )
    print(f"\n分析完成：{result.output_path}")


def _choose_one(title: str, items: list[str]) -> str:
    while True:
        print(f"\n{title}")
        for i, item in enumerate(items, start=1):
            print(f"{i}. {item}")
        raw = input("请选择编号：").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("输入无效，请重新选择。")


def _choose_many(title: str, hint: str, files: list[Path]) -> list[Path]:
    while True:
        print(title)
        print(hint)
        for i, path in enumerate(files, start=1):
            print(f"{i}. {path.name}")
        raw = input("请输入编号，例如 1,2,4：").strip()
        indexes = _parse_indexes(raw, len(files))
        if indexes:
            return [files[i - 1] for i in indexes]
        print("输入无效，请至少选择一个有效编号。")


def _parse_indexes(raw: str, max_index: int) -> list[int]:
    indexes: list[int] = []
    for part in raw.replace("，", ",").split(","):
        part = part.strip()
        if not part.isdigit():
            return []
        value = int(part)
        if value < 1 or value > max_index:
            return []
        if value not in indexes:
            indexes.append(value)
    return indexes


def _ask_score() -> int:
    while True:
        raw = input("\n请输入目标分数，满分按100分计算，例如 60 / 75 / 85 / 95 / 100：").strip()
        if raw.isdigit() and 0 <= int(raw) <= 100:
            return int(raw)
        print("分数无效，请输入 0 到 100 之间的整数。")


def _configure_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
