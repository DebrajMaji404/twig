import json
from twig.codec import encode

# NOTE: tiktoken's real vocab file is hosted on openaipublic's blob storage,
# which this sandbox's network allowlist doesn't include, so we can't call
# the real GPT tokenizer here. Using the standard approximation instead:
# ~4 characters/token for English text (well-documented rule of thumb for
# GPT-family BPE tokenizers). This is an ESTIMATE -- run this same script
# locally with `pip install tiktoken` for exact counts; the relative
# reduction % should still be close, since punctuation-heavy JSON tends to
# tokenize slightly WORSE than 4 chars/token (braces/quotes often become
# their own tokens), so real savings are likely >= what's shown here.

def toks(s):
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


print(f"{'N records':>10} | {'JSON tokens':>12} | {'compact tokens':>15} | {'reduction':>10}")
print("-" * 60)
for n in (1, 2, 5, 10, 25, 50, 100):
    data = [make_person(i) for i in range(n)]

    json_str = json.dumps(data)
    json_tok = toks(json_str)

    compact_str = encode(data)
    compact_tok = toks(compact_str)

    reduction = (1 - compact_tok / json_tok) * 100
    print(f"{n:>10} | {json_tok:>12} | {compact_tok:>15} | {reduction:>9.1f}%")

# also show minified JSON (no indent) - already what json.dumps(data) gives above
# and pretty JSON, for comparison, since a lot of real payloads are pretty-printed
print("\n--- comparison vs pretty-printed JSON (indent=2), a common real-world case ---")
for n in (1, 10, 50):
    data = [make_person(i) for i in range(n)]
    pretty_tok = toks(json.dumps(data, indent=2))
    compact_tok = toks(encode(data))
    reduction = (1 - compact_tok / pretty_tok) * 100
    print(f"n={n:>3}: pretty JSON = {pretty_tok:>6} tokens, compact = {compact_tok:>6} tokens, reduction = {reduction:.1f}%")
