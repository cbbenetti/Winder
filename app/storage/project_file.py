import json
from pathlib import Path

from app.models.project import Project

EXTENSION = ".winder"


def save_project(project: Project, path: str | Path) -> None:
    path = Path(path)
    if path.suffix != EXTENSION:
        path = path.with_suffix(EXTENSION)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project.to_dict(), f, indent=2)


def load_project(path: str | Path) -> Project:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Project.from_dict(data)
