with open('tools/run_trend_backtest.py', 'r') as f:
    content = f.read()

content = content.replace('print("Backtest completed.\n")', 'print("Backtest completed.\\n")')
content = content.replace('print("\n\n--- AUDIT DATA ---")', 'print("\\n\\n--- AUDIT DATA ---")')

with open('tools/run_trend_backtest.py', 'w') as f:
    f.write(content)
