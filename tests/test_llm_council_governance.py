"""
Governance contract tests for the Obsidian-RL LLM Council overlay.

These tests validate repository-owned governance contracts only.
They do NOT test global/local Hermes config from pytest.
"""

import re
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


class TestLLMCouncilGovernance:
    """Validate the LLM Council governance contracts."""

    def test_permanent_role_count_remains_exactly_15(self):
        """Permanent role count must remain exactly 15 — Council adds zero permanent roles."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        assert roles_path.exists(), "AGENT_OFFICE_ROLES.md must exist"

        content = roles_path.read_text()

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

        assert len(all_roles) == 15, f"Expected 15 permanent roles, found {len(all_roles)}"

        # Council must NOT add permanent roles - check no council roles in permanent list
        council_roles = [
            "CONTRARIAN",
            "FIRST-PRINCIPLES",
            "EXPANSIONIST",
            "OUTSIDER",
            "EXECUTOR",
            "PEER REVIEWER",
            "COUNCIL CHAIRMAN",
        ]
        for crole in council_roles:
            header = f"### {crole}"
            assert header not in content, (
                f"Council role '{crole}' must not appear as permanent role"
            )

    def test_hierarchy_unchanged(self):
        """Hierarchy must be unchanged — Council is advisory overlay only."""
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        content = workflow_path.read_text()

        # Verify original tier structure still documented
        assert "TIER 1 — CHIEF ORCHESTRATOR" in content
        assert "TIER 1 — PLANNING / WORKFLOW MANAGER" in content
        assert "TIER 2 — DOMAIN MANAGERS" in content
        assert "TIER 3 — SPECIALISTS" in content

        # Council protocol doc must state advisory only
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        council_content = council_path.read_text()
        assert "Council is advisory evidence, NEVER authorization" in council_content
        assert "The 15 permanent roles remain EXACT" in council_content
        assert "Council advisors/reviewers are temporary deliberation instances" in council_content

    def test_council_advisors_reviewers_read_only(self):
        """Council advisors/reviewers must have zero write authority."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        # Explicit read-only statements
        assert "NO write authority" in content or "no write authority" in content.lower()
        assert "Cannot override" in content
        assert "Cannot authorize commit/push" in content
        assert "Cannot bypass USER" in content
        assert "Cannot modify trading/research rules automatically" in content

        # Skill must enforce read-only
        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        skill_content = skill_path.read_text()
        assert "NO write authority" in skill_content or "read-only" in skill_content.lower()
        assert (
            "ZERO write authority" in skill_content or "no write authority" in skill_content.lower()
        )

    def test_council_cannot_commit_push(self):
        """Council temporary roles cannot commit/push/write production."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "Cannot authorize commit/push" in content
        assert "No repository writes by temporary council agents" in content
        assert "No commit/push" in content

        # No role in AGENT_OFFICE_ROLES.md gets commit/push via council
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        roles_content = roles_path.read_text()

        forbidden = ["git commit", "git push", "git add .", "git add -A"]
        for cmd in forbidden:
            # These should only appear in forbidden_commands sections
            allowed_sections = re.findall(
                r"allowed_commands:.*?(?=\n\w+:|\nforbidden_commands:|\n```)",
                roles_content,
                re.DOTALL,
            )
            for section in allowed_sections:
                assert cmd not in section, f"Council must not grant '{cmd}' in allowed_commands"

    def test_max_active_children_remains_3(self):
        """Max active children must remain 3 (inherited from office config)."""
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        content = workflow_path.read_text()

        assert "Max 3 specialist/reviewer children concurrently" in content
        # BASE office doc uses "Spawn depth 1 (if Hermes supports it)" for delegation depth
        # and relies on skill config for max_concurrent_children: 3
        # Accept either formulation
        assert (
            "max_concurrent_children 3" in content
            or "max_concurrent_children: 3" in content
            or "Max 3 specialist/reviewer children concurrently" in content
        )

        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        council_content = council_path.read_text()
        assert (
            "Max 3 children concurrently" in council_content
            or "max 3 concurrent" in council_content.lower()
        )

        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        skill_content = skill_path.read_text()
        assert (
            "max_concurrent_children 3" in skill_content
            or "maximum 3 simultaneous" in skill_content.lower()
        )

    def test_frozen_identical_advisor_context(self):
        """Advisor prompt/context must be frozen identically for all 5."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "frozen context digest" in content.lower() or "frozen context" in content.lower()
        assert "byte-identical" in content.lower() or "byte/logically identical" in content.lower()
        assert "SHA-256" in content

        # Advisor prompts reference must specify shared frozen context
        advisor_path = Path(".hermes/skills/obsidian-rl-council/references/advisor-prompts.md")
        advisor_content = advisor_path.read_text()
        assert "SHARED FROZEN CONTEXT" in advisor_content
        assert "injected identically into all 5" in advisor_content
        assert "CONTEXT_DIGEST_SHA256" in advisor_content

    def test_advisor_isolation_no_information_bleed(self):
        """Advisor outputs must be hidden until all 5 complete — no information bleed."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "NO advisor receives/reads prior advisor output" in content
        assert "NO shared response context before all 5 finish" in content
        assert "Scheduling later does NOT permit information bleed" in content
        assert "information bleed" in content.lower()

        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        skill_content = skill_path.read_text()
        assert "no advisor receives/reads prior" in skill_content.lower()
        assert "no shared response context before all 5" in skill_content.lower()

    def test_five_advisors_required_for_complete(self):
        """All 5 advisors required for COMPLETE status — partial = BLOCKED."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert (
            "5 advisors REQUIRED for COMPLETE" in content
            or "5 advisors required for complete" in content.lower()
        )
        assert "All 5 advisors REQUIRED" in content

        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        skill_content = skill_path.read_text()
        assert (
            "5 advisors REQUIRED" in skill_content
            or "all 5 advisors required" in skill_content.lower()
        )

        # Provider failure blocks complete
        assert "FAILED_PROVIDER" in council_path.read_text()
        assert (
            "NEVER fabricated PASS" in council_path.read_text()
            or "never fabricated pass" in council_path.read_text().lower()
        )

    def test_deterministic_anonymization_contract(self):
        """Anonymization must be deterministic — same inputs produce same outputs."""
        anon_path = Path(".hermes/skills/obsidian-rl-council/references/anonymization.md")
        content = anon_path.read_text()

        assert "deterministic" in content.lower()
        assert "SHA256" in content or "sha256" in content.lower()
        assert "permutation" in content.lower() or "relabel" in content.lower()
        assert "same inputs" in content.lower() or "same inputs" in content.lower()

        # Must remove persona identifiers
        assert "remove" in content.lower() and "persona" in content.lower()
        assert "Contrarian" in content or "contrarian" in content.lower()

        # Must preserve substantive content
        assert (
            "Preserve substantive content" in content or "preserve substantive" in content.lower()
        )

        # Internal mapping preserved privately
        assert "anonymization_map.json" in content
        assert (
            "NEVER shown to reviewers" in content
            or "never shared with reviewers" in content.lower()
        )

    def test_reviewers_cannot_access_identity_map(self):
        """Reviewers must not have access to the anonymization identity map."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "Reviewers cannot see identity map" in content
        assert "cannot access" in content.lower() and "identity map" in content.lower()

        reviewer_path = Path(".hermes/skills/obsidian-rl-council/references/reviewer-prompts.md")
        reviewer_content = reviewer_path.read_text()
        assert "Reviewers CANNOT see identity map" in reviewer_content
        assert "cannot see identity map" in reviewer_content.lower()

    def test_five_reviewers_required_for_complete(self):
        """All 5 reviewers required for COMPLETE status — partial = BLOCKED."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()
        assert (
            "5 reviewers REQUIRED for COMPLETE" in content
            or "5 reviewers required for complete" in content.lower()
        )
        assert "All 5 reviewers REQUIRED" in content

        # Provider failure blocks complete
        assert "FAILED_PROVIDER" in content
        assert "NEVER fabricated PASS" in content or "never fabricated pass" in content.lower()

    def test_partial_provider_failed_cannot_claim_complete(self):
        """Partial or provider-failed council cannot claim complete."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "FAILED_PROVIDER" in content
        assert "cannot claim complete" in content.lower() or "partial.*blocked" in content.lower()

        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        skill_content = skill_path.read_text()
        assert "FAILED_PROVIDER" in skill_content
        assert "NEVER fabricated PASS" in skill_content

    def test_chief_is_synthesis_only_not_new_writer(self):
        """Chief must be synthesis only, not a new writer with write authority."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "SYNTHESIS ONLY" in content
        assert "not a new writer" in content.lower()
        assert "not a decision-maker" in content.lower()

        chairman_path = Path(".hermes/skills/obsidian-rl-council/references/chairman-prompts.md")
        chairman_content = chairman_path.read_text()
        assert "SYNTHESIS ONLY" in chairman_content
        assert "not a new writer" in chairman_content.lower()
        assert "not a decision-maker" in chairman_content.lower()

    def test_minority_warning_preserved(self):
        """Minority warning must be preserved — mandatory field, not empty."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "MINORITY_WARNING" in content
        assert "MUST preserve material minority warnings" in content
        assert "Majority vote alone is NOT truth" in content
        assert 'If none, "NONE"' in content
        assert "Must not be empty string" in content or "not be empty" in content.lower()

        chairman_path = Path(".hermes/skills/obsidian-rl-council/references/chairman-prompts.md")
        chairman_content = chairman_path.read_text()
        assert "MINORITY_WARNING" in chairman_content
        assert "MUST preserve material minority warnings" in chairman_content
        assert 'If none, "NONE"' in chairman_content

    def test_council_cannot_override_blocked_financial_safety(self):
        """Council cannot override BLOCKED financial/safety evidence."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "Cannot override BLOCKED financial/safety evidence" in content
        assert "cannot override" in content.lower() and "blocked" in content.lower()

        # Gatekeeper retains veto
        assert "Release Gatekeeper retains veto" in content
        assert "Gatekeeper retains veto" in content

    def test_gatekeeper_retains_veto(self):
        """Release Gatekeeper must retain veto over council recommendations."""
        workflow_path = Path("docs/engineering/MULTI_AGENT_WORKFLOW.md")
        content = workflow_path.read_text()

        assert "independent read-only veto" in content
        assert "final internal gate" in content
        assert "Release Gatekeeper refuses READY while any unresolved BLOCKED exists" in content

        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        council_content = council_path.read_text()
        assert "Release Gatekeeper retains veto" in council_content
        assert "Gatekeeper still applies existing veto rules" in council_content

    def test_user_retains_sole_commit_push_authority(self):
        """USER must retain sole commit/push authority."""
        roles_path = Path("docs/engineering/AGENT_OFFICE_ROLES.md")
        content = roles_path.read_text()

        chief_section = content[
            content.find("CHIEF ORCHESTRATOR") : content.find(
                "### ", content.find("CHIEF ORCHESTRATOR") + 1
            )
        ]
        assert "escalation_path: USER" in chief_section
        user_phrase = "USER (sole commit/push authority)"
        alt_phrase = "sole commit/push"
        assert user_phrase in chief_section or alt_phrase in chief_section.lower()

        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        council_content = council_path.read_text()
        assert "Cannot bypass USER" in council_content
        assert "USER remains final commit/push authority" in council_content

    def test_trivial_tasks_do_not_auto_trigger_council(self):
        """Trivial/mechanical tasks must not automatically invoke council."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        # Explicit list of what does NOT trigger council
        assert "Do NOT council" in content or "do not council" in content.lower()
        assert "factual lookup" in content.lower()
        assert "mechanical edit" in content.lower()
        assert "routine test/lint failure" in content.lower()
        assert "obvious bounded bugfix" in content.lower()
        assert "ordinary documentation change" in content.lower()

    def test_runtime_council_evidence_git_ignored(self):
        """Runtime council evidence path must be Git-ignored/non-authoritative."""
        gitignore_path = Path(".gitignore")
        gitignore_content = gitignore_path.read_text()

        assert ".agent_runtime/" in gitignore_content

        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        council_content = council_path.read_text()

        assert ".agent_runtime/council/" in council_content
        assert "Git-ignored" in council_content
        auth_check = (
            "non-authoritative" in council_content.lower()
            or "not authoritative" in council_content.lower()
        )
        assert auth_check

    def test_no_automatic_deletion_of_failed_council_evidence(self):
        """Failed council evidence must not be automatically deleted."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        assert "Never delete failed councils automatically" in content
        assert "Preserve negative/contradictory evidence" in content

    def test_council_skill_exists_and_references_protocol(self):
        """Council skill must exist and reference governance docs."""
        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        assert skill_path.exists(), "Council skill must exist"

        skill_content = skill_path.read_text()

        # Must reference the governance docs
        assert "MULTI_AGENT_WORKFLOW.md" in skill_content
        assert "AGENT_OFFICE_ROLES.md" in skill_content
        assert "LLM_COUNCIL_PROTOCOL.md" in skill_content
        assert "AGENTS.md" in skill_content

        # Must not duplicate them
        assert "Do not duplicate" in skill_content or "do not duplicate" in skill_content.lower()

    def test_council_skill_frontmatter_valid(self):
        """Council skill frontmatter must be valid YAML with required fields."""
        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        content = skill_path.read_text()

        assert content.startswith("---"), "Skill must start with YAML frontmatter"

        frontmatter_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        assert frontmatter_match, "Invalid frontmatter format"

        frontmatter = yaml.safe_load(frontmatter_match.group(1))
        assert frontmatter.get("name") == "obsidian-rl-council"
        assert "description" in frontmatter
        assert frontmatter.get("category") == "software-development"
        assert "version" in frontmatter

    def test_advisor_prompt_templates_exist(self):
        """All 5 advisor prompt templates must exist in references."""
        advisor_path = Path(".hermes/skills/obsidian-rl-council/references/advisor-prompts.md")
        assert advisor_path.exists(), "Advisor prompts reference must exist"

        content = advisor_path.read_text()

        # All 5 personas
        assert "CONTRARIAN" in content
        assert "FIRST-PRINCIPLES" in content
        assert "EXPANSIONIST" in content
        assert "OUTSIDER" in content
        assert "EXECUTOR" in content

        # Shared frozen context section
        assert "SHARED FROZEN CONTEXT" in content
        assert "injected identically into all 5" in content

    def test_reviewer_prompt_template_exists(self):
        """Reviewer prompt template must exist in references."""
        reviewer_path = Path(".hermes/skills/obsidian-rl-council/references/reviewer-prompts.md")
        assert reviewer_path.exists(), "Reviewer prompts reference must exist"

        content = reviewer_path.read_text()

        assert "ANONYMIZED BUNDLE" in content
        assert "STRONGEST_RESPONSE" in content
        assert "BIGGEST_BLIND_SPOT" in content
        assert "ALL_FIVE_MISSED" in content
        assert "RANKING" in content
        assert "CONFIDENCE" in content

    def test_chairman_prompt_template_exists(self):
        """Chairman prompt template must exist in references."""
        chairman_path = Path(".hermes/skills/obsidian-rl-council/references/chairman-prompts.md")
        assert chairman_path.exists(), "Chairman prompts reference must exist"

        content = chairman_path.read_text()

        assert "AGREEMENT:" in content
        assert "DISAGREEMENT:" in content
        assert "BLIND_SPOTS:" in content
        assert "RECOMMENDATION:" in content
        assert "FIRST_ACTION:" in content
        assert "CONFIDENCE:" in content
        assert "MINORITY_WARNING:" in content
        assert "ROUTING:" in content

    def test_anonymization_reference_exists(self):
        """Anonymization reference must exist and specify deterministic algorithm."""
        anon_path = Path(".hermes/skills/obsidian-rl-council/references/anonymization.md")
        assert anon_path.exists(), "Anonymization reference must exist"

        content = anon_path.read_text()

        assert "Anonymization Algorithm" in content
        assert "Deterministic Relabeling" in content
        assert "Persona Identifier Removal" in content
        assert "Internal Mapping Preservation" in content
        assert "Fisher-Yates" in content or "permutation" in content.lower()

    def test_protocol_doc_exists_and_complete(self):
        """LLM_COUNCIL_PROTOCOL.md must exist and contain all required sections."""
        protocol_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        assert protocol_path.exists(), "LLM_COUNCIL_PROTOCOL.md must exist"

        content = protocol_path.read_text()

        # Required sections
        assert "Council Triggers" in content
        assert "STEP 1" in content
        assert "STEP 2" in content
        assert "STEP 3" in content
        assert "STEP 4" in content
        assert "STEP 5" in content
        assert "STEP 6" in content
        assert "Runtime Evidence" in content
        assert "Governance Tests" in content
        assert "Live Smoke Test" in content
        assert "Verification" in content
        assert "MIT Attribution" in content

        # Required constraints
        assert "15 permanent roles remain EXACT" in content
        assert "advisory evidence, NEVER authorization" in content
        assert "MAX 3 children concurrently" in content

    def test_anonymization_output_format_contract(self):
        """Anonymization must produce A-E labels (bijection)."""
        anon_path = Path(".hermes/skills/obsidian-rl-council/references/anonymization.md")
        content = anon_path.read_text()

        assert "A-E" in content or "A, B, C, D, E" in content
        assert "bijection" in content.lower() or "permutation" in content.lower()
        assert "All 5 advisors MUST be present" in content or (
            "all 5 advisors must be present" in content.lower()
        )

    def test_council_smoke_test_question_defined(self):
        """Smoke test question must be defined for protocol validation."""
        council_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = council_path.read_text()

        question = (
            "Should passing tests alone be sufficient evidence to bypass "
            "the Obsidian-RL Release Gatekeeper"
        )
        assert question in content
        assert "protocol validation, not repository decision" in content.lower()

    def test_council_skill_inherits_office_delegation_config(self):
        """Council skill must inherit office delegation config (max 3, depth 1)."""
        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        skill_content = skill_path.read_text()

        assert "max_concurrent_children 3" in skill_content
        assert "max_spawn_depth 1" in skill_content
        orch_check = (
            "orchestrator_enabled false" in skill_content
            or "flat delegation only" in skill_content.lower()
        )
        assert orch_check

    def test_council_write_enforcement_not_enforceable(self):
        """Council skill must document LIVE_COUNCIL_WRITE_ISOLATION = NOT_ENFORCEABLE."""
        skill_path = Path(".hermes/skills/obsidian-rl-council/SKILL.md")
        skill_content = skill_path.read_text()

        assert "LIVE_COUNCIL_WRITE_ISOLATION = NOT_ENFORCEABLE" in skill_content
        assert "Hermes delegation does NOT support per-child tool allowlists" in skill_content
        assert "prompt instructions alone do NOT provide hard isolation" in skill_content
        assert "Until enforcement available" in skill_content
        assert "Council local gate MUST be BLOCKED" in skill_content

    def test_protocol_documents_write_enforcement_classification(self):
        """Protocol must document ENFORCEMENT CLASSIFICATION."""
        protocol_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = protocol_path.read_text()

        assert "LIVE_COUNCIL_WRITE_ISOLATION = NOT_ENFORCEABLE" in content
        assert "Hermes delegation does NOT support per-child tool allowlists" in content
        assert "prompt instructions alone do NOT provide hard isolation" in content
        assert "Council live delegation CANNOT be marked SAFE" in content
        assert "Council local gate MUST be BLOCKED" in content

    def test_write_violation_is_terminal(self):
        """WRITE_VIOLATION must be terminal — cannot become COMPLETE/PASS."""
        protocol_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = protocol_path.read_text()

        assert "WRITE_VIOLATION IS TERMINAL" in content
        assert "cannot be converted to COMPLETE/PASS" in content
        assert "by any later stage" in content

    def test_council_smoke_fingerprints_worktree_between_batches(self):
        """Council smoke must fingerprint worktree between all batches."""
        protocol_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = protocol_path.read_text()

        assert "POST-BATCH WORKTREE CHECK" in content
        assert "pre_smoke_fingerprint.json" in content
        assert "After EVERY advisor batch AND EVERY reviewer batch" in content
        assert "git status --porcelain=v1 --untracked-files=all" in content
        assert "git diff --name-status" in content

    def test_unauthorized_repo_mutation_fails_scope_sentinel(self):
        """Scope sentinel must treat Council-created repo files as violations."""
        protocol_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = protocol_path.read_text()

        assert (
            "Scope Sentinel MUST treat any Council-created tracked/untracked repo file" in content
        )
        assert "outside Council runtime evidence as violation" in content

    def test_failed_council_evidence_preserved(self):
        """Failed Council evidence must be preserved."""
        protocol_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = protocol_path.read_text()

        assert "Never delete failed councils automatically" in content
        assert "Preserve negative/contradictory evidence" in content
        assert "archive evidence under" in content
        assert "unauthorized_write" in content

    def test_council_protocol_hardened_post_batch_checks(self):
        """Protocol must have post-batch worktree checks for both advisors and reviewers."""
        protocol_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = protocol_path.read_text()

        # Advisor batches
        assert "After each advisor batch (Batch 1 and Batch 2)" in content
        # Reviewer batches
        assert "After each reviewer batch (Batch 1 and Batch 2)" in content
        # Both advisor and reviewer batches must check
        assert "After EVERY advisor batch AND EVERY reviewer batch" in content
        """MIT attribution for YonasValentin/llm-council must be preserved."""
        protocol_path = Path("docs/engineering/LLM_COUNCIL_PROTOCOL.md")
        content = protocol_path.read_text()

        assert "YonasValentin/llm-council" in content
        assert "MIT License" in content
        assert "MIT License Notice" in content
        assert "Copyright (c) YonasValentin" in content
        assert "Permission is hereby granted" in content


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
