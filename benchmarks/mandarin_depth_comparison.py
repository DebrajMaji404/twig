"""
Depth 1-50 comparison, but with Mandarin (Chinese) text as the actual
field VALUES (not just ASCII placeholders), since CJK text tokenizes very
differently from English in real BPE tokenizers -- commonly close to
1 token per character, not ~4 chars/token like Latin script. Using a flat
chars/4 estimate across the board (as done in earlier benchmarks) would
badly misrepresent savings once real Chinese content is involved, so this
uses a CJK-aware estimate instead:

    - CJK characters (U+4E00-U+9FFF and common extensions): ~1 token each
    - everything else (structure, delimiters, digits, ASCII keys): ~4 chars/token

This is STILL an approximation, not a real tokenizer call (same network
restriction as before -- tiktoken's vocab file is outside this sandbox's
allowlist). The CJK-per-char rate is a commonly-cited rule of thumb for
GPT-style tokenizers on common Chinese characters, not a guarantee for
this specific dataset's vocabulary.
"""

import json
import random
from twig.codec import encode, decode

random.seed(23)

# common Mandarin words/phrases to use as realistic field VALUES
MANDARIN_WORDS = [
    "北京", "上海", "广州", "深圳", "杭州",       # cities
    "工程师", "经理", "设计师", "分析师",           # roles
    "科技公司", "银行", "医院", "大学",             # org types
    "你好", "谢谢", "再见", "欢迎",                # common phrases
    "产品", "服务", "质量", "价格", "客户",         # business terms
    "北京市朝阳区建国路", "上海市浦东新区世纪大道",   # longer address-like strings
]


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def cjk_aware_tokens(s: str) -> int:
    cjk_count = sum(1 for ch in s if _is_cjk(ch))
    other_count = len(s) - cjk_count
    return max(1, cjk_count + round(other_count / 4))


def build_nested_mandarin(depth: int, breadth: int, rec_idx: int, cur=1):
    node = {}
    for j in range(breadth * cur):
        node[f"f{cur}_{j}"] = random.choice(MANDARIN_WORDS)

    if cur % 5 == 0:
        node[f"arr{cur}"] = [
            {"itemName": random.choice(MANDARIN_WORDS), "itemVal": k * cur}
            for k in range(2)
        ]

    if cur < depth:
        node[f"level{cur+1}"] = build_nested_mandarin(depth, breadth, rec_idx, cur + 1)

    return node


N_RECORDS = 5
BREADTH = 1

results = []
for depth in range(1, 51):
    records = [build_nested_mandarin(depth, BREADTH, i) for i in range(N_RECORDS)]

    json_str = json.dumps(records, ensure_ascii=False)
    json_tok = cjk_aware_tokens(json_str)

    encoded = encode(records)
    decoded = decode(encoded)
    ok = decoded == records
    compact_tok = cjk_aware_tokens(encoded)

    reduction = (1 - compact_tok / json_tok) * 100
    results.append((depth, json_tok, compact_tok, reduction, ok))

n_pass = sum(1 for r in results if r[4])
print(f"Round-trip: {n_pass}/50 PASS\n")

print(f"{'Depth':>5} | {'JSON tok':>9} | {'Twig tok':>9} | {'Reduction':>10} | {'RT':>4}")
print("-" * 55)
for depth, jt, ct, red, ok in results:
    if depth in (1, 2, 3, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50):
        print(f"{depth:>5} | {jt:>9} | {ct:>9} | {red:>9.1f}% | {'OK' if ok else 'FAIL':>4}")

avg_reduction = sum(r[3] for r in results) / len(results)
print(f"\nAverage reduction across all 50 depths: {avg_reduction:.1f}%")

# save full report + a sample of the actual encoded output
with open("mandarin_depth_report.md", "w", encoding="utf-8") as f:
    f.write("# Twig vs JSON: Depth 1-50 with Mandarin (Chinese) field values\n\n")
    f.write(f"Round-trip: **{n_pass}/50 PASS**\n\n")
    f.write("Token estimate: CJK characters counted ~1 token each, "
            "everything else ~4 chars/token (not a real tokenizer call -- "
            "see script docstring for why).\n\n")
    f.write("| Depth | JSON tokens | Twig tokens | Reduction | Round-trip |\n")
    f.write("|---|---|---|---|---|\n")
    for depth, jt, ct, red, ok in results:
        f.write(f"| {depth} | {jt} | {ct} | {red:.1f}% | {'PASS' if ok else 'FAIL'} |\n")
    f.write(f"\nAverage reduction across all 50 depths: {avg_reduction:.1f}%\n")

print("\nSaved -> mandarin_depth_report.md")

# show one real sample so it's inspectable, not just numbers
sample = [build_nested_mandarin(3, BREADTH, i) for i in range(2)]
print("\n--- sample at depth=3 ---")
print("\nJSON:")
print(json.dumps(sample, ensure_ascii=False, indent=2)[:600])
print("\nTwig:")
print(encode(sample))
