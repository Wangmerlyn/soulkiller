from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


MAX_TEXT_FILE_BYTES = 5 * 1024 * 1024

DENIED_EXACT_NAMES = {
    ".env",
    "auth.json",
    "settings.local.json",
}
DENIED_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
}
DENIED_DIRS = {
    ".git",
    "__pycache__",
    "cache",
    "logs",
    "log",
    "sessions",
    "session-env",
    "transcripts",
    "telemetry",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\b\s*[:=]\s*['\"]?[^'\"\s]{6,}"),
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+"),
    re.compile(r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9-]+"),
]


@dataclass(frozen=True)
class ScanIssue:
    path: str
    message: str


@dataclass(frozen=True)
class ScanResult:
    root: Path
    issues: list[ScanIssue]

    @property
    def ok(self) -> bool:
        return not self.issues


def _is_binary(sample: bytes) -> bool:
    return b"\x00" in sample


def _denied_path(path: Path, root: Path) -> str | None:
    rel_parts = path.relative_to(root).parts
    name = path.name
    if name in DENIED_EXACT_NAMES:
        return f"denied filename: {name}"
    if any(name.endswith(suffix) for suffix in DENIED_SUFFIXES):
        return f"denied file suffix: {name}"
    if name.endswith(".env"):
        return f"denied env filename: {name}"
    if any(part in DENIED_DIRS for part in rel_parts[:-1]):
        return "denied runtime/cache directory"
    return None


def scan_tree(root: Path) -> ScanResult:
    issues: list[ScanIssue] = []
    if not root.exists():
        return ScanResult(root=root, issues=issues)

    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in {".git", "__pycache__"} for part in path.relative_to(root).parts[:-1]):
            continue

        relative = str(path.relative_to(root))
        denied = _denied_path(path, root)
        if denied:
            issues.append(ScanIssue(path=relative, message=denied))
            continue

        size = path.stat().st_size
        if size > MAX_TEXT_FILE_BYTES:
            issues.append(ScanIssue(path=relative, message=f"file exceeds {MAX_TEXT_FILE_BYTES} byte safety limit"))
            continue

        data = path.read_bytes()
        if _is_binary(data[:4096]):
            issues.append(ScanIssue(path=relative, message="binary files are not allowed in memory backups"))
            continue

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            issues.append(ScanIssue(path=relative, message="non-utf8 files are not allowed in memory backups"))
            continue

        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if match:
                issues.append(ScanIssue(path=relative, message=f"possible secret content: {match.group(1) if match.groups() else 'webhook'}"))
                break

    return ScanResult(root=root, issues=issues)

