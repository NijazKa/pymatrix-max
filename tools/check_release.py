#!/usr/bin/env python3
"""Fail when a public source tree contains common runtime secrets or backups."""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_NAMES = {
    "config.yaml",
    "registration.yaml",
    "session.db",
    "device-profile.json",
    ".env",
}
FORBIDDEN_PARTS = {"sessions", "backups"}
FORBIDDEN_PATTERNS = (
    re.compile(r".*\.db(?:[-.].*)?$", re.IGNORECASE),
    re.compile(r".*\.sqlite(?:3)?(?:[-.].*)?$", re.IGNORECASE),
    re.compile(r".*\.before-.*", re.IGNORECASE),
    re.compile(r".*\.backup-.*", re.IGNORECASE),
    re.compile(r"mautrix_max\.backup-.*", re.IGNORECASE),
)
TEXT_SUFFIXES = {
    "",
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".txt",
    ".cff",
    ".ini",
    ".env",
}
SECRET_PATTERNS = (
    re.compile(
        r"(?im)^\s*(?:as_token|hs_token|access_token|admin_token)\s*:\s*"
        r"[\"']?(?!GENERATE ME|CHANGEME|REPLACE_ME|<)[A-Za-z0-9._~+/=-]{20,}"
    ),
    re.compile(r"(?i)Authorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9_-]{32,}"),
)


def tracked_or_present_files() -> list[Path]:
    """Return tracked files in Git, or current files for an exported source tree."""
    import subprocess

    if (ROOT / ".git").exists():
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        return [
            ROOT / item.decode("utf-8")
            for item in result.stdout.split(b"\0")
            if item
        ]
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
        and ".venv" not in path.parts
    ]


def is_forbidden_path(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if relative == Path("data/.gitignore"):
        return False
    if path.name in FORBIDDEN_NAMES:
        return True
    if any(part in FORBIDDEN_PARTS for part in relative.parts):
        return True
    return any(pattern.fullmatch(path.name) for pattern in FORBIDDEN_PATTERNS)


def scan_paths() -> list[str]:
    errors: list[str] = []
    for path in tracked_or_present_files():
        if is_forbidden_path(path):
            errors.append(f"forbidden runtime/backup file: {path.relative_to(ROOT)}")
    return errors


def scan_text() -> list[str]:
    errors: list[str] = []
    for path in tracked_or_present_files():
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"possible secret in: {path.relative_to(ROOT)}")
                break
    return errors


def check_version() -> list[str]:
    errors: list[str] = []
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = str(pyproject["project"]["version"])
    init_text = (ROOT / "mautrix_max/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)', init_text)
    if not match:
        errors.append("mautrix_max.__version__ not found")
    elif match.group(1) != project_version:
        errors.append(
            f"version mismatch: pyproject={project_version}, package={match.group(1)}"
        )
    return errors


def main() -> int:
    errors = scan_paths() + scan_text() + check_version()
    if errors:
        print("Public release audit failed:", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Public release audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
