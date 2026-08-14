import json
import sys

transcript_path = r"C:\Users\Sagar Patel\.gemini\antigravity-ide\brain\8bb63e9d-227f-4828-8ba9-ba3753fa1894\.system_generated\logs\transcript_full.jsonl"

found_diff = None
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        if data.get("type") == "TOOL_RESPONSE":
            content = str(data.get("content", ""))
            if "diff --git" in content and len(content) > 5000:
                found_diff = content
                # Don't break, we want the LAST one (which was the full git diff I ran at the start of this turn)

if found_diff:
    import ast
    # The content is typically stringified JSON, so let's extract the actual output text if we can.
    # Actually, it's a list of tool responses, so data["content"] might be a string.
    try:
        parsed = json.loads(found_diff)
        if isinstance(parsed, list) and len(parsed) > 0 and "output" in parsed[0]:
            out_text = parsed[0]["output"]
        else:
            out_text = found_diff
    except:
        out_text = found_diff

    # Sometimes output string starts with 'Created At... The command completed successfully... Output:\n'
    if "Output:\n" in out_text:
        out_text = out_text.split("Output:\n", 1)[1]

    with open("full_recovered.diff", "w", encoding="utf-8") as out:
        out.write(out_text)
    print(f"Recovered diff of length {len(out_text)}")
else:
    print("Diff not found")
