from pathlib import Path
import os

from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[1]
RESOURCES_DIR = ROOT_DIR / "resources"
OUTPUT_DIR = ROOT_DIR / "output"
CHROMA_DIR = ROOT_DIR / "chroma_db"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv(ROOT_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


class AppSettings(BaseModel):
    chunk_size: int = Field(default=_env_int("CHUNK_SIZE", 900), ge=200)
    chunk_overlap: int = Field(default=_env_int("CHUNK_OVERLAP", 150), ge=0)
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    chat_model: str = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    chat_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    llm_api_key: str | None = os.getenv("LLM_API_KEY")
    retrieval_k: int = Field(default=_env_int("RETRIEVAL_K", 10), ge=1)
    retrieval_fetch_k: int = Field(default=_env_int("RETRIEVAL_FETCH_K", 30), ge=1)


settings = AppSettings()
