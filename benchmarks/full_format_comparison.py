"""
Full format comparison: JSON (minified + pretty), XML, YAML, a TOON-style
flattener (no parent-pointer tree), and Twig -- all encoding the SAME
dataset, at multiple record counts.

Token counts use a chars/4 approximation (same caveat as every other
benchmark in this project: tiktoken's vocab file is outside this
sandbox's network allowlist, so this is not a real tokenizer call).
Where a format is CJK-heavy, chars/4 underestimates real JSON-family
cost and overestimates Twig's advantage less than you'd think -- see
mandarin_depth_comparison.py for a CJK-aware version of this same idea.

Round-trip correctness is checked for every format that has a standard
decoder available (json, yaml, twig). XML and the TOON-style flattener
here are included for token-size comparison only -- writing a fully
general XML/TOON parser back to the original nested-list-of-dicts shape
is a separate, non-trivial undertaking not attempted here, so those two
are marked "not verified" rather than falsely claimed correct.
"""

import json
import yaml
from xml.sax.saxutils import escape as xml_escape
from twig.codec import encode as twig_encode, decode as twig_decode


def toks(s: str) -> int:
    return max(1, round(len(s) / 4))


def make_person(i):
    return {
        "name": f"person{i}",
        "address": {
            "present": {"state": "West Bengal", "district": "Paschim Bardhaman",
                         "block": f"Block-{i%9+1}", "landmark": "near temple", "pin": "713201"},
            "permanent": {"state": "Bihar", "district": "Patna",
                          "block": f"Block-{i%7+1}", "landmark": "near market", "pin": "800001"},
        },
        "experience": [
            {"companyName": "Tata Steel", "role": "Engineer", "years": 2,
             "state": "Jharkhand", "district": "East Singhbhum",
             "block": "Block-9", "landmark": "near river"},
            {"companyName": "Infosys", "role": "Developer", "years": 3,
             "state": "Karnataka", "district": "Bangalore Urban",
             "block": "Block-1", "landmark": "near lake"},
        ],
    }


# ---------------------------------------------------------------------------
# XML encoder (simple recursive dict -> XML, no external library needed)
# ---------------------------------------------------------------------------

def dict_to_xml(obj, tag="item"):
    if isinstance(obj, dict):
        inner = "".join(dict_to_xml(v, k) for k, v in obj.items())
        return f"<{tag}>{inner}</{tag}>"
    if isinstance(obj, list):
        return "".join(dict_to_xml(item, tag) for item in obj)
    return f"<{tag}>{xml_escape(str(obj))}</{tag}>"


def records_to_xml(records):
    body = "".join(dict_to_xml(r, "record") for r in records)
    return f"<records>{body}</records>"


# ---------------------------------------------------------------------------
# minimal TOON-style flattener (no parent-pointer tree) -- same as the
# earlier comparison script, reused here for consistency
# ---------------------------------------------------------------------------

def toon_flatten(d, prefix=""):
    scalars, lists = {}, {}
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            s, l = toon_flatten(v, path)
            scalars.update(s)
            lists.update(l)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            lists[path] = v
        else:
            scalars[path] = v
    return scalars, lists


def toon_encode(records):
    all_scalar_paths = []
    for r in records:
        sc, _ = toon_flatten(r)
        for k in sc:
            if k not in all_scalar_paths:
                all_scalar_paths.append(k)

    lines = [",".join(all_scalar_paths)]
    for r in records:
        sc, ls = toon_flatten(r)
        vals = [str(sc.get(p, "")) for p in all_scalar_paths]
        lines.append(",".join(vals))
        for lpath, items in ls.items():
            if not items:
                continue
            item_paths = list(items[0].keys())
            lines.append(f"  {lpath}[]: " + ",".join(item_paths))
            for item in items:
                lines.append("    " + ",".join(str(item.get(p, "")) for p in item_paths))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# run the comparison
# ---------------------------------------------------------------------------

RECORD_COUNTS = [1, 2, 5, 10, 25, 50, 100]

