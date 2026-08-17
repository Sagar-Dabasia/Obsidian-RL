import json

with open("found_replacements.txt", "r", encoding="utf-8") as f:
    text = f.read()

parts = text.split("=====\n\n")
for idx, part in enumerate(parts):
    if not part.strip(): continue
    try:
        # replace single quotes with double quotes? The string represents a python dict.
        data = eval(part)
        if 'tool_calls' in data:
            for tc in data['tool_calls']:
                args = tc.get('args', {})
                if 'CodeContent' in args:
                    print(f"--- MATCH {idx} CodeContent ---")
                    print(args['CodeContent'])
                if 'ReplacementChunks' in args:
                    print(f"--- MATCH {idx} ReplacementChunks ---")
                    print(args['ReplacementChunks'])
    except Exception as e:
        print(f"Failed to parse block {idx}: {e}")
