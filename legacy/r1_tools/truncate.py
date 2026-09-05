with open("tools/run_trend_backtest.py", "r") as f:
    content = f.read()

idx = content.find('if __name__ == "__main__":\n    main()')
if idx != -1:
    content = content[:idx + len('if __name__ == "__main__":\n    main()')] + "\n"

with open("tools/run_trend_backtest.py", "w") as f:
    f.write(content)
