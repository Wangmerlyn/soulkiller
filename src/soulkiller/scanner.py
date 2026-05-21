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
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?P<key>api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\b\s*[:=]\s*(?P<value>[^\n#]+)"
)
WEBHOOK_PATTERNS = [
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


def _secret_assignment_issue(text: str) -> str | None:
    for match in SECRET_ASSIGNMENT.finditer(text):
        key = match.group("key")
        value = match.group("value").strip().strip("'\"`,")
        upper_value = value.upper()
        if "REDACTED" in upper_value:
            continue
        if "OS.ENVIRON" in upper_value or "GETENV" in upper_value:
            continue
        if upper_value.startswith("ENV_"):
            continue
        return key
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

        assignment_key = _secret_assignment_issue(text)
        if assignment_key:
            issues.append(ScanIssue(path=relative, message=f"possible secret content: {assignment_key}"))
            continue

        for pattern in WEBHOOK_PATTERNS:
            if pattern.search(text):
                issues.append(ScanIssue(path=relative, message="possible secret content: webhook"))
                break

    return ScanResult(root=root, issues=issues)
