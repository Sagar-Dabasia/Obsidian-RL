"""Repository foundation invariants."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_gitignore_is_utf8_and_covers_essentials() -> None:
    text = (REPO / ".gitignore").read_text(encoding="utf-8")  # raises on UTF-16 relapse
    for pattern in (".env", "__pycache__/", "*.pkl", "data/", ".venv/"):
        assert pattern in text, f".gitignore missing {pattern}"


def test_package_importable() -> None:
    import obsidian_rl

    assert obsidian_rl.__version__


def test_legacy_not_imported_by_new_code() -> None:
    src = REPO / "src" / "obsidian_rl"
    offenders = [
        p
        for p in src.rglob("*.py")
        if "import legacy" in p.read_text(encoding="utf-8")
        or "from legacy" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"new code must not import legacy modules: {offenders}"
