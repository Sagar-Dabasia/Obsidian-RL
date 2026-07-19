"""Secret hygiene: no credentials or runtime artifacts may be tracked by git."""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FORBIDDEN_TRACKED = re.compile(
    r"(^|/)\.env$|\.pkl$|\.joblib$|\.pyc$|\.log$|\.sqlite3?$|\.db$|\.pt$|\.pth$"
)
# Binance-style API keys are 64-char base62 strings; flag any long secret-like literal
# assigned to a credential-named variable in tracked text files.
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|api[_-]?secret|password|token)\s*[=:]\s*['\"][A-Za-z0-9]{32,}['\"]"
)


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def test_no_forbidden_files_tracked() -> None:
    bad = [f for f in tracked_files() if FORBIDDEN_TRACKED.search(f)]
    assert not bad, f"forbidden files tracked by git: {bad}"


def test_env_is_ignored() -> None:
    res = subprocess.run(["git", "check-ignore", ".env"], cwd=REPO, capture_output=True, text=True)
    assert res.returncode == 0, ".env must be matched by .gitignore"


def test_env_example_has_blank_values_only() -> None:
    for line in (REPO / ".env.example").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        assert value.strip() == "", f".env.example must keep {key} blank"


def test_no_hardcoded_secrets_in_tracked_sources() -> None:
    hits: list[str] = []
    for f in tracked_files():
        p = REPO / f
        if p.suffix not in {".py", ".toml", ".md", ".yml", ".yaml", ".cfg", ".ini", ".json"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SECRET_ASSIGNMENT.search(text):
            hits.append(f)
    assert not hits, f"possible hardcoded secrets in: {hits}"
