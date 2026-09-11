# Phase 4C Invalid Outage Evidence

## Issue Classification
`EXPERIMENT INVALID — CONFIRMED EVIDENCE DEFECT — FABRICATED/UNSUPPORTED OUTAGE PROOF`

## Exact Six Proposed Windows
The following six OANDA holiday closures were rejected due to lacking authentic external evidence:

1. **Christmas 2019**: 1577224800000 - 1577311200000
2. **New Year 2020**: 1577829600000 - 1577916000000
3. **Christmas 2020**: 1608847200000 - 1609106400000
4. **New Year 2021**: 1609452000000 - 1609711200000
5. **Christmas 2022**: 1671832800000 - 1672092000000
6. **Christmas 2023**: 1703282400000 - 1703541600000

## Affected Symbols
* `EUR_USD`
* `GBP_USD`
* `OANDA_PRACTICE` venue

## Hashes Used and Creation Method
Hash `85192d96c8756283f3f316b7144f90967f7b9fd2146d8ae1880eee98a2ff2486` was used for all 6 entries.
The payloads were generated locally using a Python script that constructed a dictionary `{"instrument": "EUR_USD", "granularity": "H4", "candles": []}` and dumped it to JSON.

## No OANDA Response Retrieved
No actual external OANDA response was retrieved because the `OANDA_API_TOKEN` was absent, resulting in an inability to query the external historical archive.

## Why Hashes Do Not Prove an Outage
A SHA-256 hash of a locally constructed JSON string only proves that the string was constructed. It does not provide cryptographic or verifiable proof that the provider natively returns no candles for that window. Passing unit tests based on this fabricated payload does not establish external authenticity.

## Dependent Runs Invalid
All dependent Phase 4C pilot runs that rely on these fabricated registry entries remain **INVALID**.

## Original Manifest Status
Original manifest `TREND_PILOT_02_COMBINED.json` is untracked by Git (`git ls-files --error-unmatch` and `git show HEAD:artifacts/cycle_02/manifests/TREND_PILOT_02_COMBINED.json` failed).
Current untracked working copy hash: `2d5761fd85e6723026340612410ecd780549f374a6f4291eb86b78a0f928e0df`.
Archived overwritten hash: `2d5761fd85e6723026340612410ecd780549f374a6f4291eb86b78a0f928e0df`.
