#!/usr/bin/env python3
"""
Task Scope Sentinel - detects unauthorized file changes.

This utility compares current Git state against a task contract stored in
.agent_runtime/task_scope.json to ensure no unauthorized paths are modified.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def run_git_command(args):
    """Run a git command and return (stdout, stderr, returncode)."""
    result = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=Path.cwd())
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def get_git_status():
    """Get current git status including untracked files."""
    # Get tracked changes (modified, deleted, etc.)
    stdout, _, _ = run_git_command(["diff", "--name-status"])
    tracked_changes = []
    if stdout:
        for line in stdout.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                tracked_changes.append((parts[0], parts[1]))

    # Get untracked files
    stdout, _, _ = run_git_command(["ls-files", "--others", "--exclude-standard"])
    untracked = []
    if stdout:
        for line in stdout.splitlines():
            if line:
                untracked.append(("??", line))

    return tracked_changes + untracked


def load_task_contract():
    """Load the task scope contract from .agent_runtime/task_scope.json."""
    contract_path = Path(".agent_runtime/task_scope.json")
    if not contract_path.exists():
        return None
    with open(contract_path) as f:
        return json.load(f)


def save_task_contract(contract):
    """Save the task scope contract to .agent_runtime/task_scope.json."""
    contract_path = Path(".agent_runtime/task_scope.json")
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    with open(contract_path, "w") as f:
        json.dump(contract, f, indent=2)


def initialize_task_scope(task_id, authorized_paths):
    """Initialize a new task scope contract with current baseline."""
    baseline = get_git_status()
    baseline_paths = {path for _, path in baseline}

    contract = {
        "task_id": task_id,
        "authorized_paths": authorized_paths,
        "baseline_paths": sorted(baseline_paths)
    }
    save_task_contract(contract)
    return contract


def check_task_scope():
    """Check current git state against task contract."""
    contract = load_task_contract()
    if not contract:
        print("ERROR: No task scope contract found. Run 'python -m tools.task_scope_sentinel init <task_id> <authorized_paths...>' first.", file=sys.stderr)
        return 1, ["No task scope contract initialized"]

    current = get_git_status()
    current_paths = {path for _, path in current}
    baseline_paths = set(contract.get("baseline_paths", []))
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
        print(f"Initialized task scope for '{task_id}' with {len(authorized_paths)} authorized paths")
        print(f"Baseline recorded: {len(contract['baseline_paths'])} pre-existing paths")
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