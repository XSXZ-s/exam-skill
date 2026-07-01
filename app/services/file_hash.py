from __future__ import annotations

from hashlib import sha256
from pathlib import Path


HASH_CHUNK_SIZE = 1024 * 1024


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
