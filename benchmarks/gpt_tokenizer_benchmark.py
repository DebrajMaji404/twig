import json
import yaml
from xml.sax.saxutils import escape as xml_escape
import tiktoken
from twig.codec import encode as twig_encode

enc = tiktoken.get_encoding("cl100k_base")


def toks(s: str) -> int:
    return len(enc.encode(s))


def make_person(i):
    return {
        "name": f"person{i}",
        "address": {
            "present": {"state": "West Bengal", "district": "Paschim Bardhaman", "block": f"Block-{i % 9 + 1}", "landmark": "near temple", "pin": "713201"},
            "permanent": {"state": "Bihar", "district": "Patna", "block": f"Block-{i % 7 + 1}", "landmark": "near market", "pin": "800001"},
        },
        "experience": [
            {"companyName": "Tata Steel", "role": "Engineer", "years": 2, "state": "Jharkhand", "district": "East Singhbhum", "block": "Block-9", "landmark": "near river"},
            {"companyName": "Infosys", "role": "Developer", "years": 3, "state": "Karnataka", "district": "Bangalore Urban", "block": "Block-1", "landmark": "near lake"},
        ],
    }


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


def run_benchmark():
    print("Real GPT tokenizer benchmark using tiktoken cl100k_base")
    print(f"{'N':>4} | {'JSON-min':>10} | {'JSON-pretty':>12} | {'XML':>8} | {'YAML':>8} | {'TOON-style':>10} | {'Twig':>8}")
    print("-" * 80)

    rows = []
    for n in [1, 10, 100, 1000]:
        data = [make_person(i) for i in range(n)]
        json_min = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        json_pretty = json.dumps(data, indent=2, ensure_ascii=False)
        xml_str = records_to_xml(data)
        yaml_str = yaml.dump(data, allow_unicode=True, sort_keys=False)
        toon_str = toon_encode(data)
        twig_str = twig_encode(data)
        rows.append({
            "n": n,
            "json_min": toks(json_min),
            "json_pretty": toks(json_pretty),
            "xml": toks(xml_str),
            "yaml": toks(yaml_str),
            "toon": toks(toon_str),
            "twig": toks(twig_str),
        })

    for r in rows:
        print(f"{r['n']:>4} | {r['json_min']:>10} | {r['json_pretty']:>12} | {r['xml']:>8} | "
              f"{r['yaml']:>8} | {r['toon']:>10} | {r['twig']:>8}")

    last = rows[-1]
    print(f"\n--- reduction vs JSON-min at n={last['n']} ---")
    for fmt in ("json_pretty", "xml", "yaml", "toon", "twig"):
        red = (1 - last[fmt] / last["json_min"]) * 100
        label = {"json_pretty": "JSON (pretty)", "xml": "XML", "yaml": "YAML",
                  "toon": "TOON-style", "twig": "Twig"}[fmt]
        print(f"{label:>15}: {red:.1f}% ({'smaller' if red > 0 else 'larger'} than JSON-min)")

    print("\n--- linear projection to large payloads (based on n=1000 observed rate) ---")
    base_n = 1000
    base_data = [make_person(i) for i in range(base_n)]
    base_json = toks(json.dumps(base_data, separators=(",", ":"), ensure_ascii=False))
    base_twig = toks(twig_encode(base_data))
    print(f"Observed at n=1000: JSON={base_json}, Twig={base_twig}, reduction={(1-base_twig/base_json)*100:.2f}%")
    for target_n in [1000, 10000, 100000, 1000000, 10000000, 100000000]:
        est_json = int(round((base_json / base_n) * target_n))
        est_twig = int(round((base_twig / base_n) * target_n))
        red = (1 - est_twig / est_json) * 100
        print(f"target_n={target_n:>9,} | est_JSON={est_json:>13,} | est_Twig={est_twig:>13,} | reduction={red:>7.2f}%")


if __name__ == "__main__":
    run_benchmark()
