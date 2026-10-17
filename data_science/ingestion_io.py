"""Atomic local ingestion artifacts; no network or credential handling."""
import json
import os
from pathlib import Path
import tempfile


def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def atomic_json(path, content):
    atomic_bytes(path, (json.dumps(content, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode())
