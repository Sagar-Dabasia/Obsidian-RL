import json

transcript_path = r"C:\Users\Sagar Patel\.gemini\antigravity-ide\brain\8bb63e9d-227f-4828-8ba9-ba3753fa1894\.system_generated\logs\transcript_full.jsonl"

found = []
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if data.get("type") == "PLANNER_RESPONSE":
            content = str(data)
            if "run_trend_backtest.py" in content and "multi_replace_file_content" in content:
                found.append(content)

with open("found_replacements.txt", "w", encoding="utf-8") as out:
    for c in found:
        out.write(c + "\n\n=====\n\n")
