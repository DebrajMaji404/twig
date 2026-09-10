"""
Comprehensive scaling projection: JSON-pretty vs JSON-min vs TOON-style vs Twig.

Measures actual token counts (tiktoken cl100k_base) at small record counts,
then projects to 1K → 100M token scale to show real-world cost impact.

Covers two workloads:
  1. Dense data  — every field present in every record (Twig's strong suit)
  2. Sparse data — explicit nulls, missing keys, empty lists (harder for Twig)
"""

import json
import itertools
from twig.codec import encode as twig_encode, decode as twig_decode

try:
    import tiktoken
    TOKENIZER = tiktoken.get_encoding("cl100k_base")
    def token_count(text):
        return len(TOKENIZER.encode(text))
    TOKENIZER_NAME = "tiktoken cl100k_base (real GPT tokenizer)"
except ImportError:
    def token_count(text):
        return max(1, len(text) // 4)
    TOKENIZER_NAME = "chars/4 estimate (install tiktoken for exact counts)"


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def make_dense_record(i):
    """Fully populated nested record — no missing fields."""
    return {
        "id": f"usr_{i:05d}",
        "name": f"Person {i}",
        "email": f"person{i}@example.com",
        "age": 25 + (i % 40),
        "active": i % 3 != 0,
        "score": 72.5 + (i % 28),
        "address": {
            "city": "Durgapur",
            "state": "West Bengal",
            "pin": f"{713200 + i % 100}",
        },
        "employment": {
            "company": f"Company {i % 20}",
            "role": "Engineer" if i % 2 else "Analyst",
            "years": i % 15,
        },
        "tags": ["python", "sql", "ml"] if i % 2 else ["java", "spring"],
    }


def make_sparse_record(i):
    """Record with deliberate sparsity: nulls, missing keys, empty lists."""
    record = {
        "id": f"usr_{i:05d}",
        "name": f"Person {i}",
        "email": None if i % 3 == 0 else f"person{i}@example.com",
        "profile": {
            "city": "Durgapur" if i % 2 else None,
            "state": "West Bengal",
            "pin": None if i % 5 == 0 else "713201",
        },
        "employment": {
            "company": "Acme Labs",
            "role": None if i % 4 == 0 else "Engineer",
            "years": i % 12,
        },
        "skills": ["python", None, "sql"] if i % 2 else [],
        "active": i % 7 != 0,
        "score": None if i % 6 == 0 else 87,
        "notes": None,
    }
    if i % 4 == 0:
        record.pop("email")
    if i % 5 == 0:
        record["profile"].pop("pin")
    if i % 6 == 0:
        record.pop("notes")
    return record


# ---------------------------------------------------------------------------
# TOON-style encoder (flat CSV with dotted paths)
# ---------------------------------------------------------------------------

def _flatten_for_toon(record, prefix=""):
    vals = {}
    for k, v in record.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            vals.update(_flatten_for_toon(v, path))
        elif isinstance(v, list):
            vals[path] = "[" + "|".join("null" if x is None else str(x) for x in v) + "]"
        elif v is None:
            vals[path] = "null"
        else:
            vals[path] = str(v)
    return vals


def encode_toon(records):
    cols = []
    rows = []
    for r in records:
        flat = _flatten_for_toon(r)
        rows.append(flat)
        for c in flat:
            if c not in cols:
                cols.append(c)
    lines = [",".join(cols)]
    for row in rows:
        lines.append(",".join(row.get(c, "null") for c in cols))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Measure at real record counts
# ---------------------------------------------------------------------------

def measure(make_record, counts):
    """Returns {count: {format_name: token_count}}."""
    results = {}
    for n in counts:
        recs = [make_record(i) for i in range(n)]

        json_pretty = json.dumps(recs, indent=2, ensure_ascii=False)
        json_min    = json.dumps(recs, separators=(",", ":"), ensure_ascii=False)
        toon_text   = encode_toon(recs)
        twig_text   = twig_encode(recs)

        # Verify round-trip
        assert twig_decode(twig_text) == recs, f"Twig round-trip FAILED at n={n}"

        results[n] = {
            "JSON-pretty": token_count(json_pretty),
            "JSON-min":    token_count(json_min),
            "TOON-style":  token_count(toon_text),
            "Twig":        token_count(twig_text),
        }
    return results


def print_measured(title, results):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"  Tokenizer: {TOKENIZER_NAME}")
    print(f"{'='*80}")
    formats = ["JSON-pretty", "JSON-min", "TOON-style", "Twig"]
    print(f"{'Records':>10} | " + " | ".join(f"{f:>13}" for f in formats))
    print("-" * 72)
    for n, sizes in results.items():
        print(f"{n:>10,} | " + " | ".join(f"{sizes[f]:>13,}" for f in formats))


