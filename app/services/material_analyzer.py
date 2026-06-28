from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha1, sha256
import json
from pathlib import Path
import re
from typing import Any

from app.config import ROOT_DIR
from app.services.document_loader import load_documents


ANALYZER_VERSION = "material_analyzer_v2"
SAMPLE_LIMIT = 4000


@dataclass
class MaterialFileMeta:
    path: str
    content_hash: str
    material_type: str
    detected_chapters: list[str]
    confidence: float
    reason: str
    sample_chars: int = 0


@dataclass
class MaterialGroup:
    group_id: str
    chapter: str | None
    knowledge_files: list[str] = field(default_factory=list)
    exam_files: list[str] = field(default_factory=list)
    instruction_files: list[str] = field(default_factory=list)
    other_files: list[str] = field(default_factory=list)


def analyze_materials(subject: str, subject_dir: Path, paths: list[Path]) -> dict:
    manifest = _load_manifest(subject)
    metas = [_analyze_one(subject_dir, path, manifest) for path in paths]
    _save_manifest(subject, manifest)
    groups = _group_materials(metas)
    selected_fingerprint = _selected_fingerprint(metas)
    return {
        "subject": subject,
        "analyzer_version": ANALYZER_VERSION,
        "selected_fingerprint": selected_fingerprint,
        "files": [asdict(meta) for meta in metas],
        "groups": [asdict(group) for group in groups],
        "summary": _build_summary(groups),
    }


def _analyze_one(subject_dir: Path, path: Path, manifest: dict[str, Any]) -> MaterialFileMeta:
    relative_path = str(path.relative_to(subject_dir))
    content_hash = _hash_file(path)
    cache_key = sha1(f"{ANALYZER_VERSION}:{content_hash}:{relative_path.lower()}".encode("utf-8")).hexdigest()
    cached = manifest["files"].get(cache_key)
    if cached:
        return MaterialFileMeta(**cached)

    sample = _extract_sample(path)
    chapters = _detect_chapters(relative_path, sample)
    material_type, confidence, reason = _detect_material_type(path.name, sample)
    meta = MaterialFileMeta(
        path=relative_path,
        content_hash=content_hash,
        material_type=material_type,
        detected_chapters=chapters,
        confidence=confidence,
        reason=reason,
        sample_chars=len(sample),
    )
    manifest["files"][cache_key] = asdict(meta)
    return meta


def _detect_material_type(filename: str, sample: str) -> tuple[str, float, str]:
    name = filename.lower()
    sample_lower = sample.lower()

    instruction_patterns = [
        r"add",
        r"instruction",
        r"requirement",
        r"需求",
        r"要求",
        r"提示",
        r"说明",
        r"老师",
    ]
    exam_patterns = [
        r"test",
        r"exam",
        r"quiz",
        r"homework",
        r"practice",
        r"exercise",
        r"program_test",
        r"mid",
        r"习题",
        r"练习",
        r"作业",
        r"试卷",
        r"测验",
        r"题",
    ]
    knowledge_patterns = [
        r"knowledge",
        r"review",
        r"summary",
        r"target\d+",
        r"chapter",
        r"lecture",
        r"slide",
        r"textbook",
        r"复习",
        r"方案",
        r"总结",
        r"课件",
        r"教材",
        r"讲义",
        r"笔记",
        r"学习",
    ]

    if _matches_any(name, instruction_patterns) and not _matches_any(name, exam_patterns):
        return "instruction", 0.86, "文件名包含需求/说明类关键词。"
    if _matches_any(name, knowledge_patterns) or re.search(r"\bch[-_ ]?\d{1,2}\b", name):
        return "knowledge", 0.9, "文件名包含章节课件/知识类关键词。"
    if _matches_any(name, exam_patterns):
        return "exam", 0.92, "文件名包含习题/考试类关键词。"

    if re.search(r"(单选题|多选题|判断题|正确答案|答案[:：]|解析[:：]|综合编程题)", sample):
        return "exam", 0.78, "正文包含题目、答案或解析特征。"
    if re.search(r"(学习目标|学习笔记|本章小结|知识点|概述|开发流程)", sample):
        return "knowledge", 0.74, "正文包含课件/讲义类结构。"
    if re.search(r"(请帮我|需要|要求|建议|提示)", sample_lower):
        return "instruction", 0.62, "正文包含需求描述特征。"
    return "other", 0.35, "未识别到明确资料类型。"


