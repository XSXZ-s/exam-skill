from pathlib import Path
import sys

from app.config import RESOURCES_DIR
from app.schemas import ReviewRequest
from app.services.document_quality import inspect_files, low_quality_files
from app.services.document_loader import discover_files, discover_subjects
from app.services.review_service import run_review


def main() -> None:
    _configure_stdio()
    subjects = discover_subjects(RESOURCES_DIR)
    if not subjects:
        print("未在 resources/ 下发现学科文件夹。请先创建例如 resources/gaoshu 并放入资料。")
        return

    subject = _choose_one("发现以下学科资源：", subjects)
    subject_dir = RESOURCES_DIR / subject
    files = discover_files(subject_dir)
    if not files:
        print(f"已选择：{subject}")
        print("该学科目录下没有发现支持的资料文件。支持：pdf、pptx、docx、txt、md。")
        return
    instruction_candidates = [p for p in files if p.suffix.lower() in {".txt", ".md"}]

    print(f"\n已选择：{subject}")
    knowledge_files = _choose_many(
        title="\n请选择作为【知识库】的资料编号，可多选，用逗号分隔。",
        hint="知识库用于确定本学科需要掌握的完整知识范围，例如教材、课件、讲义、笔记。",
        files=files,
    )
    exam_files = _choose_many(
        title="\n请选择作为【出题参考资料】的资料编号，可多选，用逗号分隔。",
        hint="这些资料用于分析出题风格、常考题型、难度水平和重点偏好。推荐选择课后作业、历年试卷、平时测验、复习题、老师重点题。",
        files=files,
    )
    instruction_files = _choose_many(
        title="\n请选择作为【额外需求描述】的文件编号，可多选，用逗号分隔；直接回车跳过。",
        hint="这类文件会原样作为本次提示性指令传给模型，不会进入知识库或向量检索。推荐使用 txt/md 描述本次输出要求、老师口头提示、复习偏好。",
        files=instruction_candidates,
        required=False,
    )
    target_score = _ask_score()

    print("\n复习任务配置如下：")
    print(f"学科：{subject}")
    print("知识库资料：")
    for path in knowledge_files:
        print(f"- {path.name}")
    print("出题参考资料：")
    for path in exam_files:
        print(f"- {path.name}")
    print("额外需求描述：")
    if instruction_files:
        for path in instruction_files:
            print(f"- {path.name}")
    else:
        print("- 未选择")
    print(f"目标分数：{target_score}")

    confirm = input("\n是否开始分析？Y/n: ").strip().lower()
    if confirm not in {"", "y", "yes"}:
        print("已取消。")
        return

    quality_reports = inspect_files(knowledge_files + exam_files, subject=subject)
    low_quality = low_quality_files(quality_reports)
    if low_quality:
        print("\n以下资料提取到的文字较少，可能影响分析准确性：")
        for report in low_quality:
            print(
                f"- {report.path.name}: {report.extracted_chars} 字符，"
                f"{report.chunk_count} 个片段。{report.message}"
            )
        if not _ask_yes_no("是否仍然继续分析？y/N: ", default=False):
            print("已停止。请先将扫描件/图片型资料手动转为文本，或替换为可提取文字的资料后再运行。")
            return

    result = run_review(
        ReviewRequest(
            subject=subject,
            knowledge_files=knowledge_files,
            exam_files=exam_files,
            instruction_files=instruction_files,
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


def _choose_many(
    title: str,
    hint: str,
    files: list[Path],
    required: bool = True,
) -> list[Path]:
    while True:
        print(title)
        print(hint)
        if not files:
            if required:
                print("没有可选文件。")
            else:
                print("没有可选的 txt/md 文件，已跳过。")
                return []
        for i, path in enumerate(files, start=1):
            print(f"{i}. {path.name}")
        raw = input("请输入编号，例如 1,2,4：").strip()
        if not raw and not required:
            return []
        indexes = _parse_indexes(raw, len(files))
        if indexes:
            return [files[i - 1] for i in indexes]
        if required:
            print("输入无效，请至少选择一个有效编号。")
        else:
            print("输入无效，请输入有效编号，或直接回车跳过。")


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


def _ask_yes_no(prompt: str, default: bool) -> bool:
    raw = input(prompt).strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def _configure_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    main()
