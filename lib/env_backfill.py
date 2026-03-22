from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path


def backfill_env_file(env_path: Path, updates: Mapping[str, str]) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_updates = {
        key: value
        for key, value in updates.items()
        if value is not None and value != ""
    }
    if not normalized_updates:
        return

    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    rendered_lines: list[str] = []
    seen_keys: set[str] = set()
    for raw_line in existing_lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            rendered_lines.append(raw_line)
            continue

        key, _value = raw_line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in normalized_updates:
            rendered_lines.append(
                f"{normalized_key}={normalized_updates[normalized_key]}"
            )
            seen_keys.add(normalized_key)
            continue

        rendered_lines.append(raw_line)

    missing_keys = [key for key in normalized_updates if key not in seen_keys]
    if missing_keys:
        if rendered_lines and rendered_lines[-1].strip():
            rendered_lines.append("")
        for key in missing_keys:
            rendered_lines.append(f"{key}={normalized_updates[key]}")

    env_path.write_text("\n".join(rendered_lines) + "\n", encoding="utf-8")
