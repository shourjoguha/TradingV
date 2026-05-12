import json, sys
# Read the JSON output from playwright (saved manually below)
data = sys.stdin.read()
# Strip wrapping quotes if present
if data.startswith('"') and data.rstrip().endswith('"'):
    data = data.strip()[1:-1]
data = data.encode().decode('unicode_escape')
parsed = json.loads(data)
out_path = "/Users/shourjosmac/Documents/Claude/TradingView /.scratch/gekko/trailblazers.json"
with open(out_path, "w") as f:
    json.dump(parsed, f, indent=2)
print(f"saved {len(parsed)} funds -> {out_path}")
non_empty = [k for k,v in parsed.items() if v]
print(f"non-empty: {len(non_empty)}")
