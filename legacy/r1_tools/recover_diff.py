import json
import sys

transcript_path = r"C:\Users\Sagar Patel\.gemini\antigravity-ide\brain\8bb63e9d-227f-4828-8ba9-ba3753fa1894\.system_generated\logs\transcript_full.jsonl"

found_diff = None
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if data.get("type") == "TOOL_RESPONSE" and "git diff" in str(data):
            # Check if this is the large diff
            content = data.get("content", "")
            if "diff --git" in content and len(content) > 10000:
                found_diff = content

if found_diff:
    with open("full_recovered.diff", "w", encoding="utf-8") as out:
        out.write(found_diff)
    print(f"Recovered diff of length {len(found_diff)}")
else:
    print("Diff not found")