def print_reductions(results):
    """Print % reduction vs JSON-min at each measured size."""
    formats = ["JSON-pretty", "JSON-min", "TOON-style", "Twig"]
    print(f"\n{'Records':>10} | " + " | ".join(f"{f:>13}" for f in formats))
    print("-" * 72)
    for n, sizes in results.items():
        base = sizes["JSON-min"]
        print(f"{n:>10,} | " + " | ".join(
            f"{(1 - sizes[f]/base)*100:>12.1f}%" for f in formats
        ))


def print_projections(results, max_record_count):
    """Project from the largest measured count to huge scales."""
    base_n = max(results.keys())
    base = results[base_n]
    formats = ["JSON-pretty", "JSON-min", "TOON-style", "Twig"]

    targets = [1_000, 10_000, 100_000, 1_000_000, 10_000_000, 100_000_000]
    targets = [t for t in targets if t >= base_n]

    print(f"\nProjected token counts (linear from {base_n:,}-record measurement)")
    print(f"{'Scale':>14} | " + " | ".join(f"{f:>14}" for f in formats) +
          " | Twig vs JSON-min | Twig vs TOON")
    print("-" * 120)
    for target in targets:
        ratio = target / base_n
        projected = {f: round(base[f] * ratio) for f in formats}
        vs_json = (1 - projected["Twig"] / projected["JSON-min"]) * 100
        vs_toon = (1 - projected["Twig"] / projected["TOON-style"]) * 100
        print(
            f"{target:>14,} | " +
            " | ".join(f"{projected[f]:>14,}" for f in formats) +
            f" |          {vs_json:>5.1f}% |       {vs_toon:>5.1f}%"
        )


def print_cost_estimate(results):
    """Estimate API cost savings at GPT-4o input pricing ($2.50/1M tokens)."""
    base_n = max(results.keys())
    base = results[base_n]
    price_per_m = 2.50  # GPT-4o input $/1M tokens

    print(f"\nEstimated GPT-4o input cost (${price_per_m}/1M tokens)")
    print(f"{'Scale':>14} | {'JSON-min cost':>14} | {'Twig cost':>14} | {'Savings':>14}")
    print("-" * 70)
    for target in [1_000, 10_000, 100_000, 1_000_000, 10_000_000, 100_000_000]:
        if target < base_n:
            continue
        ratio = target / base_n
        json_tokens = round(base["JSON-min"] * ratio)
        twig_tokens = round(base["Twig"] * ratio)
        json_cost = json_tokens * price_per_m / 1_000_000
        twig_cost = twig_tokens * price_per_m / 1_000_000
        savings = json_cost - twig_cost
        print(
            f"{target:>14,} | "
            f"${json_cost:>12,.2f} | "
            f"${twig_cost:>12,.2f} | "
            f"${savings:>12,.2f}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    record_counts = [1, 10, 100, 1_000]

    # ---- Dense workload ----
    print("\n" + "#" * 80)
    print("#  WORKLOAD 1: DENSE DATA (all fields present in every record)")
    print("#" * 80)

    dense = measure(make_dense_record, record_counts)
    print_measured("Dense Data — Measured Token Counts", dense)
    print("\nReduction vs JSON-min:")
    print_reductions(dense)
    print_projections(dense, max(record_counts))
    print_cost_estimate(dense)

    # ---- Sparse workload ----
    print("\n\n" + "#" * 80)
    print("#  WORKLOAD 2: SPARSE DATA (nulls, missing keys, empty lists)")
    print("#" * 80)

    sparse = measure(make_sparse_record, record_counts)
    print_measured("Sparse Data — Measured Token Counts", sparse)
    print("\nReduction vs JSON-min:")
    print_reductions(sparse)
    print_projections(sparse, max(record_counts))
    print_cost_estimate(sparse)

    # ---- Summary ----
    print("\n\n" + "=" * 80)
    print("  SUMMARY at 1,000 records (measured, not projected)")
    print("=" * 80)
    for label, data in [("Dense", dense), ("Sparse", sparse)]:
        d = data[1000]
        twig_vs_json = (1 - d["Twig"] / d["JSON-min"]) * 100
        twig_vs_toon = (1 - d["Twig"] / d["TOON-style"]) * 100
        toon_vs_json = (1 - d["TOON-style"] / d["JSON-min"]) * 100
        print(f"\n  {label} workload:")
        print(f"    Twig vs JSON-min:    {twig_vs_json:>6.2f}% smaller")
        print(f"    TOON vs JSON-min:    {toon_vs_json:>6.2f}% smaller")
        print(f"    Twig vs TOON-style:  {twig_vs_toon:>6.2f}% {'smaller' if twig_vs_toon > 0 else 'larger'}")

    print("\n\nAll round-trip checks: PASSED")
    print(f"Tokenizer: {TOKENIZER_NAME}")
