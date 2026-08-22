#!/usr/bin/env python3
"""
Task Scope Sentinel - detects unauthorized file changes.

This utility compares current Git state against a task contract stored in
.agent_runtime/task_scope.json to ensure no unauthorized paths are modified.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def run_git_command(args):
    """Run a git command and return (stdout, stderr, returncode). Fails on non-zero exit."""
    result = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=Path.cwd())
    if result.returncode != 0:
        raise RuntimeError(f"Git command failed: git {' '.join(args)} (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def compute_file_hash(filepath):
    """Compute SHA256 hash of a file for fingerprint tracking."""
    try:
        with open(filepath, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, IOError):
        return None


def get_git_status():
    """Get current git status including staged, unstaged, and untracked files.

    Returns list of (status, path) tuples where status is:
    - 'M' = modified (staged or unstaged)
    - 'A' = added
    - 'D' = deleted
    - 'R' = renamed (handled as delete old + add new)
    - '??' = untracked
    """
    # First verify we're in a git repo
    run_git_command(["rev-parse", "--git-dir"])

    changes = []

    # Get both staged and unstaged tracked changes from HEAD
    # --no-renames treats renames as delete + add for path-based detection
    stdout, _, _ = run_git_command(["diff", "--name-only", "--no-renames", "HEAD"])
    if stdout:
        for line in stdout.splitlines():
            path = line.strip()
            if path:
                changes.append(("M", path))

    # Get untracked files (excluding .gitignored)
    stdout, _, _ = run_git_command(["ls-files", "--others", "--exclude-standard"])
    if stdout:
        for line in stdout.splitlines():
            path = line.strip()
            if path:
                changes.append(("??", path))

    return changes


def load_task_contract():
    """Load the task scope contract from .agent_runtime/task_scope.json."""
    contract_path = Path(".agent_runtime/task_scope.json")
    if not contract_path.exists():
        return None
    try:
        with open(contract_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_task_contract(contract):
    """Save the task scope contract to .agent_runtime/task_scope.json."""
    contract_path = Path(".agent_runtime/task_scope.json")
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    with open(contract_path, "w") as f:
        json.dump(contract, f, indent=2)


def initialize_task_scope(task_id, authorized_paths):
    """Initialize a new task scope contract with current baseline."""
    try:
        baseline = get_git_status()
    except RuntimeError as e:
        print(f"ERROR: Git command failed: {e}", file=sys.stderr)
        return None
    baseline_paths = {path for _, path in baseline}

    # Also record fingerprints for baseline files to detect mutations
    baseline_fingerprints = {}
    for _, path in baseline:
        if not path.startswith(".agent_runtime/"):
            filepath = Path(path)
            if filepath.exists() and filepath.is_file():
                fp = compute_file_hash(filepath)
                if fp:
                    baseline_fingerprints[path] = fp

    contract = {
        "task_id": task_id,
        "authorized_paths": authorized_paths,
        "baseline_paths": sorted(baseline_paths),
        "baseline_fingerprints": baseline_fingerprints
    }
    save_task_contract(contract)
    return contract


def check_task_scope():
    """Check current git state against task contract."""
    contract = load_task_contract()
    if not contract:
        print("ERROR: No task scope contract found. Run 'python -m tools.task_scope_sentinel init <task_id> <authorized_paths...>' first.", file=sys.stderr)
        return 1, ["No task scope contract initialized"]

    try:
        current = get_git_status()
    except RuntimeError as e:
        print(f"ERROR: Git command failed: {e}", file=sys.stderr)
        return 1, [f"Git command failure: {e}"]

    current_paths = {path for _, path in current}
    baseline_paths = set(contract.get("baseline_paths", []))
    baseline_fingerprints = contract.get("baseline_fingerprints", {})
    authorized = set(contract.get("authorized_paths", []))

    # Find new/changed paths since baseline
    changed = current_paths - baseline_paths

    # Filter out .agent_runtime/ files (allowed runtime evidence)
    changed = {p for p in changed if not p.startswith(".agent_runtime/")}

    # Check each changed path against authorized
    unauthorized = []
    for path in changed:
        # Check if path is authorized or under an authorized directory
        is_authorized = False
        for auth in authorized:
            if path == auth or path.startswith(auth.rstrip("/") + "/"):
                is_authorized = True
                break
        if not is_authorized:
            unauthorized.append(path)

    # Also check for mutations in baseline files (files that existed at baseline but now changed)
        # This catches modifications to baseline files that don't add new paths
        for baseline_path, baseline_fp in baseline_fingerprints.items():
            if baseline_path.startswith(".agent_runtime/"):
                continue
            if baseline_path in current_paths:
                # File still exists in current - check if fingerprint changed
                current_fp = compute_file_hash(Path(baseline_path))
                if current_fp and current_fp != baseline_fp:
                    # File mutated - check if authorized
                    is_authorized = False
                    for auth in authorized:
                        if baseline_path == auth or baseline_path.startswith(auth.rstrip("/") + "/"):
                            is_authorized = True
                            break
                    if not is_authorized:
                        unauthorized.append(f"{baseline_path} (mutated)")
            else:
                # File existed at baseline but is now missing (deleted) - check if authorized
                is_authorized = False
                for auth in authorized:
                    if baseline_path == auth or baseline_path.startswith(auth.rstrip("/") + "/"):
                        is_authorized = True
                        break
                if not is_authorized:
                    unauthorized.append(f"{baseline_path} (deleted)")

    if unauthorized:
        print("TASK SCOPE VIOLATION: Unauthorized paths detected:", file=sys.stderr)
        for path in sorted(unauthorized):
            print(f"  {path}", file=sys.stderr)
        return 1, unauthorized

    return 0, []


def main():
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  python -m tools.task_scope_sentinel init <task_id> <authorized_path>...", file=sys.stderr)
        print("  python -m tools.task_scope_sentinel check", file=sys.stderr)
        return 1

    if sys.argv[1] == "init":
        if len(sys.argv) < 4:
            print("ERROR: init requires task_id and at least one authorized_path", file=sys.stderr)
            return 1
        task_id = sys.argv[2]
        authorized_paths = sys.argv[3:]
        contract = initialize_task_scope(task_id, authorized_paths)
        if contract is None:
            return 1
        print(f"Initialized task scope for '{task_id}' with {len(authorized_paths)} authorized paths")
        print(f"Baseline recorded: {len(contract['baseline_paths'])} pre-existing paths")
        print(f"Fingerprints recorded: {len(contract.get('baseline_fingerprints', {}))} files")
        return 0

    elif sys.argv[1] == "check":
        exit_code, violations = check_task_scope()
        if exit_code == 0:
            print("TASK SCOPE: PASS - All changes within authorized paths")
        return exit_code

    else:
        print(f"ERROR: Unknown command '{sys.argv[1]}'", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())