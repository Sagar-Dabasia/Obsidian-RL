"""
Governance contract tests for the Obsidian-RL 15-role engineering office.

These tests validate repository-owned governance contracts only.
They do NOT test global/local Hermes config from pytest.
"""

import json
import re
import sys
from pathlib import Path
import yaml


def load_skill_yaml(skill_path: Path) -> dict:
    """Load and parse a skill's YAML frontmatter."""
    content = skill_path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return yaml.safe_load(parts[1])
    return {}


def load_markdown_sections(md_path: Path) -> dict:
    """Extract key sections from governance markdown files."""
    content = md_path.read_text()
    return {"content": content}


class TestAgentOfficeGovernance:
    """Validate the 15-role agent office governance contracts."""

    def test_exactly_15_logical_roles_represented(self):
        """Exactly 15 logical roles must be defined in governance docs."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        assert roles_path.exists(), "AGENT_OFFICE_ROLES.md must exist"

        content = roles_path.read_text()

        # Count role definitions by looking for ### ROLE patterns
        tier3_roles = [
            "LEAD / WRITER",
            "ARCHITECTURE REVIEWER",
            "ENVIRONMENT / REPRODUCIBILITY REVIEWER",
            "FINANCIAL / ACCOUNTING REVIEWER",
            "ADVERSARIAL / RED-TEAM TESTER",
            "DATA / LEAKAGE REVIEWER",
            "SAFETY / EVIDENCE REVIEWER",
            "COORDINATION / TEST-LEDGER AGENT",
            "RELEASE GATEKEEPER",
        ]

        tier2_managers = [
            "ENGINEERING MANAGER",
            "FINANCIAL INTEGRITY MANAGER",
            "RESEARCH/DATA MANAGER",
            "VERIFICATION/RELEASE MANAGER",
        ]

        tier1_roles = [
            "CHIEF ORCHESTRATOR",
            "PLANNING / WORKFLOW MANAGER",
        ]

        all_roles = tier1_roles + tier2_managers + tier3_roles

        for role in all_roles:
            assert role in content, f"Role '{role}' not found in AGENT_OFFICE_ROLES.md"

        # Verify exactly 15
        assert len(all_roles) == 15, f"Expected 15 roles, found {len(all_roles)}"

    def test_lead_writer_is_sole_writer(self):
        """Lead/Writer must be the ONLY role with write_permission: ALLOWED."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        content = roles_path.read_text()

        # Count write_permission: ALLOWED occurrences
        # Only Lead/Writer should have ALLOWED, others FORBIDDEN or CONDITIONAL
        write_permissions = re.findall(r'write_permission:\s*(\w+)', content)
        allowed_count = write_permissions.count("ALLOWED")
        conditional_count = write_permissions.count("CONDITIONAL")

        assert allowed_count == 1, f"Expected exactly 1 ALLOWED write_permission, found {allowed_count}"
        assert conditional_count == 1, f"Expected exactly 1 CONDITIONAL (ledger agent), found {conditional_count}"

        # Verify it's Lead/Writer
        lead_section = content[content.find("LEAD / WRITER"):content.find("### ", content.find("LEAD / WRITER") + 1)]
        assert "write_permission: ALLOWED" in lead_section

    def test_reviewers_managers_read_only(self):
        """All reviewers and managers must have write_permission: FORBIDDEN (or CONDITIONAL for ledger)."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        content = roles_path.read_text()

        # All roles except Lead/Writer and Coordination agent must be FORBIDDEN
        forbidden_roles = [
            "CHIEF ORCHESTRATOR",
            "PLANNING / WORKFLOW MANAGER",
            "ENGINEERING MANAGER",
            "FINANCIAL INTEGRITY MANAGER",
            "RESEARCH/DATA MANAGER",
            "VERIFICATION/RELEASE MANAGER",
            "ARCHITECTURE REVIEWER",
            "ENVIRONMENT / REPRODUCIBILITY REVIEWER",
            "FINANCIAL / ACCOUNTING REVIEWER",
            "ADVERSARIAL / RED-TEAM TESTER",
            "DATA / LEAKAGE REVIEWER",
            "SAFETY / EVIDENCE REVIEWER",
            "RELEASE GATEKEEPER",
        ]

        for role in forbidden_roles:
            section_start = content.find(role)
            assert section_start != -1, f"Role {role} not found"
            section_end = content.find("### ", section_start + 1)
            if section_end == -1:
                section_end = len(content)
            section = content[section_start:section_end]
            assert "write_permission: FORBIDDEN" in section, f"Role {role} must have write_permission: FORBIDDEN"

    def test_user_exclusive_commit_push_authorization(self):
        """Commit/push must require explicit user authorization (not in any role's allowed_commands)."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        content = roles_path.read_text()

        # No role should have git commit or git push in allowed_commands
        forbidden_commands = ["git commit", "git push", "git add .", "git add -A", "git reset --hard", "git push --force"]

        for cmd in forbidden_commands:
            # Check that no role's allowed_commands contains these
            # They should only appear in forbidden_commands sections
            allowed_section_pattern = r'allowed_commands:.*?(?=\n\w+:|\nforbidden_commands:|\n```)'
            allowed_sections = re.findall(allowed_section_pattern, content, re.DOTALL)
            for section in allowed_sections:
                assert cmd not in section, f"Forbidden command '{cmd}' found in allowed_commands"

        # Verify escalation path for Chief ends at USER
        chief_section = content[content.find("CHIEF ORCHESTRATOR"):content.find("### ", content.find("CHIEF ORCHESTRATOR") + 1)]
        assert "escalation_path: USER" in chief_section or "USER (sole commit/push authority)" in chief_section

    def test_max_concurrency_contract(self):
        """Max concurrency contract must be 3."""
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        content = workflow_path.read_text()

        assert "Max 3 specialist/reviewer children concurrently" in content or "max_concurrent_children: 3" in content

        # Also verify in skill
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        skill_content = skill_path.read_text()
        assert "max_concurrent_children 3" in skill_content or "maximum 3 simultaneous children" in skill_content.lower()

    def test_physical_delegation_depth_contract(self):
        """Physical delegation depth contract must be 1 (flat delegation only)."""
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        content = workflow_path.read_text()

        assert "Spawn depth 1" in content or "max_spawn_depth: 1" in content or "flat delegation only" in content.lower()

        # Verify in skill
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        skill_content = skill_path.read_text()
        assert "max_spawn_depth 1" in skill_content or "flat delegation only" in skill_content.lower()

    def test_release_gatekeeper_required(self):
        """Release Gatekeeper role must exist and be required."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        content = roles_path.read_text()

        assert "RELEASE GATEKEEPER" in content

        # The "independent read-only veto, final internal gate" is in MULTI_AGENT_WORKFLOW.md
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        workflow_content = workflow_path.read_text()
        assert "independent read-only veto" in workflow_content
        assert "final internal gate" in workflow_content

        assert "RELEASE GATEKEEPER" in workflow_content
        assert "RELEASE GATE" in workflow_content

    def test_runtime_ledger_path(self):
        """Runtime ledger path must be .agent_runtime/ledger.jsonl."""
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        content = workflow_path.read_text()

        assert ".agent_runtime/ledger.jsonl" in content

        gitignore_path = Path(".gitignore")
        gitignore_content = gitignore_path.read_text()
        assert ".agent_runtime/" in gitignore_content

    def test_duplicate_current_evidence_rerun_forbidden(self):
        """Anti-loop rule: duplicate current evidence must not rerun without invalidation/reason."""
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        content = workflow_path.read_text()

        assert "ANTI-LOOP RULE" in content or "duplicate" in content.lower()
        assert "identical check MUST NOT rerun" in content or "identical check must not rerun" in content.lower()

    def test_bounded_retry_escalation_rule_exists(self):
        """Bounded retry/escalation rule must exist."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        content = roles_path.read_text()

        assert "Retry >2 escalates" in content or "retry" in content.lower()
        assert "escalation" in content.lower()
        assert "escalation_path" in content

    def test_project_skill_exists_and_references_governance_docs(self):
        """Project skill must exist and reference governance docs."""
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        assert skill_path.exists(), "Project skill .hermes/skills/obsidian-rl-office/SKILL.md must exist"

        skill_content = skill_path.read_text()

        # Must reference the three governance docs
        assert "AGENTS.md" in skill_content
        assert "MULTI_AGENT_WORKFLOW.md" in skill_content
        assert "AGENT_OFFICE_ROLES.md" in skill_content

        # Must not duplicate them
        assert "Do not duplicate" in skill_content or "do not duplicate" in skill_content.lower()

    def test_no_live_testnet_private_order_authorization(self):
        """No role must authorize live/Testnet/private orders."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        content = roles_path.read_text()

        # Check forbidden_commands sections contain these
        assert "live/Testnet/private orders" in content or "Live/Testnet/private orders" in content
        assert "live" in content.lower() and "testnet" in content.lower()

        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        workflow_content = workflow_path.read_text()
        assert "live/Testnet/private orders" in workflow_content or "no live" in workflow_content.lower()

    def test_skill_frontmatter_valid(self):
        """Skill frontmatter must be valid YAML with required fields."""
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        content = skill_path.read_text()

        assert content.startswith("---"), "Skill must start with YAML frontmatter"

        frontmatter_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
        assert frontmatter_match, "Invalid frontmatter format"

        frontmatter = yaml.safe_load(frontmatter_match.group(1))
        assert frontmatter.get("name") == "obsidian-rl-office"
        assert "description" in frontmatter
        assert frontmatter.get("category") == "software-development"
        assert "version" in frontmatter


    def test_blocked_never_silently_normalized_to_pass(self):
        """BLOCKED child verdict must never be silently converted to PASS in Chief summary."""
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        skill_content = skill_path.read_text()

        # Skill must contain verdict integrity rules
        assert "BLOCKED never becomes PASS automatically" in skill_content
        assert "Child verdicts preserved exactly" in skill_content


    def test_unresolved_blocked_prevents_ready(self):
        """Unresolved BLOCKED must prevent READY_FOR_USER_REVIEW verdict."""
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        workflow_content = workflow_path.read_text()

        # Release Gatekeeper must refuse READY while unresolved BLOCKED exists
        assert "Release Gatekeeper refuses READY while any unresolved BLOCKED exists" in workflow_content
        assert "must veto" in workflow_content.lower() or "Must veto" in workflow_content


    def test_out_of_scope_requires_explicit_classification(self):
        """OUT_OF_SCOPE findings must be explicitly classified, not implicitly treated as PASS."""
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        skill_content = skill_path.read_text()

        assert "OUT_OF_SCOPE" in skill_content
        assert "Out-of-scope findings recorded as OUT_OF_SCOPE, not PASS" in skill_content


    def test_manager_resolution_requires_evidence(self):
        """Domain Manager resolution must require documented evidence."""
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        skill_content = skill_path.read_text()

        # Domain Manager must return RESOLVED_WITH_EVIDENCE or BLOCKER_CONFIRMED
        assert "RESOLVED_WITH_EVIDENCE" in skill_content
        assert "BLOCKER_CONFIRMED" in skill_content
        assert "Specialist BLOCKED routes to Domain Manager" in skill_content


    def test_release_gatekeeper_rejects_contradictory_verdict_state(self):
        """Release Gatekeeper must reject contradictory verdict state (e.g., Chief says PASS but ledger shows BLOCKED)."""
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        skill_content = skill_path.read_text()

        assert "Contradictory summary fields fail closed" in skill_content
        assert "verification fails" in skill_content.lower() or "verification fails" in skill_content.lower()

        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        workflow_content = workflow_path.read_text()
        assert "zero contradictory findings" in workflow_content


    def test_task_scope_sentinel_exists(self):
        """Task scope sentinel tool must exist in tools/."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        assert sentinel_path.exists(), "tools/task_scope_sentinel.py must exist"

        content = sentinel_path.read_text()
        assert "task_scope_sentinel" in content
        assert "init" in content
        assert "check" in content
        assert ".agent_runtime/task_scope.json" in content


    def test_release_gatekeeper_requires_sentinel_check(self):
        """Release Gatekeeper allowed_commands must include task_scope_sentinel check."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        content = roles_path.read_text()

        release_section = content[content.find("RELEASE GATEKEEPER"):content.find("### ", content.find("RELEASE GATEKEEPER") + 1)]
        assert "python -m tools.task_scope_sentinel check" in release_section


    def test_skill_includes_sentinel_workflow_steps(self):
        """Skill must include SCOPE and SCOPE CHECK workflow steps."""
        skill_path = Path(".hermes/skills/obsidian-rl-office/SKILL.md")
        skill_content = skill_path.read_text()

        assert "SCOPE" in skill_content
        assert "SCOPE CHECK" in skill_content
        assert "task scope sentinel" in skill_content.lower()
        assert "requires sentinel PASS" in skill_content


    def test_sentinel_reports_exact_offending_paths(self):
        """Sentinel must report exact unauthorized paths on violation."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        # Check for exact path reporting
        assert "unauthorized" in content.lower()
        assert "print" in content or "sys.stderr" in content


    def test_sentinel_never_repairs_or_deletes(self):
        """Sentinel must never repair, delete, or restore files."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        # Check no dangerous operations
        assert "os.remove" not in content
        assert "shutil.rmtree" not in content
        assert "git checkout" not in content
        assert "git restore" not in content
        assert "git reset" not in content
        assert "unlink" not in content
        # Should only read and report


    def test_sentinel_baseline_ignores_preexisting_artifacts(self):
        """Pre-existing baseline artifacts should not cause false failures."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        # Should track baseline and only flag new changes
        assert "baseline" in content.lower()
        assert "baseline_paths" in content


    def test_sentinel_detects_staged_and_unstaged_changes(self):
        """Sentinel must detect both staged and unstaged tracked changes."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        # Uses git diff --name-only --no-renames HEAD to catch both
        assert "diff" in content
        assert "--name-only" in content
        assert "--no-renames" in content
        assert "HEAD" in content


    def test_sentinel_detects_renames_as_delete_add(self):
        """Sentinel must detect renames (treated as delete old + add new via --no-renames)."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        # --no-renames makes git treat renames as delete+add
        assert "--no-renames" in content


    def test_sentinel_git_failure_fails_closed(self):
        """Any Git command failure must cause sentinel to FAIL, never empty-success."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        # Checks return codes and raises on failure
        assert "returncode" in content
        assert "RuntimeError" in content
        assert "Git command failed" in content or "Git command failure" in content


    def test_sentinel_baseline_mutation_detected(self):
        """Sentinel must detect mutations to baseline files via fingerprints."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        # Records fingerprints and compares on check
        assert "fingerprint" in content.lower()
        assert "sha256" in content.lower() or "hashlib" in content
        assert "baseline_fingerprints" in content
        assert "mutated" in content.lower() or "compute_file_hash" in content


    def test_sentinel_untracked_files_detected(self):
        """Sentinel must detect untracked files via git ls-files --others."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        assert "ls-files" in content
        assert "--others" in content
        assert "--exclude-standard" in content


    def test_sentinel_agent_runtime_excluded(self):
        """Sentinel must exclude .agent_runtime/ paths from violation checks."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        assert ".agent_runtime/" in content
        assert "excluded" in content.lower() or "filter" in content.lower()


    def test_sentinel_behavioral_authorized_unstaged_edit_passes(self):
        """Authorized unstaged edit should PASS sentinel check."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                # Initialize git repo
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                # Create authorized file
                Path("authorized.txt").write_text("initial")
                subprocess.run(["git", "add", "authorized.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                # Copy sentinel to temp dir for testing
                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                # Initialize sentinel with authorized.txt
                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0, f"Init failed: {result.stderr}"

                # Make authorized change (unstaged)
                Path("authorized.txt").write_text("modified")

                # Check - should PASS
                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode == 0, f"Authorized edit should PASS: {result.stdout} {result.stderr}"
                assert "PASS" in result.stdout

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_unauthorized_unstaged_edit_fails(self):
        """Unauthorized unstaged edit should FAIL sentinel check."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                Path("authorized.txt").write_text("initial")
                subprocess.run(["git", "add", "authorized.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0

                # Create unauthorized file
                Path("unauthorized.txt").write_text("new file")

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode == 1, f"Unauthorized edit should FAIL: {result.stdout}"
                assert "VIOLATION" in result.stderr
                assert "unauthorized.txt" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_unauthorized_staged_edit_fails(self):
        """Unauthorized STAGED edit should FAIL sentinel check."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                Path("authorized.txt").write_text("initial")
                subprocess.run(["git", "add", "authorized.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0

                # Create unauthorized file and STAGE it
                Path("unauthorized_staged.txt").write_text("staged file")
                subprocess.run(["git", "add", "unauthorized_staged.txt"], capture_output=True, check=True)

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode == 1, f"Unauthorized staged edit should FAIL: {result.stdout}"
                assert "VIOLATION" in result.stderr
                assert "unauthorized_staged.txt" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_unauthorized_rename_fails(self):
        """Unauthorized rename should FAIL (detected as delete + add via --no-renames)."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                Path("authorized.txt").write_text("initial")
                subprocess.run(["git", "add", "authorized.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0

                # Rename authorized.txt to unauthorized_renamed.txt
                subprocess.run(["git", "mv", "authorized.txt", "unauthorized_renamed.txt"], capture_output=True, check=True)

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                # Should detect both delete (authorized.txt) and add (unauthorized_renamed.txt)
                # At least one should be unauthorized
                assert result.returncode == 1, f"Unauthorized rename should FAIL: {result.stdout} {result.stderr}"
                assert "VIOLATION" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_untouched_baseline_artifact_passes(self):
        """Pre-existing baseline artifact not in authorized paths but untouched should PASS."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                # Create baseline artifact (pre-existing, not authorized)
                Path("baseline_artifact.txt").write_text("pre-existing")
                subprocess.run(["git", "add", "baseline_artifact.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                # Only authorize a different file
                Path("authorized.txt").write_text("initial")
                subprocess.run(["git", "add", "authorized.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "add authorized"], capture_output=True, check=True)

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0

                # No changes - baseline_artifact.txt is untouched
                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode == 0, f"Untouched baseline should PASS: {result.stdout}"
                assert "PASS" in result.stdout

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_modified_baseline_artifact_fails(self):
        """Modified baseline artifact (not authorized) should FAIL."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                Path("baseline_artifact.txt").write_text("pre-existing")
                subprocess.run(["git", "add", "baseline_artifact.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                Path("authorized.txt").write_text("initial")
                subprocess.run(["git", "add", "authorized.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "add authorized"], capture_output=True, check=True)

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0

                # Modify baseline artifact (not authorized)
                Path("baseline_artifact.txt").write_text("modified!")

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode == 1, f"Modified baseline should FAIL: {result.stdout} {result.stderr}"
                assert "VIOLATION" in result.stderr
                assert "baseline_artifact.txt" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_git_diff_failure_fails_closed(self):
        """Real git diff failure must propagate and cause sentinel FAIL, never PASS."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                # Test outside a git repo - this should fail
                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                # Try to init without git repo - should fail
                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode != 0, f"Init should fail outside git repo: {result.stdout}"
                assert "Git command failed" in result.stderr or "Git command failure" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_git_ls_files_failure_fails_closed(self):
        """Real git ls-files failure must propagate and cause sentinel FAIL, never PASS."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                # Test check outside a git repo - this should fail
                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                # Create a fake contract file to bypass the "no contract" check
                Path(".agent_runtime").mkdir(exist_ok=True)
                Path(".agent_runtime/task_scope.json").write_text(json.dumps({
                    "task_id": "test",
                    "authorized_paths": ["authorized.txt"],
                    "baseline_paths": [],
                    "baseline_fingerprints": {}
                }))

                # Try to check without git repo - should fail
                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode != 0, f"Check should fail outside git repo: {result.stdout}"
                assert "Git command failed" in result.stderr or "Git command failure" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_unauthorized_baseline_deletion_fails(self):
        """Unauthorized deletion of fingerprinted baseline file must FAIL."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                # Create baseline file that will be fingerprinted
                Path("baseline_file.txt").write_text("pre-existing content")
                subprocess.run(["git", "add", "baseline_file.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                # Authorize a different file
                Path("authorized.txt").write_text("initial")
                subprocess.run(["git", "add", "authorized.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "add authorized"], capture_output=True, check=True)

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0

                # Now DELETE the fingerprinted baseline file (unauthorized)
                os.remove("baseline_file.txt")
                # Need to stage the deletion for it to be tracked
                subprocess.run(["git", "rm", "baseline_file.txt"], capture_output=True, check=True)

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode == 1, f"Unauthorized baseline deletion should FAIL: {result.stdout} {result.stderr}"
                assert "VIOLATION" in result.stderr
                assert "baseline_file.txt" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_authorized_baseline_deletion_passes(self):
        """Authorized deletion of fingerprinted baseline file must PASS."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                # Create baseline file that will be fingerprinted AND authorized
                Path("authorized_baseline.txt").write_text("pre-existing content")
                subprocess.run(["git", "add", "authorized_baseline.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                # Authorize THIS file (so deletion is authorized)
                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized_baseline.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0

                # Now DELETE the authorized baseline file
                os.remove("authorized_baseline.txt")
                subprocess.run(["git", "rm", "authorized_baseline.txt"], capture_output=True, check=True)

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode == 0, f"Authorized baseline deletion should PASS: {result.stdout} {result.stderr}"
                assert "PASS" in result.stdout

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_git_failure_cannot_produce_pass(self):
        """Git command failure must never silently produce PASS."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                # Test outside a git repo - this should fail
                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                # Try to init without git repo - should fail
                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode != 0
                assert "PASS" not in result.stdout
                assert "Git command failed" in result.stderr or "Git command failure" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_exact_offending_path_reported(self):
        """Sentinel must report exact offending path on violation."""
        import subprocess
        import tempfile
        import os
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                subprocess.run(["git", "init"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)

                Path("authorized.txt").write_text("initial")
                subprocess.run(["git", "add", "authorized.txt"], capture_output=True, check=True)
                subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, check=True)

                sentinel_src = Path(old_cwd) / "tools" / "task_scope_sentinel.py"
                Path("tools").mkdir(exist_ok=True)
                import shutil
                shutil.copy(sentinel_src, Path("tools") / "task_scope_sentinel.py")

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "init", "test_task", "authorized.txt"
                ], capture_output=True, text=True)
                assert result.returncode == 0

                Path("exact_offender.txt").write_text("bad")

                result = subprocess.run([
                    "python", "-m", "tools.task_scope_sentinel", "check"
                ], capture_output=True, text=True)
                assert result.returncode == 1
                assert "exact_offender.txt" in result.stderr

            finally:
                os.chdir(old_cwd)


    def test_sentinel_behavioral_no_repair_delete_behavior(self):
        """Sentinel must never repair, delete, restore, or modify files."""
        sentinel_path = Path("tools/task_scope_sentinel.py")
        content = sentinel_path.read_text()

        # Check no dangerous operations
        assert "os.remove" not in content
        assert "shutil.rmtree" not in content
        assert "git checkout" not in content
        assert "git restore" not in content
        assert "git reset" not in content
        assert "unlink" not in content
        # Should only read and report


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])