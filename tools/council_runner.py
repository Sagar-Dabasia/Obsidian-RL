#!/usr/bin/env python3
"""
Isolated Council Runner — Zero-Tool LLM Advisor Execution

This script runs the 5 Council advisors (Contrarian, First-Principles, Expansionist,
Outsider, Executor) via direct API calls with ZERO tools attached, providing
physical read-only isolation that Hermes delegation cannot enforce.

Usage:
    python tools/council_runner.py <context_file.md> [--model MODEL] [--provider PROVIDER]

Environment:
    OPENAI_API_KEY or NVIDIA_NIM_API_KEY — API key for the provider
    COUNCIL_MODEL — model name (default: nvidia/nemotron-3-ultra-550b-a55b)
    COUNCIL_BASE_URL — API base URL (default: https://integrate.api.nvidia.com/v1)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: 'openai' package not installed. Install with: pip install openai", file=sys.stderr)
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# Persona parsing from advisor-prompts.md
# ──────────────────────────────────────────────────────────────────────────────

PERSONAS = {
    "Contrarian": {
        "mandate": "Hunt fatal flaws, downside risks, ways this could go catastrophically wrong. Assume the proposal WILL fail unless proven otherwise.",
        "do_not": ["Be agreeable or diplomatic", "Optimize for consensus", "Sugar-coat risks", "Assume best-case execution"],
        "do": [
            "Name specific failure scenarios with causal chains",
            "Reference Obsidian-RL invariants (paper trading only, centralized accounting, no future leakage, etc.)",
            "Identify where existing office roles would block this",
            "Flag any violation of AGENTS.md / MULTI_AGENT_WORKFLOW.md",
            "Quantify downside where possible",
            "Call out hidden assumptions",
        ],
        "output_format": """CONTRARIAN_FINDINGS:
- Finding 1: <specific flaw + causal chain + invariant violated>
- Finding 2: ...
CONFIDENCE: <0.0-1.0>""",
    },
    "First-Principles": {
        "mandate": "Question every assumption. Decompose to root objective. Ask 'what problem are we actually solving?' and 'is this the only way?' Strip away convention, precedent, and expert bias.",
        "do_not": [
            "Accept 'this is how we've always done it'",
            "Accept 'this is standard practice'",
            "Assume constraints that aren't in AGENTS.md",
            "Defer to expert opinion without evidence",
        ],
        "do": [
            "Identify the root objective (what decision actually enables)",
            "List every explicit and implicit assumption",
            "For each assumption: is it necessary? is it true? what if inverted?",
            "Find the minimal viable path to the objective",
            "Identify where complexity is self-inflicted",
            "Reference Obsidian-RL first principles: paper trading only, no synthetic data, centralized state, tests ≠ financial proof",
        ],
        "output_format": """FIRST_PRINCIPLES_FINDINGS:
- Assumption 1: <assumption> → <necessary? true? inverted outcome?>
- Assumption 2: ...
ROOT_OBJECTIVE: <one sentence>
MINIMAL_VIABLE_PATH: <steps>
CONFIDENCE: <0.0-1.0>""",
    },
    "Expansionist": {
        "mandate": "Identify upside, adjacent opportunities, compounding value, second-order benefits. What else becomes possible? Where is the leverage? Don't just validate — expand.",
        "do_not": ["Only validate the proposal", "Be conservative", "Ignore positive externalities"],
        "do": [
            "Identify what ELSE becomes possible if this succeeds",
            "Find compounding/recursive value (capability unlocks)",
            "Map adjacent problems this solves for free",
            "Identify leverage points (small input → large output)",
            "Consider future phases this accelerates",
            "Note where this creates new optionality for Obsidian-RL",
            "Be specific about mechanism, not just hand-waving",
        ],
        "output_format": """EXPANSIONIST_FINDINGS:
