"""Load and validate department configuration."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Department


DEFAULT_CONFIG = Path(__file__).parent / "departments.json"


def load_departments(path: Path | str = DEFAULT_CONFIG) -> dict[str, Department]:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    departments: dict[str, Department] = {}

    for item in payload.get("departments", []):
        department = Department(
            id=item["id"],
            name=item["name"],
            executive=item["executive"],
            mandate=item["mandate"],
            keywords=tuple(keyword.lower() for keyword in item["keywords"]),
            instructions=item["instructions"],
        )
        if department.id in departments:
            raise ValueError(f"Duplicate department id: {department.id}")
        departments[department.id] = department

    if not departments:
        raise ValueError("Department configuration must contain at least one department")
    if "executive_strategy" not in departments:
        raise ValueError("Department configuration requires executive_strategy fallback")
    return departments
