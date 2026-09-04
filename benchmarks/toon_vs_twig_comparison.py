"""
3-way comparison across depth 1-50:
  A) TOON-style encoding (plain dot-notation flatten, NO parent-pointer
     tree -- this is the key architectural difference from Twig) + Mandarin data
  B) Twig (parent-pointer tree) + English data
  C) Twig (parent-pointer tree) + Mandarin data

This isolates two variables at once: format (TOON-style vs Twig) and
language (English vs Mandarin), using the SAME underlying data shape for
all three so the comparison is fair.

TOON-style encoder here is a minimal, faithful reimplementation of the
core idea (flatten nested keys into dotted paths, declare the header
once, then rows) -- not the actual TOON library/spec, just enough to
demonstrate the difference the parent-pointer tree makes. Real TOON may
have additional optimizations not reproduced here.
"""

import json
import random
from twig.codec import encode as twig_encode, decode as twig_decode

random.seed(23)

MANDARIN_WORDS = [
    "北京", "上海", "广州", "深圳", "杭州",
    "工程师", "经理", "设计师", "分析师",
    "科技公司", "银行", "医院", "大学",
    "你好", "谢谢", "再见", "欢迎",
    "产品", "服务", "质量", "价格", "客户",
    "北京市朝阳区建国路", "上海市浦东新区世纪大道",
]

ENGLISH_WORDS = [
    "Beijing", "Shanghai", "Guangzhou", "Shenzhen", "Hangzhou",
    "Engineer", "Manager", "Designer", "Analyst",
    "Tech Company", "Bank", "Hospital", "University",
    "Hello", "Thanks", "Goodbye", "Welcome",
    "Product", "Service", "Quality", "Price", "Customer",
    "123 Main Street", "45 Century Avenue",
]


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def cjk_aware_tokens(s: str) -> int:
    cjk_count = sum(1 for ch in s if _is_cjk(ch))
    other_count = len(s) - cjk_count
    return max(1, cjk_count + round(other_count / 4))


def build_nested(depth: int, breadth: int, rec_idx: int, words: list, cur=1):
    node = {}
    for j in range(breadth * cur):
        node[f"f{cur}_{j}"] = random.choice(words)
    if cur % 5 == 0:
        node[f"arr{cur}"] = [
            {"itemName": random.choice(words), "itemVal": k * cur}
            for k in range(2)
        ]
    if cur < depth:
        node[f"level{cur+1}"] = build_nested(depth, breadth, rec_idx, words, cur + 1)
    return node


# ---------------------------------------------------------------------------
# minimal TOON-style encoder: dot-path flatten, NO parent-pointer tree,
# arrays-of-dicts flattened as an inline nested table under their parent
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

    lines = [",".join(all_scalar_paths)]  # header row: FULL dotted paths, every time
    for r in records:
        sc, ls = toon_flatten(r)
        vals = [str(sc.get(p, "")) for p in all_scalar_paths]
        lines.append(",".join(vals))
        # nested arrays: flatten inline as their own mini-table per record
        for lpath, items in ls.items():
            if not items:
                continue
            item_paths = list(items[0].keys())
            lines.append(f"  {lpath}[]: " + ",".join(item_paths))
            for item in items:
                lines.append("    " + ",".join(str(item.get(p, "")) for p in item_paths))
    return "\n".join(lines)


N_RECORDS = 5
BREADTH = 1
DEPTHS_TO_SHOW = [1, 2, 3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]