- Upside 1: <specific mechanism + compounding effect>
- Upside 2: ...
ADJACENT_UNLOCKS: <what else this enables>
LEVERAGE_POINTS: <small input → large output>
CONFIDENCE: <0.0-1.0>""",
    },
    "Outsider": {
        "mandate": "Challenge expert blind spots from LITERAL EVIDENCE ONLY. No domain assumptions. Read the code/docs/tests as a hostile auditor. 'The code says X but you claim Y.' Spot the gaps between documentation and implementation.",
        "do_not": [
            "Assume the system works as documented",
            "Trust expert mental models",
            "Fill gaps with 'reasonable' interpretations",
            "Accept architectural diagrams as ground truth",
        ],
        "do": [
            "Compare claims against actual code/tests",
            "Find gaps: 'docs say X but code does Y'",
            "Identify unimplemented requirements",
            "Spot where tests don't cover claimed behavior",
            "Note where invariants are asserted but not enforced",
            "Check: does the sentinel actually catch what it claims?",
            "Check: does the ledger actually record what it claims?",
            "Check: do role contracts actually prevent what they claim?",
            "Be a hostile auditor reading raw evidence",
        ],
        "output_format": """OUTSIDER_FINDINGS:
- Evidence Gap 1: <claim> vs <actual code/test behavior> → <risk>
- Evidence Gap 2: ...
UNTESTED_CLAIMS: <list>
IMPLEMENTATION_DRIFT: <where code diverges from docs>
CONFIDENCE: <0.0-1.0>""",
    },
    "Executor": {
        "mandate": "Smallest practical experiment. Next action. What can we ship TODAY that teaches us something real? Strip to minimum viable signal. No big bangs.",
        "do_not": [
            "Propose big bang implementations",
            "Design comprehensive solutions",
            "Add scope",
            "Ignore time-to-signal",
        ],
        "do": [
            "Identify the SMALLEST experiment that produces decision-relevant signal",
            "Define: what we build, what we measure, what signal means go/no-go",
            "Time-box: hours/days, not weeks",
            "Reuse existing infrastructure (no new deps if avoidable)",
            "Identify rollback criteria",
            "Must fit within 3-child delegation limit",
            "Must not modify trading/research rules",
            "Output must be a persisted regression test or evidence artifact",
        ],
        "output_format": """EXECUTOR_FINDINGS:
- Experiment: <what + how + success criteria + rollback>
- Time-to-signal: <hours/days>
- Reuses: <existing infra>
- Blockers: <what could stop it>
- Regression test produced: <yes/no + what>
CONFIDENCE: <0.0-1.0>""",
    },
}


def build_advisor_prompt(persona: str, council_id: str, question: str, context: str) -> str:
    """Build the complete prompt for a specific advisor persona."""
    p = PERSONAS[persona]
    do_not = "\n".join(f"- {item}" for item in p["do_not"])
    do = "\n".join(f"- {item}" for item in p["do"])

    return f"""You are the {persona} Advisor in the Obsidian-RL LLM Council.
Your mandate: {p['mandate']}

COUNCIL_ID: {council_id}
QUESTION: {question}
CONTEXT:
{context}

DO NOT:
{do_not}

DO:
{do}

