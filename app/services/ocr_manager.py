from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import importlib.util
from pathlib import Path
import subprocess
import sys
import threading
from uuid import uuid4

from app.config import ROOT_DIR


OCR_PACKAGES = ["paddleocr", "paddlepaddle", "pymupdf"]
TASKS: dict[str, "InstallTask"] = {}
_LOCK = threading.Lock()


@dataclass
class InstallTask:
    id: str
    status: str = "running"
    message: str = "正在安装本地 OCR 增强包..."
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    finished_at: str | None = None
    return_code: int | None = None
    log_path: Path | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "message": self.message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "log_path": str(self.log_path) if self.log_path else None,
        }


def ocr_status() -> dict:
    paddleocr_available = importlib.util.find_spec("paddleocr") is not None
    paddle_available = importlib.util.find_spec("paddle") is not None
    pymupdf_available = importlib.util.find_spec("fitz") is not None
    installed = paddleocr_available and paddle_available and pymupdf_available
    return {
        "installed": installed,
        "engine": "PaddleOCR",
        "packages": {
            "paddleocr": paddleocr_available,
            "paddlepaddle": paddle_available,
            "pymupdf": pymupdf_available,
        },
        "message": (
            "本地 OCR 增强包已可用。"
            if installed
            else "本地 OCR 增强包尚未完整安装。扫描 PDF、图片课件和截图资料可能无法自动识别。"
        ),
    }


def start_ocr_install() -> dict:
    status = ocr_status()
    if status["installed"]:
        return {
            "installed": True,
            "task": None,
            "message": "本地 OCR 增强包已安装，无需重复安装。",
        }

    with _LOCK:
        running = next((task for task in TASKS.values() if task.status == "running"), None)
        if running:
            return {
                "installed": False,
                "task": running.to_dict(),
                "message": "已有 OCR 安装任务正在运行。",
            }

        task_id = f"ocr_install_{uuid4().hex[:12]}"
        log_dir = ROOT_DIR / ".cache" / "ocr"
        log_dir.mkdir(parents=True, exist_ok=True)
        task = InstallTask(
            id=task_id,
            log_path=log_dir / f"{task_id}.log",
        )
        TASKS[task_id] = task

    thread = threading.Thread(target=_run_install, args=(task,), daemon=True)
    thread.start()
    return {
        "installed": False,
        "task": task.to_dict(),
        "message": "已开始安装本地 OCR 增强包，请保持后端服务运行。",
    }


def get_task(task_id: str) -> dict | None:
    task = TASKS.get(task_id)
    return task.to_dict() if task else None


def _run_install(task: InstallTask) -> None:
    command = [sys.executable, "-m", "pip", "install", *OCR_PACKAGES]
    assert task.log_path is not None
    try:
        with task.log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            log_file.write(f"Command: {' '.join(command)}\n\n")
            log_file.flush()
            process = subprocess.run(
                command,
                cwd=str(ROOT_DIR),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        task.return_code = process.returncode
        task.finished_at = datetime.now().isoformat(timespec="seconds")
        if process.returncode == 0:
            task.status = "success"
            task.message = "本地 OCR 增强包安装完成。"
        else:
            task.status = "failed"
            task.message = "本地 OCR 增强包安装失败，请查看安装日志或手动安装。"
    except Exception as exc:
        task.status = "failed"
        task.message = f"本地 OCR 增强包安装失败：{exc}"
        task.finished_at = datetime.now().isoformat(timespec="seconds")
