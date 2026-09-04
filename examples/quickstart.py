"""
Minimal runnable example. From the project root:

    pip install -e .
    python examples/quickstart.py
"""

from twig import encode, decode

data = [
    {
        "name": "ffs",
        "address": {
            "present": {"state": "West Bengal", "district": "Paschim Bardhaman", "pin": "713201"},
            "permanent": {"state": "West Bengal", "district": "Paschim Bardhaman", "pin": "713301"},
        },
        "experience": [
            {"companyName": "Tata Steel", "role": "Engineer", "years": 2},
            {"companyName": "Infosys", "role": "Developer", "years": 3},
        ],
    },
    {
        "name": "raj",
        "address": {
            "present": {"state": "Bihar", "district": "Patna", "pin": "800001"},
            "permanent": {"state": "Bihar", "district": "Gaya", "pin": "823001"},
        },
        "experience": [
            {"companyName": "Wipro", "role": "Analyst", "years": 1},
        ],
    },
]

text = encode(data)
print("--- compact form ---")
print(text)

restored = decode(text)
print("\n--- round-trip check ---")
print("MATCH" if restored == data else "MISMATCH")

import json
json_len = len(json.dumps(data))
compact_len = len(text)
print(f"\nJSON size: {json_len} chars")
print(f"Compact size: {compact_len} chars")
print(f"Reduction: {(1 - compact_len/json_len)*100:.1f}%")
