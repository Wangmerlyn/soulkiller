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
    r"(?i)(?P<key>[A-Z0-9_]*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)[A-Z0-9_]*)[ \t]*[:=][ \t]*(?P<value>[^\n#]+)"
)
WEBHOOK_PATTERNS = [
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+"),
    re.compile(r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9-]+"),
]
ENV_NAME_VALUE = re.compile(r"^[A-Z][A-Z0-9_]*$")
ENV_NAME_CONSTANT_KEY = re.compile(
    r"^ENV_(?P<suffix>[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|REFRESH_TOKEN|SECRET|PASSWORD)[A-Z0-9_]*)$"
)
GENERIC_ENV_NAME_PREFIX_PARTS = {
    "ACCESS",
    "ADMIN",
    "DEFAULT",
    "KEY",
    "PASSWORD",
    "PROD",
    "PRODUCTION",
    "REAL",
    "REFRESH",
    "ROOT",
    "SECRET",
    "TOKEN",
}
CHINESE_PLACEHOLDER_MARKERS = ("你的", "您的", "你自己的", "您自己的")
CHINESE_SECRET_WORDS = ("令牌", "密钥", "密码")


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


def _is_placeholder_secret_value(value: str, upper_value: str) -> bool:
    if "..." in value:
        return True
    if "REDACTED" in upper_value:
        return True
    if any(marker in value for marker in CHINESE_PLACEHOLDER_MARKERS):
        return any(secret_word in value for secret_word in CHINESE_SECRET_WORDS)
    return False


def _uses_env_name_constant(text: str, key: str) -> bool:
    escaped_key = re.escape(key)
    return any(
        re.search(pattern, text)
        for pattern in (
            rf"\bos\.environ\.get\(\s*{escaped_key}\b",
            rf"\bos\.environ\[\s*{escaped_key}\s*\]",
            rf"\bos\.getenv\(\s*{escaped_key}\b",
            rf"\bgetenv\(\s*{escaped_key}\b",
        )
    )


def _is_env_name_constant_assignment(key: str, value: str, text: str) -> bool:
    key_match = ENV_NAME_CONSTANT_KEY.fullmatch(key)
    if not key_match or not ENV_NAME_VALUE.fullmatch(value):
        return False

    suffix = key_match.group("suffix")
    if "_" not in suffix or not value.endswith(f"_{suffix}"):
        return False

    prefix = value[: -(len(suffix) + 1)]
    if not prefix:
        return False
    if any(part in GENERIC_ENV_NAME_PREFIX_PARTS for part in prefix.split("_")):
        return False

    return _uses_env_name_constant(text, key)


def _denied_path(path: Path, root: Path) -> str | None:
    rel_parts = path.relative_to(root).parts
    name = path.name
    if name in DENIED_EXACT_NAMES:
        return f"denied filename: {name}"
    if name == ".env" or name.startswith(".env."):
        return f"denied env filename: {name}"
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
        if _is_placeholder_secret_value(value, upper_value):
            continue
        if "OS.ENVIRON" in upper_value or "GETENV" in upper_value:
            continue
        if _is_env_name_constant_assignment(key, value, text):
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
