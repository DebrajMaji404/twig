"""
Full report: depth 1-50, using the ACTUAL production codec (codec.py),
not a simplified stand-in. At each depth, records are genuinely complex --
not just a unary chain of dicts, but with sibling fields growing per level
AND array-of-dicts fields injected periodically (every 5 levels), so deep
nesting is tested together with the array/child-table machinery, not
nesting alone.
"""

import json
import random
import time
from twig.codec import encode, decode

random.seed(11)


def build_nested(depth: int, breadth: int, rec_idx: int, cur=1):
    """
    Recursively builds one record nested `depth` levels deep. Each level
    adds `breadth * level` sibling scalar fields. Every 5th level also
    injects a small array-of-dicts field (2 items, each with 2 scalar
    fields) to keep the structure genuinely complex, not just deep.
    """
    node = {}
    for j in range(breadth * cur):
        node[f"f{cur}_{j}"] = f"v_{cur}_{j}_{rec_idx}"

    if cur % 5 == 0:
        node[f"arr{cur}"] = [
            {"itemName": f"item_{cur}_{k}_{rec_idx}", "itemVal": k * cur}
            for k in range(2)
        ]

    if cur < depth:
        node[f"level{cur+1}"] = build_nested(depth, breadth, rec_idx, cur + 1)

    return node


def toks(s: str) -> int:
    return max(1, round(len(s) / 4))


N_RECORDS = 5           # records per depth (kept modest x50 depths = still a lot of work)
BREADTH = 1              # sibling fields per level (kept small so depth 50 stays tractable)

results = []
t0 = time.time()

for depth in range(1, 51):
    records = [build_nested(depth, BREADTH, i) for i in range(N_RECORDS)]

    json_str = json.dumps(records)
    json_tok = toks(json_str)

    try:
        encoded = encode(records)
        decoded = decode(encoded)
        ok = decoded == records
        err = None
    except Exception as e:
        encoded = ""
        ok = False
        err = f"{type(e).__name__}: {e}"

    compact_tok = toks(encoded) if encoded else None
    reduction = (1 - compact_tok / json_tok) * 100 if compact_tok else None

    results.append({
        "depth": depth,
        "json_tok": json_tok,
        "compact_tok": compact_tok,
        "reduction": reduction,
        "roundtrip_ok": ok,
        "error": err,
    })

elapsed = time.time() - t0

# --- write full report ---
n_pass = sum(1 for r in results if r["roundtrip_ok"])
n_fail = len(results) - n_pass

lines = []
lines.append("# Depth 1-50 Full Report\n")
lines.append(f"Records per depth: {N_RECORDS} | Sibling fields per level: {BREADTH} | "
              f"Array field injected every 5th level (2 items)\n")
lines.append(f"Round-trip: **{n_pass}/50 PASS**, {n_fail}/50 FAIL\n")
lines.append(f"Generated + tested in {elapsed:.1f}s\n")
lines.append("\n| Depth | JSON tok | Compact tok | Reduction | Round-trip |")
lines.append("|---|---|---|---|---|")
for r in results:
    ct = r["compact_tok"] if r["compact_tok"] is not None else "-"
    red = f"{r['reduction']:.1f}%" if r["reduction"] is not None else "-"
    status = "PASS" if r["roundtrip_ok"] else f"**FAIL** ({r['error']})" if r["error"] else "**FAIL**"
    lines.append(f"| {r['depth']} | {r['json_tok']} | {ct} | {red} | {status} |")

report = "\n".join(lines)
with open("depth_report_1_50.md", "w", encoding="utf-8") as f:
    f.write(report)

print(f"PASS: {n_pass}/50   FAIL: {n_fail}/50")
print(f"Elapsed: {elapsed:.1f}s")
print()

# print first failure in detail, if any
first_fail = next((r for r in results if not r["roundtrip_ok"]), None)
if first_fail:
    print(f"First failure at depth={first_fail['depth']}")
    if first_fail["error"]:
        print(f"  Error: {first_fail['error']}")
    else:
        print("  (silent mismatch, not an exception -- data corrupted without error)")

print("\nSaved full table -> depth_report_1_50.md")
