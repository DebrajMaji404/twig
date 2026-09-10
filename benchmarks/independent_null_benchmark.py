import csv
import io
import json
from xml.sax.saxutils import escape as xml_escape

import tiktoken
import yaml

from twig.codec import decode as twig_decode
from twig.codec import encode as twig_encode

ENCODING = "cl100k_base"
TOKENIZER = tiktoken.get_encoding(ENCODING)


def token_count(text):
    return len(TOKENIZER.encode(text))


def make_record(index):
    record = {
        "id": f"usr_{index:05d}",
        "name": f"Person {index}",
        "email": None if index % 3 == 0 else f"person{index}@example.com",
        "profile": {
            "city": "Durgapur" if index % 2 else None,
            "state": "West Bengal",
            "pin": None if index % 5 == 0 else "713201",
        },
        "employment": {
            "company": "Acme Labs",
            "role": None if index % 4 == 0 else "Engineer",
            "years": index % 12,
        },
        "skills": ["python", None, "sql"] if index % 2 else [],
        "active": index % 7 != 0,
        "score": None if index % 6 == 0 else 87,
        "notes": None,
    }
    if index % 4 == 0:
        record.pop("email")
    if index % 5 == 0:
        record["profile"].pop("pin")
    if index % 6 == 0:
        record.pop("notes")
    return record


def xml_value(value, tag):
    if value is None:
        return f"<{tag} null=\"true\"></{tag}>"
    if isinstance(value, dict):
        inner = "".join(xml_value(child, key) for key, child in value.items())
        return f"<{tag}>{inner}</{tag}>"
    if isinstance(value, list):
        inner = "".join(xml_value(child, "item") for child in value)
        return f"<{tag}>{inner}</{tag}>"
    return f"<{tag}>{xml_escape(str(value))}</{tag}>"


def encode_xml(records):
    return "<records>" + "".join(xml_value(record, "record") for record in records) + "</records>"


def flatten_record(record, prefix=""):
    values = {}
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            values.update(flatten_record(value, path))
        elif isinstance(value, list):
            values[path] = "[" + "|".join("null" if item is None else str(item) for item in value) + "]"
        elif value is None:
            values[path] = "null"
        else:
            values[path] = str(value)
    return values


def encode_toon(records):
    columns = []
    rows = []
    for record in records:
        flattened = flatten_record(record)
        rows.append(flattened)
        for column in flattened:
            if column not in columns:
                columns.append(column)
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(row.get(column, "null") for column in columns))
    return "\n".join(lines)


def encode_csv(records):
    flattened = [flatten_record(record) for record in records]
    columns = []
    for row in flattened:
        for column in row:
            if column not in columns:
                columns.append(column)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for row in flattened:
        writer.writerow([row.get(column, "null") for column in columns])
    return output.getvalue().rstrip("\n")


def format_payloads(records):
    return {
        "JSON-min": json.dumps(records, separators=(",", ":"), ensure_ascii=False),
        "JSON-pretty": json.dumps(records, indent=2, ensure_ascii=False),
        "YAML": yaml.safe_dump(records, allow_unicode=True, sort_keys=False),
        "XML": encode_xml(records),
        "CSV": encode_csv(records),
        "TOON-style": encode_toon(records),
        "Twig": twig_encode(records),
    }


def round_trip_status(records):
    twig_text = twig_encode(records)
    return twig_decode(twig_text) == records


print(f"Independent null benchmark using tiktoken {ENCODING}")
print("Dataset: repeated nested records, explicit nulls, empty lists, and sparse fields")
print()
print(f"{'Records':>8} | " + " | ".join(f"{name:>12}" for name in format_payloads([make_record(0)])) )
print("-" * 112)

measured = {}
for count in (1, 10, 100, 1000):
    records = [make_record(index) for index in range(count)]
    payloads = format_payloads(records)
    measured[count] = {name: token_count(text) for name, text in payloads.items()}
    print(f"{count:>8} | " + " | ".join(f"{measured[count][name]:>12,}" for name in payloads))

print()
print("Reduction versus JSON-min at 1,000 records")
base = measured[1000]["JSON-min"]
for name, count in measured[1000].items():
    reduction = (1 - count / base) * 100
    print(f"{name:>12}: {reduction:>7.2f}% {'smaller' if reduction >= 0 else 'larger'}")

print()
print("Percentage comparison at each measured size")
print(f"{'Records':>8} | {'JSON-min':>10} | {'JSON-pretty':>12} | {'YAML':>8} | {'XML':>8} | {'CSV':>8} | {'TOON-style':>12} | {'Twig':>8}")
print("-" * 104)
for count, sizes in measured.items():
    base = sizes["JSON-min"]
    percentages = {
        name: (1 - value / base) * 100
        for name, value in sizes.items()
    }
    print(
        f"{count:>8} | "
        + " | ".join(
            f"{percentages[name]:>9.2f}%"
            for name in ("JSON-min", "JSON-pretty", "YAML", "XML", "CSV", "TOON-style", "Twig")
        )
    )

print()
print("Round-trip and null checks")
records = [make_record(index) for index in range(1000)]
print(f"{'JSON':>12}: {'PASS' if json.loads(json.dumps(records)) == records else 'FAIL'}")
print(f"{'YAML':>12}: {'PASS' if yaml.safe_load(yaml.safe_dump(records, sort_keys=False)) == records else 'FAIL'}")
print(f"{'Twig':>12}: {'PASS' if round_trip_status(records) else 'FAIL'}")
print(f"{'XML':>12}: size-only; no decoder in this benchmark")
print(f"{'CSV':>12}: size-only; null and missing values serialized as text markers")
print(f"{'TOON-style':>12}: size-only; no decoder in this benchmark")

print()
print("Linear token projection from the measured 1,000-record payload")
print(f"{'Records':>12} | {'JSON-min':>14} | {'TOON-style':>14} | {'TOON reduction':>15} | {'Twig':>14} | {'Twig reduction':>15}")
print("-" * 99)
for target in (1_000, 10_000, 100_000, 1_000_000, 10_000_000, 100_000_000):
    json_tokens = round(measured[1000]["JSON-min"] * target / 1000)
    toon_tokens = round(measured[1000]["TOON-style"] * target / 1000)
    twig_tokens = round(measured[1000]["Twig"] * target / 1000)
    toon_reduction = (1 - toon_tokens / json_tokens) * 100
    reduction = (1 - twig_tokens / json_tokens) * 100
    print(
        f"{target:>12,} | {json_tokens:>14,} | {toon_tokens:>14,} | "
        f"{toon_reduction:>14.2f}% | {twig_tokens:>14,} | {reduction:>14.2f}%"
    )