rows = []
for depth in range(1, 51):
    mandarin_records = [build_nested(depth, BREADTH, i, MANDARIN_WORDS) for i in range(N_RECORDS)]
    random.seed(23)  # reset so English uses the exact same structural randomness
    english_records = [build_nested(depth, BREADTH, i, ENGLISH_WORDS) for i in range(N_RECORDS)]
    random.seed(23 + depth)  # advance seed differently per depth for next iteration variety

    # A) TOON-style + Mandarin
    toon_mandarin = toon_encode(mandarin_records)
    toon_mandarin_tok = cjk_aware_tokens(toon_mandarin)

    # B) Twig + English
    twig_english = twig_encode(english_records)
    twig_english_tok = cjk_aware_tokens(twig_english)

    # C) Twig + Mandarin
    twig_mandarin = twig_encode(mandarin_records)
    twig_mandarin_tok = cjk_aware_tokens(twig_mandarin)

    json_mandarin_tok = cjk_aware_tokens(json.dumps(mandarin_records, ensure_ascii=False))
    json_english_tok = cjk_aware_tokens(json.dumps(english_records, ensure_ascii=False))

    # correctness check for twig only (toon-style here is lossy/demo-only, not decoded)
    twig_mandarin_ok = twig_decode(twig_mandarin) == mandarin_records
    twig_english_ok = twig_decode(twig_english) == english_records

    rows.append({
        "depth": depth,
        "json_mandarin": json_mandarin_tok,
        "json_english": json_english_tok,
        "toon_mandarin": toon_mandarin_tok,
        "twig_english": twig_english_tok,
        "twig_mandarin": twig_mandarin_tok,
        "twig_mandarin_ok": twig_mandarin_ok,
        "twig_english_ok": twig_english_ok,
    })

print(f"{'Depth':>5} | {'JSON(en)':>8} | {'JSON(zh)':>8} | {'TOON-zh':>8} | {'Twig-en':>8} | {'Twig-zh':>8} | {'RT':>4}")
print("-" * 70)
for r in rows:
    if r["depth"] in DEPTHS_TO_SHOW:
        rt = "OK" if (r["twig_mandarin_ok"] and r["twig_english_ok"]) else "FAIL"
        print(f"{r['depth']:>5} | {r['json_english']:>8} | {r['json_mandarin']:>8} | "
              f"{r['toon_mandarin']:>8} | {r['twig_english']:>8} | {r['twig_mandarin']:>8} | {rt:>4}")

# reduction percentages at depth 50 specifically
last = rows[-1]
print(f"\n--- Reduction vs JSON at depth 50 ---")
print(f"TOON-style + Mandarin: {(1 - last['toon_mandarin']/last['json_mandarin'])*100:.1f}%")
print(f"Twig + English:        {(1 - last['twig_english']/last['json_english'])*100:.1f}%")
print(f"Twig + Mandarin:       {(1 - last['twig_mandarin']/last['json_mandarin'])*100:.1f}%")

# save full report
with open("toon_vs_twig_mandarin_english.md", "w", encoding="utf-8") as f:
    f.write("# TOON-style vs Twig, Mandarin vs English -- Depth 1-50\n\n")
    f.write("Token estimate: CJK chars ~1 token each, everything else ~4 chars/token "
            "(approximation -- see script docstring; no real tokenizer access in this sandbox).\n\n")
    f.write("TOON-style = plain dot-path flatten, header once, rows after -- "
            "NO parent-pointer tree (that's Twig's distinguishing feature).\n\n")
    f.write("| Depth | JSON(en) | JSON(zh) | TOON-style+zh | Twig+en | Twig+zh |\n")
    f.write("|---|---|---|---|---|---|\n")
    for r in rows:
        f.write(f"| {r['depth']} | {r['json_english']} | {r['json_mandarin']} | "
                f"{r['toon_mandarin']} | {r['twig_english']} | {r['twig_mandarin']} |\n")
    f.write(f"\n## Reduction vs same-language JSON at depth 50\n\n")
    f.write(f"- TOON-style + Mandarin: {(1 - last['toon_mandarin']/last['json_mandarin'])*100:.1f}%\n")
    f.write(f"- Twig + English: {(1 - last['twig_english']/last['json_english'])*100:.1f}%\n")
    f.write(f"- Twig + Mandarin: {(1 - last['twig_mandarin']/last['json_mandarin'])*100:.1f}%\n")

print("\nSaved -> toon_vs_twig_mandarin_english.md")