def _detect_chapters(relative_path: str, sample: str) -> list[str]:
    chapters: list[str] = []
    text = f"{relative_path}\n{sample[:1500]}"
    patterns = [
        r"(?:^|[/\\\s_-])ch[-_ ]?0?(\d{1,2})(?:\D|$)",
        r"(?:chapter|chap)[-_ ]?0?(\d{1,2})(?:\D|$)",
        r"第\s*([0-9]{1,2})\s*[章节章]",
        r"第\s*([一二三四五六七八九十]{1,3})\s*[章节章]",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw = match.group(1)
            number = _chapter_number(raw)
            if number is not None:
                chapter = f"ch{number:02d}"
                if chapter not in chapters:
                    chapters.append(chapter)
    return chapters


def _group_materials(metas: list[MaterialFileMeta]) -> list[MaterialGroup]:
    groups: dict[str, MaterialGroup] = {}
    for meta in metas:
        if meta.material_type == "instruction":
            chapter = None
            group_id = "instructions"
        else:
            chapter = meta.detected_chapters[0] if meta.detected_chapters else None
            group_id = chapter or "unassigned"
        group = groups.setdefault(group_id, MaterialGroup(group_id=group_id, chapter=chapter))
        target = {
            "knowledge": group.knowledge_files,
            "exam": group.exam_files,
            "instruction": group.instruction_files,
        }.get(meta.material_type, group.other_files)
        target.append(meta.path)
    return sorted(groups.values(), key=lambda group: (group.chapter is None, group.group_id))


def _build_summary(groups: list[MaterialGroup]) -> str:
    if not groups:
        return "未选择资料。"
    if len(groups) == 1:
        group = groups[0]
        if group.chapter:
            return f"识别为单章资料：{group.chapter}。"
        return "识别为未标注章节的单主题/补充资料。"
    chapters = [group.chapter for group in groups if group.chapter]
    if chapters:
        return f"识别为多章节资料：{', '.join(chapters)}。"
    return "识别为多组未标注章节资料。"


def _extract_sample(path: Path) -> str:
    try:
        if path.suffix.lower() in {".txt", ".md"}:
            return path.read_text(encoding="utf-8", errors="ignore")[:SAMPLE_LIMIT]
        documents = load_documents([path])
        parts = []
        for doc in documents:
            content = doc.page_content.strip()
            if content:
                parts.append(content)
            if sum(len(part) for part in parts) >= SAMPLE_LIMIT:
                break
        return "\n".join(parts)[:SAMPLE_LIMIT]
    except Exception:
        return ""


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _chapter_number(raw: str) -> int | None:
    if raw.isdigit():
        value = int(raw)
        return value if 0 < value < 100 else None
    chinese_digits = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if raw == "十":
        return 10
    if raw.startswith("十") and len(raw) == 2:
        return 10 + chinese_digits.get(raw[1], 0)
    if raw.endswith("十") and len(raw) == 2:
        return chinese_digits.get(raw[0], 0) * 10
    if "十" in raw and len(raw) == 3:
        return chinese_digits.get(raw[0], 0) * 10 + chinese_digits.get(raw[2], 0)
    return chinese_digits.get(raw)


def _selected_fingerprint(metas: list[MaterialFileMeta]) -> str:
    raw = json.dumps(
        [
            {
                "path": meta.path,
                "content_hash": meta.content_hash,
                "material_type": meta.material_type,
                "detected_chapters": meta.detected_chapters,
            }
            for meta in sorted(metas, key=lambda item: item.path.lower())
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return sha256(f"{ANALYZER_VERSION}:{raw}".encode("utf-8")).hexdigest()


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(subject: str) -> Path:
    return ROOT_DIR / ".cache" / "material_analysis" / subject / "manifest.json"


def _load_manifest(subject: str) -> dict[str, Any]:
    path = _manifest_path(subject)
    if not path.exists():
        return {"version": 1, "files": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "files": {}}


def _save_manifest(subject: str, manifest: dict[str, Any]) -> None:
    path = _manifest_path(subject)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
