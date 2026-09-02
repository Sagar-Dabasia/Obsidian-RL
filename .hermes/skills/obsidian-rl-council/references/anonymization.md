---
name: anonymization
description: Deterministic anonymization protocol for council advisor responses and peer reviews
category: software-development
version: 1.0.0
---

# Council Anonymization Protocol

## Purpose

Remove obvious persona identifiers from advisor responses while preserving substantive content. Ensure reviewers cannot deduce which advisor had which persona (Contrarian, First-Principles, Expansionist, Outsider, Executor).

## Anonymization Algorithm

### Input
- 5 advisor responses with known persona labels (A=Contrarian, B=First-Principles, C=Expansionist, D=Outsider, E=Executor)
- council_id (unique per council session)
- session_fingerprint (SHA-256 of frozen context + HEAD + timestamp)

### Deterministic Relabeling

1. Compute `relabel_seed = SHA256(council_id + session_fingerprint)`
2. Convert first 5 bytes of seed to a permutation of [0,1,2,3,4] using Fisher-Yates shuffle
3. Apply permutation to advisor responses
4. New labels: A, B, C, D, E (randomized per council)

### Persona Identifier Removal

For each response, strip/obfuscate obvious persona markers:
- "As a Contrarian..." / "Contrarian view:" / "Contrarian finding:" → remove
- "From first principles..." / "First-principles analysis:" → remove
- "Expansionist view:" / "Upside opportunity:" → remove
- "As an Outsider..." / "External audit:" / "Hostile auditor:" → remove
- "Executor view:" / "Minimum viable experiment:" / "Next action:" → remove
- Any explicit role self-identification

Preserve:
- All substantive findings, evidence, reasoning
- Specific references to code/files/tests
- Confidence scores
- Structural format (findings lists, etc.)

### Internal Mapping Preservation

Maintain private mapping in runtime evidence:
```
.agent_runtime/council/<council_id>/anonymization_map.json
{
  "council_id": "...",
  "original_to_anonymized": {"Contrarian": "C", "First-Principles": "A", ...},
  "anonymized_to_original": {"A": "First-Principles", "B": "Outsider", ...},
  "relabel_seed": "...",
  "session_fingerprint": "..."
}
```

This mapping is NEVER shown to reviewers or included in the review bundle.

## Reviewer Anonymization

Reviewers are already anonymous (R1-R5). No relabeling needed.
Reviewer outputs must not contain identity-revealing language.

## Verification Rules (Governance Tests)

- Anonymization MUST be deterministic (same inputs → same outputs)
- Anonymization MUST remove obvious persona identifiers
- Anonymization MUST preserve substantive content
- Internal mapping MUST be preserved in runtime evidence
- Internal mapping MUST NOT be accessible to reviewers
- All 5 advisors MUST be present in output (no dropping)
- Relabeling MUST be a permutation (bijection)