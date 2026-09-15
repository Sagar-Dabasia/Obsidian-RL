import os
import re

path = "tests/evaluation/test_trend_backtest.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix mock parse_args in test_cli_boundaries
old_mock_parse = """    def mock_parse_args(*args, **kwargs):
        res = orig_parse_args(*args, **kwargs)
        parsed_args_capture.append(res)
        return res"""

new_mock_parse = """    def mock_parse_args(*args, **kwargs):
        import sys
        sys.argv.extend(["--market-model", "PERPETUAL", "--exposure-policy", "BIDIRECTIONAL"])
        res = orig_parse_args(*args, **kwargs)
        parsed_args_capture.append(res)
        return res"""

content = content.replace(old_mock_parse, new_mock_parse)

# Fix test_manifest_*
def _replace_manifest_test(content, func_name):
    # we need to insert `p = "man.json"; import json; json.dump(manifest, open(p, "w"))` 
    # instead of `p` being undefined.
    return re.sub(
        r'        with pytest.raises\(ValueError, match="(.*?)"\):\n            load_and_validate_manifest\(str\(p\), (.*?)\)',
        r'        p = "man.json"\n        import json\n        with open(p, "w") as f: json.dump(manifest, f)\n        with pytest.raises(ValueError, match="\1"):\n            load_and_validate_manifest(p, \2)',
        content
    )

content = _replace_manifest_test(content, "test_manifest_duplicate_exact_match_rejected")
content = _replace_manifest_test(content, "test_manifest_wrong_identity_rejected")
content = _replace_manifest_test(content, "test_manifest_malformed_values_rejected")
content = _replace_manifest_test(content, "test_runtime_bounds_count_and_digest_rejected")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
