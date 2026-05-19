from pathlib import Path
import json

CONFIG_DIR = Path.home() / ".config" / "winder"
CONFIG_FILE = CONFIG_DIR / "recent_files.json"
MAX_RECENT = 10


def load_recent() -> list[str]:
    if not CONFIG_FILE.exists():
        return []
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def add_recent(path: str) -> None:
    recent = load_recent()
    path = str(Path(path).resolve())
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    recent = recent[:MAX_RECENT]
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(recent, f)


def clear_recent() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)