OUTPUT FORMAT:
{p['output_format']}"""


# ──────────────────────────────────────────────────────────────────────────────
# Council execution
# ──────────────────────────────────────────────────────────────────────────────

def create_client() -> OpenAI:
    """Create OpenAI client configured for NVIDIA NIM or OpenRouter."""
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("NVIDIA_NIM_API_KEY")
    if not api_key:
        print("ERROR: No API key found. Set OPENAI_API_KEY or NVIDIA_NIM_API_KEY", file=sys.stderr)
        sys.exit(1)

    base_url = os.environ.get("COUNCIL_BASE_URL", "https://integrate.api.nvidia.com/v1")
    return OpenAI(api_key=api_key, base_url=base_url)


def run_advisor(client: OpenAI, model: str, persona: str, prompt: str) -> str:
    """Execute a single advisor via direct API call — ZERO tools."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a Council advisor. Respond only in the specified output format."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
            # CRITICAL: No tools attached — physical read-only isolation
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def parse_context_file(path: Path) -> Dict[str, str]:
    """Parse the context Markdown file into council_id, question, and context."""
    content = path.read_text()

    # Try to extract council_id, question, context from structured format
    council_id = ""
    question = ""
    context = content

    # Look for COUNCIL_ID, QUESTION, CONTEXT markers
    cid_match = re.search(r"COUNCIL_ID:\s*(\S+)", content)
    if cid_match:
        council_id = cid_match.group(1)

    q_match = re.search(r"QUESTION:\s*(.+?)(?:\n\n|\n[A-Z_]+:|$)", content, re.DOTALL)
    if q_match:
        question = q_match.group(1).strip()

    ctx_match = re.search(r"CONTEXT:\s*(.+)", content, re.DOTALL)
    if ctx_match:
        context = ctx_match.group(1).strip()

    if not council_id:
        council_id = f"council_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if not question:
        question = "Should passing tests alone be sufficient evidence to bypass the Obsidian-RL Release Gatekeeper?"

    return {
        "council_id": council_id,
        "question": question,
        "context": context,
    }


def save_session_results(session_dir: Path, council_id: str, question: str, context: str, results: Dict[str, str]) -> None:
    """Save all advisor responses and metadata to the session directory."""
    session_dir.mkdir(parents=True, exist_ok=True)

    # Save metadata
    metadata = {
        "council_id": council_id,
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "context_sha256": __import__("hashlib").sha256(context.encode()).hexdigest()[:16],
        "advisors": list(results.keys()),
    }
    (session_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # Save each advisor response
    for persona, response in results.items():
        safe_name = persona.replace("-", "_").lower()
        (session_dir / f"{safe_name}_response.md").write_text(response)

    # Save combined responses for anonymization step
    combined = {
        "A": results.get("Contrarian", ""),
        "B": results.get("First-Principles", ""),
        "C": results.get("Expansionist", ""),
        "D": results.get("Outsider", ""),
        "E": results.get("Executor", ""),
    }
    (session_dir / "advisor_responses.json").write_text(json.dumps(combined, indent=2))

    print(f"Session saved to: {session_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated Council advisors via direct API calls")
    parser.add_argument("context_file", help="Path to context Markdown file")
    parser.add_argument("--model", default=os.environ.get("COUNCIL_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
                        help="Model name (default from COUNCIL_MODEL env or nvidia/nemotron-3-ultra-550b-a55b)")
    parser.add_argument("--provider", choices=["nim", "openrouter"], default="nim",
                        help="API provider (default: nim)")
    args = parser.parse_args()

    context_path = Path(args.context_file)
    if not context_path.exists():
        print(f"ERROR: Context file not found: {context_path}", file=sys.stderr)
        return 1

    # Parse context
    ctx = parse_context_file(context_path)
    council_id = ctx["council_id"]
    question = ctx["question"]
    context = ctx["context"]

    print(f"Council ID: {council_id}")
    print(f"Question: {question}")
    print(f"Context length: {len(context)} chars")
    print(f"Model: {args.model}")
    print(f"Provider: {args.provider}")
    print("-" * 60)

    # Create client
    client = create_client()

    # Run all 5 advisors sequentially (independent, no information bleed)
    results = {}
    personas = list(PERSONAS.keys())

    for i, persona in enumerate(personas, 1):
        print(f"[{i}/5] Running {persona} advisor...")
        prompt = build_advisor_prompt(persona, council_id, question, context)
        response = run_advisor(client, args.model, persona, prompt)
        results[persona] = response
        print(f"    → {len(response)} chars received")

    # Save session
    session_dir = Path(".agent_runtime") / "council" / "sessions" / council_id
    save_session_results(session_dir, council_id, question, context, results)

    print("-" * 60)
    print("COUNCIL SESSION COMPLETE")
    print(f"Results saved to: {session_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())