rows = []
for n in RECORD_COUNTS:
    data = [make_person(i) for i in range(n)]

    json_min = json.dumps(data)
    json_pretty = json.dumps(data, indent=2)
    xml_str = records_to_xml(data)
    yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False)
    toon_str = toon_encode(data)
    twig_str = twig_encode(data)

    # correctness checks where a standard decoder exists
    json_ok = json.loads(json_min) == data
    yaml_ok = yaml.safe_load(yaml_str) == data
    twig_ok = twig_decode(twig_str) == data

    rows.append({
        "n": n,
        "json_min": toks(json_min),
        "json_pretty": toks(json_pretty),
        "xml": toks(xml_str),
        "yaml": toks(yaml_str),
        "toon": toks(toon_str),
        "twig": toks(twig_str),
        "json_ok": json_ok, "yaml_ok": yaml_ok, "twig_ok": twig_ok,
    })

# --- print table ---
header = f"{'N':>4} | {'JSON-min':>9} | {'JSON-pretty':>11} | {'XML':>7} | {'YAML':>7} | {'TOON-style':>10} | {'Twig':>6}"
print(header)
print("-" * len(header))
for r in rows:
    print(f"{r['n']:>4} | {r['json_min']:>9} | {r['json_pretty']:>11} | {r['xml']:>7} | "
          f"{r['yaml']:>7} | {r['toon']:>10} | {r['twig']:>6}")

print(f"\nRound-trip (where a standard decoder exists): "
      f"JSON {'OK' if all(r['json_ok'] for r in rows) else 'FAIL'}, "
      f"YAML {'OK' if all(r['yaml_ok'] for r in rows) else 'FAIL'}, "
      f"Twig {'OK' if all(r['twig_ok'] for r in rows) else 'FAIL'}")

# --- reduction vs JSON-min, at n=100 ---
last = rows[-1]
print(f"\n--- Reduction vs JSON (minified) at n={last['n']} ---")
for fmt in ("json_pretty", "xml", "yaml", "toon", "twig"):
    red = (1 - last[fmt] / last["json_min"]) * 100
    label = {"json_pretty": "JSON (pretty)", "xml": "XML", "yaml": "YAML",
              "toon": "TOON-style", "twig": "Twig"}[fmt]
    sign = "smaller" if red > 0 else "LARGER"
    print(f"{label:>15}: {abs(red):>5.1f}% {sign}")

# --- save full report ---
with open("full_format_comparison.md", "w", encoding="utf-8") as f:
    f.write("# Full format comparison: JSON, XML, YAML, TOON-style, Twig\n\n")
    f.write("Token estimate: chars/4 approximation (no real tokenizer access "
            "in this sandbox -- see script docstring).\n\n")
    f.write(f"Round-trip: JSON {'PASS' if all(r['json_ok'] for r in rows) else 'FAIL'}, "
            f"YAML {'PASS' if all(r['yaml_ok'] for r in rows) else 'FAIL'}, "
            f"Twig {'PASS' if all(r['twig_ok'] for r in rows) else 'FAIL'} "
            f"(XML and TOON-style not round-trip tested -- token-size comparison only)\n\n")
    f.write("| N | JSON-min | JSON-pretty | XML | YAML | TOON-style | Twig |\n")
    f.write("|---|---|---|---|---|---|---|\n")
    for r in rows:
        f.write(f"| {r['n']} | {r['json_min']} | {r['json_pretty']} | {r['xml']} | "
                f"{r['yaml']} | {r['toon']} | {r['twig']} |\n")
    f.write(f"\n## Reduction vs JSON (minified) at n={last['n']}\n\n")
    for fmt in ("json_pretty", "xml", "yaml", "toon", "twig"):
        red = (1 - last[fmt] / last["json_min"]) * 100
        label = {"json_pretty": "JSON (pretty)", "xml": "XML", "yaml": "YAML",
                  "toon": "TOON-style", "twig": "Twig"}[fmt]
        f.write(f"- {label}: {red:.1f}% ({'smaller' if red > 0 else 'larger'} than JSON-min)\n")

    f.write("\n## Sample output at n=1\n\n")
    sample = [make_person(0)]
    f.write("### JSON (minified)\n```json\n" + json.dumps(sample) + "\n```\n\n")
    f.write("### XML\n```xml\n" + records_to_xml(sample) + "\n```\n\n")
    f.write("### YAML\n```yaml\n" + yaml.dump(sample, allow_unicode=True, sort_keys=False) + "```\n\n")
    f.write("### TOON-style\n```\n" + toon_encode(sample) + "\n```\n\n")
    f.write("### Twig\n```\n" + twig_encode(sample) + "\n```\n")

print("\nSaved -> full_format_comparison.md")
