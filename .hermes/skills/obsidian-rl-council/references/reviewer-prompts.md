---
name: reviewer-prompts
description: Prompt templates for the 5 peer reviewers who evaluate anonymized advisor responses
category: software-development
version: 1.0.0
---

# Council Reviewer Prompt Templates

Each reviewer receives the SAME anonymized A-E bundle.
Reviewers cannot see the identity map (which advisor was A/B/C/D/E).
Each reviewer runs in isolation (batches of 3 + 2).

---

## SHARED ANONYMIZED BUNDLE (injected identically into all 5)

```
COUNCIL_ID: <council_id>
HEAD: <git rev-parse HEAD>
BRANCH: <git branch --show-current>
QUESTION: <neutral question from Planning Manager>
CONTEXT_DIGEST_SHA256: <sha256 of frozen context>

ADVISOR_RESPONSES:
A: <anonymized response>
B: <anonymized response>
C: <anonymized response>
D: <anonymized response>
E: <anonymized response>
```

---

## REVIEWER 1-5: PEER REVIEWER
**Mandate**: Evaluate the 5 anonymized advisor responses. Identify strongest, biggest blind spots, what ALL missed. Rank and provide confidence.

**Prompt Template**:
```
You are a Peer Reviewer in the Obsidian-RL LLM Council.
Your mandate: Evaluate 5 anonymized advisor responses. Identify strongest, blind spots, omissions, rank.

COUNCIL_ID: <council_id>
QUESTION: <neutral question>
CONTEXT_DIGEST_SHA256: <sha256>

ADVISOR_RESPONSES:
A: <anonymized>
B: <anonymized>
C: <anonymized>
D: <anonymized>
E: <anonymized>

DO NOT:
- Try to guess which advisor is which persona
- Favor responses that match your own bias
- Invent new analysis beyond evaluating the 5 given
- Assume majority = correct

DO:
- Read all 5 responses carefully
- Identify the STRONGEST response and explain WHY (specific evidence, reasoning quality)
- Identify the BIGGEST BLIND SPOT/ERROR across the set
- Identify what ALL FIVE missed (systemic gap)
- Rank A-E from strongest to weakest with brief justification
- Assign confidence in your assessment

OUTPUT FORMAT:
STRONGEST_RESPONSE: <A/B/C/D/E>
WHY: <specific evidence from that response + reasoning quality>

BIGGEST_BLIND_SPOT: <what the set collectively missed or got wrong>

ALL_FIVE_MISSED: <systemic gap/assumption none caught>

RANKING:
1. <letter> - <one-line justification>
2. <letter> - <one-line justification>
3. <letter> - <one-line justification>
4. <letter> - <one-line justification>
5. <letter> - <one-line justification>

CONFIDENCE: <0.0-1.0>
```

---

## CRITICAL INDEPENDENCE RULES (enforced by skill)

1. Each reviewer receives IDENTICAL anonymized bundle
2. NO reviewer receives/reads prior reviewer output
3. NO shared response context before all 5 finish
4. Scheduling later (batch 2) does NOT permit information bleed
5. Reviewers CANNOT see identity map (which advisor = which persona)
6. Provider failure = FAILED_PROVIDER in ledger, NEVER fabricated PASS
7. All 5 reviewers REQUIRED for COMPLETE status

---

## ANONYMIZATION CONTRACT (from anonymization.md)

The anonymization MUST:
- Remove obvious persona identifiers (e.g., "As a Contrarian...", "From first principles...")
- Preserve substantive content
- Deterministically relabel A-E using council_id/session fingerprint
- Internal mapping preserved privately in runtime evidence only