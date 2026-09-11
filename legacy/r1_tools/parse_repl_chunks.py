import json

with open("found_replacements.txt", "r", encoding="utf-8") as f:
    text = f.read()

parts = text.split("=====\n\n")
with open("out3.txt", "w", encoding="utf-8") as out:
    for idx, part in enumerate(parts):
        if not part.strip(): continue
        try:
            part = part.replace("'", '"')
            part = part.replace("True", "true").replace("False", "false").replace("None", "null")
            data = json.loads(part)
            if 'tool_calls' in data:
                for tc in data['tool_calls']:
                    args = tc.get('args', {})
                    if 'ReplacementChunks' in args:
                        for chunk in args['ReplacementChunks']:
                            out.write(f"--- MATCH {idx} ReplacementChunk ---\n")
                            out.write(chunk.get("ReplacementContent") + "\n")
        except Exception as e:
            pass
