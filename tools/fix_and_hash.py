import sys
import hashlib

files = [
    'docs/cycle_02/research/CYCLE_02_RESEARCH_REGISTER.md',
    'src/obsidian_rl/data/historical_dataset.py',
    'tests/data/test_outages.py',
    'tools/run_trend_backtest.py',
    'tools/verify_binance_outage.py'
]

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        lines = file.read().splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    with open(f, 'w', encoding='utf-8', newline='\n') as file:
        file.write('\n'.join(line.rstrip() for line in lines) + '\n')

hash_files = [
    'docs/cycle_02/research/PHASE_04D_CRYPTO_TREND_ROBUSTNESS_PLAN.md',
    'docs/cycle_02/reports/PHASE_04D_CRYPTO_TREND_ROBUSTNESS.md',
    'artifacts/cycle_02/results/PHASE_4D_0a70bdb7_7b86b57f.json',
    'artifacts/cycle_02/manifests/PHASE_4D_PROVENANCE_BTCUSDT.json',
    'artifacts/cycle_02/manifests/PHASE_4D_PROVENANCE_ETHUSDT.json'
]

for hf in hash_files:
    with open(hf, 'rb') as file:
        file_hash = hashlib.sha256(file.read()).hexdigest()
    print(f"{hf}: {file_hash}")
