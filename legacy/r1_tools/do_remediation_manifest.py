import os

path = "src/obsidian_rl/evaluation/trend_backtest.py"
with open(path, "r") as f:
    code = f.read()

# insert the function at the top
manifest_func = """
def parse_and_validate_manifest(
    manifest_data: dict,
    asset_class: str,
    venue: str,
    symbol: str,
    timeframe: str
) -> tuple[str, int]:
    \"\"\"Parse and validate manifest, return (digest, end_timestamp_utc).\"\"\"
    components = manifest_data.get("components")
    if not isinstance(components, list):
        raise ValueError("Manifest component missing or ambiguous")
    
    matches = [
        c for c in components
        if c.get("asset_class") == asset_class
        and c.get("venue") == venue
        and c.get("symbol") == symbol
        and c.get("timeframe") == timeframe
    ]
    if len(matches) != 1:
        raise ValueError("Manifest component missing or ambiguous")
    
    c = matches[0]
    
    start_ts = c.get("start_timestamp_utc")
    end_ts = c.get("end_timestamp_utc")
    row_count = c.get("row_count")
    
    if type(start_ts) is not int or type(end_ts) is not int or type(row_count) is not int:
        raise ValueError("Manifest component missing or ambiguous")
        
    if start_ts >= end_ts or row_count <= 0:
        raise ValueError("Manifest component missing or ambiguous")
        
    digest = c.get("digest")
    import re
    if not isinstance(digest, str) or not re.match(r"^[0-9a-f]{64}$", digest):
        raise ValueError("Manifest digest is malformed")
        
    return digest, end_ts
"""

code = code.replace("from obsidian_rl.portfolio.costs import CostModel\n", 
                    "from obsidian_rl.portfolio.costs import CostModel\n" + manifest_func)
with open(path, "w") as f:
    f.write(code)
