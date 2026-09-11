#!/usr/bin/env python3
"""
Obsidian-RL Patch Acceptance Gate

Mechanical pre-merge validation that rejects unsafe/unexpected diffs.
Extends the existing task_scope_sentinel with additional checks.

Output: PASS / FAIL / REVIEW_REQUIRED with exact reasons.
FAIL CLOSED on malformed/missing scope, checker crash, ambiguous base.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

# Reuse task_scope_sentinel internals
from tools.task_scope_sentinel import (
    run_git_command,
    load_task_contract,
    get_git_status,
    compute_file_hash,
)


def get_git_diff_stats(cwd: Path = None) -> Tuple[int, int, List[str]]:
    """Get diff stats: files changed, lines added, lines removed, file list."""
    if cwd is None:
        cwd = Path.cwd()
    stdout, _, _ = run_git_command(["diff", "--stat", "HEAD"], cwd=cwd)
    files_changed = 0
    insertions = 0
    deletions = 0
    file_list = []

    for line in stdout.splitlines():
        if " files changed" in line:
            parts = line.split(",")
            for p in parts:
                p = p.strip()
                if "file" in p:
                    files_changed = int(p.split()[0])
                elif "insertion" in p:
                    insertions = int(p.split()[0])
                elif "deletion" in p:
                    deletions = int(p.split()[0])
        elif "|" in line:
            file_list.append(line.split("|")[0].strip())

    return files_changed, insertions + deletions, file_list


def get_git_diff_files(cwd: Path = None) -> List[str]:
    """Get list of files changed in HEAD (both staged and unstaged)."""
    if cwd is None:
        cwd = Path.cwd()
    # Get staged changes
    stdout, _, _ = run_git_command(["diff", "--name-only", "--staged"], cwd=cwd)
    staged_files = [line.strip() for line in stdout.splitlines() if line.strip()]
    
    # Get unstaged changes
    stdout, _, _ = run_git_command(["diff", "--name-only", "HEAD"], cwd=cwd)
    unstaged_files = [line.strip() for line in stdout.splitlines() if line.strip()]
    
    # Combine and deduplicate
    all_files = list(set(staged_files + unstaged_files))
    return all_files


def check_test_weakening(contract: Dict, cwd: Path = None) -> Tuple[str, List[str]]:
    """Check for test modifications that may indicate weakening.
    Returns (status, reasons) where status is PASS/FAIL/REVIEW_REQUIRED.
    """
    if cwd is None:
        cwd = Path.cwd()
    reasons = []
    test_files = []
    authorized = set(contract.get("authorized_paths", []))

    # Get test files from diff
    diff_files = get_git_diff_files(cwd=cwd)
    for f in diff_files:
        if f.startswith("tests/") and f.endswith(".py"):
            test_files.append(f)

    if not test_files:
        return "PASS", []

    # Check if test files are authorized
    unauthorized_tests = []
    for tf in test_files:
        is_authorized = False
        for auth in authorized:
            if tf == auth or tf.startswith(auth.rstrip("/") + "/"):
                is_authorized = True
                break
        if not is_authorized:
            unauthorized_tests.append(tf)

    if unauthorized_tests:
        return "FAIL", [f"Unauthorized test file modifications: {unauthorized_tests}"]

    # Authorized test files modified - check for weakening signals
    # This is a mechanical check; cannot prove semantic strength
    for tf in test_files:
        try:
            # Get staged diff for this test file
            stdout_staged, _, _ = run_git_command(["diff", "--staged", "HEAD", "--", tf], cwd=cwd)
            # Get unstaged diff for this test file
            stdout_unstaged, _, _ = run_git_command(["diff", "HEAD", "--", tf], cwd=cwd)
            combined_stdout = stdout_staged + "\n" + stdout_unstaged
            if not combined_stdout.strip():
                continue

            # Heuristic checks for potential weakening
            lines = combined_stdout.splitlines()
            removed_assertions = 0
            added_assertions = 0
            removed_test_funcs = 0
            added_test_funcs = 0

            for line in lines:
                if line.startswith("-") and not line.startswith("---"):
                    stripped = line[1:].strip()
                    # Only count actual assertion statements, not comments containing "assert"
                    if stripped.startswith("assert ") or stripped.startswith("assert("):
                        removed_assertions += 1
                    if stripped.startswith("def test_"):
                        removed_test_funcs += 1
                elif line.startswith("+") and not line.startswith("+++"):
                    stripped = line[1:].strip()
                    # Only count actual assertion statements, not comments containing "assert"
                    if stripped.startswith("assert ") or stripped.startswith("assert("):
                        added_assertions += 1
                    if stripped.startswith("def test_"):
                        added_test_funcs += 1

            if removed_test_funcs > 0:
                reasons.append(f"{tf}: {removed_test_funcs} test function(s) removed")
            if removed_assertions > added_assertions and removed_assertions > 0:
                reasons.append(f"{tf}: net {removed_assertions - added_assertions} assertion(s) removed")

        except RuntimeError as e:
            # Git command failure - FAIL CLOSED
            return "FAIL", [f"check_test_weakening: git diff failed for {tf}: {e}"]
        except Exception as e:
            # Any internal failure - FAIL CLOSED
            return "FAIL", [f"check_test_weakening: checker crash on {tf}: {e}"]

    if reasons:
        return "REVIEW_REQUIRED", [f"Test modifications detected (cannot mechanically verify strength): {reasons}"]

    return "PASS", []


def check_dependency_changes(cwd: Path = None) -> Tuple[str, List[str]]:
    """Check for dependency/lock/config changes."""
    if cwd is None:
        cwd = Path.cwd()
    reasons = []
    diff_files = get_git_diff_files(cwd=cwd)

    sensitive_patterns = [
        "pyproject.toml",
        "uv.lock",
        "requirements.txt",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "setup.py",
        "setup.cfg",
        ".github/workflows/",
        ".gitlab-ci.yml",
        "Dockerfile",
        "docker-compose.yml",
    ]

    for f in diff_files:
        for pattern in sensitive_patterns:
            if f == pattern or f.startswith(pattern.rstrip("/") + "/"):
                reasons.append(f"Dependency/config file changed: {f}")
                break

    if reasons:
        return "REVIEW_REQUIRED", reasons

    return "PASS", []


def check_archived_imports(cwd: Path = None) -> Tuple[str, List[str]]:
    """Check if archived/quarantined code is newly imported into active source.

    Scans active Python files (src/, tests/, tools/) for NEW imports from
    quarantined legacy/ or archive/ directories. Existence of archived code
    alone is not a violation — only active imports from it are.
    """
    if cwd is None:
        cwd = Path.cwd()
    reasons = []
    diff_files = get_git_diff_files(cwd=cwd)

    # Patterns that indicate importing from legacy/archive
    # Matches: from legacy.xxx import ..., import legacy.xxx, from archive.xxx import ...
    legacy_import_pattern = re.compile(r'^\s*(?:from|import)\s+(legacy|archive)\.')

    for f in diff_files:
        # Only check active Python source files, not the archived files themselves
        if not (f.startswith("src/") or f.startswith("tests/") or f.startswith("tools/")):
            continue
        if not f.endswith(".py"):
            continue

        try:
            # Get the diff for this file (staged + unstaged)
            stdout_staged, _, _ = run_git_command(["diff", "--staged", "HEAD", "--", f], cwd=cwd)
            stdout_unstaged, _, _ = run_git_command(["diff", "HEAD", "--", f], cwd=cwd)
            combined_stdout = stdout_staged + "\n" + stdout_unstaged

            # Check only ADDED lines for new imports from legacy/archive
            for line in combined_stdout.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    stripped = line[1:].strip()
                    if legacy_import_pattern.search(stripped):
                        reasons.append(f"Active code imports quarantined legacy/archive in {f}: {stripped[:120]}")
        except RuntimeError as e:
            # Git diff failure - FAIL CLOSED
            return "FAIL", [f"check_archived_imports: git diff failed for {f}: {e}"]
        except Exception as e:
            # Any other internal failure - FAIL CLOSED
            return "FAIL", [f"check_archived_imports: checker crash on {f}: {e}"]

    if reasons:
        return "FAIL", reasons

    return "PASS", []


def check_diff_size(contract: Dict, cwd: Path = None) -> Tuple[str, List[str]]:
    """Check if diff size exceeds reasonable task budget."""
    if cwd is None:
        cwd = Path.cwd()
    reasons = []
    files_changed, total_lines, file_list = get_git_diff_stats(cwd=cwd)

    # Heuristic: >20 files or >1000 lines is oversized for a "one bounded defect"
    if files_changed > 20:
        reasons.append(f"Oversized diff: {files_changed} files changed (budget: ≤20)")
    if total_lines > 1000:
        reasons.append(f"Oversized diff: {total_lines} lines changed (budget: ≤1000)")

    if reasons:
        return "REVIEW_REQUIRED", reasons

    return "PASS", []


def check_deleted_tracked_files(contract: Dict, cwd: Path = None) -> Tuple[str, List[str]]:
    """Check for deleted tracked files not in authorized paths."""
    if cwd is None:
        cwd = Path.cwd()
    reasons = []
    diff_files = get_git_diff_files(cwd=cwd)
    authorized = set(contract.get("authorized_paths", []))

    for f in diff_files:
        # Check if file was deleted (not in current working tree but was in HEAD)
        if not (cwd / f).exists():
            is_authorized = False
            for auth in authorized:
                if f == auth or f.startswith(auth.rstrip("/") + "/"):
                    is_authorized = True
                    break
            if not is_authorized:
                reasons.append(f"Deleted tracked file not authorized: {f}")
            elif f.startswith("tests/") and f.endswith(".py"):
                # Deleted test file even if authorized requires review
                reasons.append(f"Deleted test file (authorized but requires review): {f}")

    if reasons:
        # Check if any are unauthorized (FAIL) vs authorized test deletions (REVIEW_REQUIRED)
        unauthorized = [r for r in reasons if "not authorized" in r]
        if unauthorized:
            return "FAIL", reasons
        return "REVIEW_REQUIRED", reasons

    return "PASS", []


def check_git_diff_check(cwd: Path = None) -> Tuple[str, List[str]]:
    """Run git diff --check."""
    if cwd is None:
        cwd = Path.cwd()
    try:
        run_git_command(["diff", "--check", "HEAD"], cwd=cwd)
        return "PASS", []
    except RuntimeError as e:
        return "FAIL", [f"git diff --check failed: {e}"]


def run_patch_gate(cwd: Path = None) -> Tuple[int, Dict]:
    """
    Run the complete patch gate.
    Returns (exit_code, result_dict) where exit_code: 0=PASS, 1=FAIL, 2=REVIEW_REQUIRED
    """
    if cwd is None:
        cwd = Path.cwd()
    # Load task contract
    contract = load_task_contract(cwd=cwd)
    if not contract:
        return 1, {
            "status": "FAIL",
            "reasons": ["No task scope contract found (.agent_runtime/task_scope.json)"],
            "task_id": "unknown",
            "checks": {}
        }

    # Run all checks
    all_checks = {}
    overall_status = "PASS"

    # 1. Task scope (reuse existing)
    try:
        from tools.task_scope_sentinel import check_task_scope
        scope_exit, scope_violations = check_task_scope(cwd=cwd)
        
        # Filter out common cache/build artifacts that shouldn't be considered violations
        filtered_violations = []
        for v in scope_violations:
            if any(v.startswith(ignore) for ignore in [
                "__pycache__/", ".pyc", ".pytest_cache/", ".mypy_cache/", 
                ".ruff_cache/", ".coverage", "htmlcov/", ".venv/", "venv/",
                "build/", "dist/", "*.egg-info/", ".tox/", ".nox/"
            ]):
                continue
            filtered_violations.append(v)
        
        all_checks["task_scope"] = {
            "status": "PASS" if scope_exit == 0 and not filtered_violations else "FAIL",
            "reasons": filtered_violations if filtered_violations else (scope_violations if scope_exit != 0 else [])
        }
        if scope_exit != 0 or filtered_violations:
            overall_status = "FAIL"
    except Exception as e:
        all_checks["task_scope"] = {"status": "FAIL", "reasons": [f"Checker crash: {e}"]}
        overall_status = "FAIL"

    # 2. Test weakening
    test_status, test_reasons = check_test_weakening(contract, cwd=cwd)
    all_checks["test_weakening"] = {"status": test_status, "reasons": test_reasons}
    if test_status == "FAIL":
        overall_status = "FAIL"
    elif test_status == "REVIEW_REQUIRED" and overall_status == "PASS":
        overall_status = "REVIEW_REQUIRED"

    # 3. Dependency changes
    dep_status, dep_reasons = check_dependency_changes(cwd=cwd)
    all_checks["dependencies"] = {"status": dep_status, "reasons": dep_reasons}
    if dep_status == "FAIL":
        overall_status = "FAIL"
    elif dep_status == "REVIEW_REQUIRED" and overall_status == "PASS":
        overall_status = "REVIEW_REQUIRED"

    # 4. Archived imports
    arch_status, arch_reasons = check_archived_imports(cwd=cwd)
    all_checks["archived_imports"] = {"status": arch_status, "reasons": arch_reasons}
    if arch_status == "FAIL":
        overall_status = "FAIL"
    elif arch_status == "REVIEW_REQUIRED" and overall_status == "PASS":
        overall_status = "REVIEW_REQUIRED"

    # 5. Diff size
    size_status, size_reasons = check_diff_size(contract, cwd=cwd)
    all_checks["diff_size"] = {"status": size_status, "reasons": size_reasons}
    if size_status == "FAIL":
        overall_status = "FAIL"
    elif size_status == "REVIEW_REQUIRED" and overall_status == "PASS":
        overall_status = "REVIEW_REQUIRED"

    # 6. Deleted tracked files
    del_status, del_reasons = check_deleted_tracked_files(contract, cwd=cwd)
    all_checks["deleted_files"] = {"status": del_status, "reasons": del_reasons}
    if del_status == "FAIL":
        overall_status = "FAIL"
    elif del_status == "REVIEW_REQUIRED" and overall_status == "PASS":
        overall_status = "REVIEW_REQUIRED"

    # 7. git diff --check
    check_status, check_reasons = check_git_diff_check(cwd=cwd)
    all_checks["git_diff_check"] = {"status": check_status, "reasons": check_reasons}
    if check_status == "FAIL":
        overall_status = "FAIL"

    # Prepare result
    result = {
        "status": overall_status,
        "task_id": contract.get("task_id", "unknown"),
        "checks": all_checks
    }

    # Exit codes: 0=PASS, 1=FAIL, 2=REVIEW_REQUIRED
    exit_map = {"PASS": 0, "FAIL": 1, "REVIEW_REQUIRED": 2}
    return exit_map.get(overall_status, 1), result


def main():
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  python -m tools.patch_gate check", file=sys.stderr)
        print("  python -m tools.patch_gate check --json", file=sys.stderr)
        return 1

    if sys.argv[1] == "check":
        cwd = Path.cwd()
        exit_code, result = run_patch_gate(cwd=cwd)

        if "--json" in sys.argv:
            print(json.dumps(result, indent=2))
        else:
            print(f"PATCH GATE: {result['status']}")
            print(f"Task: {result['task_id']}")
            if result.get("reasons"):
                for reason in result["reasons"]:
                    print(f"  {reason}")
            for check_name, check_result in result["checks"].items():
                status = check_result["status"]
                print(f"  {check_name}: {status}")
                for reason in check_result["reasons"]:
                    print(f"    - {reason}")

        return exit_code

    else:
        print(f"ERROR: Unknown command '{sys.argv[1]}'", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())