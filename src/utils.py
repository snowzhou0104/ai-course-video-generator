import json
from pathlib import Path
from typing import Any


def ensure_dir(path) -> None:
    """Create a directory (and any missing parents) if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)


def write_json_file(data: Any, path) -> None:
    """Write data as pretty-printed UTF-8 JSON, creating parent dirs as needed."""
    path = Path(path)
    ensure_dir(path.parent)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_json_file(path) -> Any:
    """Read and parse a UTF-8 JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
