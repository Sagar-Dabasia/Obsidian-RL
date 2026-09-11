import json
import re

transcript_path = r"C:\Users\Sagar Patel\.gemini\antigravity-ide\brain\8bb63e9d-227f-4828-8ba9-ba3753fa1894\.system_generated\logs\transcript_full.jsonl"

found = []
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if data.get("type") == "TOOL_RESPONSE" and "write_to_file" in str(data):
            content = str(data)
            if "run_trend_backtest" in content:
                found.append(content)
        if data.get("type") == "PLANNER_RESPONSE" and "CodeContent" in str(data) and "run_trend_backtest" in str(data):
            found.append(str(data))

with open("found_replacements.txt", "w", encoding="utf-8") as out:
    for c in found:
        out.write(c + "\n\n=====\n\n")
