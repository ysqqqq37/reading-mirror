#!/usr/bin/env python3
"""Validate Reading Mirror's required WeRead Skill before touching user data."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable


CANONICAL_SKILL_NAME = "weread-skills"
ACCEPTED_SKILL_NAMES = {CANONICAL_SKILL_NAME, "wereadskill"}


class DependencyError(RuntimeError):
    """A required runtime dependency is absent or unusable."""


def _frontmatter(content: str, path: Path) -> str:
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        raise DependencyError(f"WeRead Skill has invalid frontmatter: {path}")
    return match.group(1)


def _field(frontmatter: str, field: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(field)}:\s*['\"]?([^'\"\s#]+)", frontmatter)
    return match.group(1) if match else None


def candidate_skill_files(extra_roots: Iterable[Path] = ()) -> list[Path]:
    """Return deterministic candidates without treating backup folders as installed Skills."""
    candidates: list[Path] = []
    configured = os.environ.get("WEREAD_SKILL_DIR")
    if configured:
        configured_path = Path(configured).expanduser()
        candidates.append(configured_path if configured_path.name == "SKILL.md" else configured_path / "SKILL.md")

    roots = list(extra_roots)
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        roots.append(Path(codex_home).expanduser() / "skills")
    roots.extend([Path.home() / ".agents" / "skills", Path.home() / ".codex" / "skills"])
    for root in roots:
        for name in (CANONICAL_SKILL_NAME, "wereadskill"):
            candidates.append(root / name / "SKILL.md")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.expanduser().resolve(strict=False))
        if key not in seen:
            seen.add(key)
            unique.append(Path(key))
    return unique


def discover_weread_skill(extra_roots: Iterable[Path] = ()) -> dict[str, Any]:
    """Find and structurally validate the active WeRead data-access Skill."""
    invalid: list[str] = []
    for path in candidate_skill_files(extra_roots):
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
            frontmatter = _frontmatter(content, path)
            name = _field(frontmatter, "name")
            version = _field(frontmatter, "version")
            if name not in ACCEPTED_SKILL_NAMES:
                raise DependencyError(f"unexpected Skill name {name!r}")
            if not version:
                raise DependencyError("missing version")
            notes_path = path.parent / "notes.md"
            if not notes_path.is_file():
                raise DependencyError("missing notes.md")
            return {
                "name": name,
                "version": version,
                "directory": str(path.parent),
                "skill_file": str(path),
                "notes_file": str(notes_path),
            }
        except (OSError, UnicodeError, DependencyError) as exc:
            invalid.append(f"{path}: {exc}")

    message = (
        "Required WeRead Skill is not installed or usable. "
        "Install or enable `weread-skills`, then retry Reading Mirror."
    )
    if invalid:
        message += " Invalid candidates: " + "; ".join(invalid)
    raise DependencyError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-api-key",
        action="store_true",
        help="Also require WEREAD_API_KEY without printing its value",
    )
    args = parser.parse_args()
    try:
        skill = discover_weread_skill()
        api_key_configured = bool(os.environ.get("WEREAD_API_KEY"))
        if args.require_api_key and not api_key_configured:
            raise DependencyError(
                "WEREAD_API_KEY is not configured. Follow the installed weread-skills authentication instructions."
            )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "weread_skill": {"name": skill["name"], "version": skill["version"]},
                    "api_key_configured": api_key_configured,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except DependencyError as exc:
        print(
            json.dumps(
                {"status": "missing_dependency", "dependency": CANONICAL_SKILL_NAME, "message": str(exc)},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
