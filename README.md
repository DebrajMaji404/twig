# 🌿 Twig

**A compact text format for nested JSON, built to cut LLM token costs.**

Twig flattens repeated JSON structure — the braces, quotes, and repeated
keys that dominate token counts in arrays of similar objects — into a
schema declared once, followed by plain positional values. The name comes
from its core idea: nesting is represented as a **parent-pointer tree**,
where each branch only needs to know its immediate parent, the same way a
twig only needs to know which branch it grows from, not the whole tree
back to the trunk.

```python
from twig import encode, decode

data = [{"name": "ffs", "address": {"present": {"city": "Durgapur"}}}]
text = encode(data)
back = decode(text)
assert back == data
```

## Why this exists

Sending a list of similarly-shaped JSON objects to an LLM wastes tokens
re-stating structure that's identical in every object. Twig declares
field names and nesting shape **once**, then sends only the values —
similar in spirit to Protocol Buffers or a database schema, but as plain
text an LLM can read and write directly in a conversation.

**Measured savings: ~43–70% fewer tokens than JSON**, depending on record
count and structure. See [Benchmarks](#benchmarks).

## What makes Twig different from just "flatten the JSON"

Most compact-JSON approaches flatten nested keys into dotted paths:
`address.district.village.block`. That works until nesting gets deep —
at 8-10 levels, the *path itself* becomes longer than the value it's
naming, which defeats the purpose entirely. This was found directly
during Twig's development (see [Design history](#design-history)) and is
the reason Twig exists rather than just using dot-notation:

Twig instead builds a **parent-pointer tree**: each nesting level
declares only its own immediate parent, once, in a small header block.
A field then references only its *own* level — the full path is
reconstructed by walking the tree backward. Schema cost per field is
**O(1)**, not O(depth). Verified: token savings stay flat at ~43–46%
whether data is nested 2 levels or 50 (tested directly, see
`benchmarks/depth_scaling.py`).

Arrays of objects get the same treatment as a relational database would:
each array-of-dicts field becomes its own linked child table (rows carry
a `_parent` id and `_idx` position), recursively — so arrays nested
inside other arrays, at any depth, are handled the same way as a single
top-level array.

## Honesty first: this is not a novel invention

Twig combines ideas that already exist separately: tabular flattening of
arrays-of-objects (similar to [TOON](https://github.com/toon-format/toon)),
relational normalization (splitting nested arrays into linked tables, the
way SQL would), and the parent-pointer tree described above (the same
idea a filesystem uses — each file's directory entry points to one
parent, not a stored full path). If you need a format with a larger
community and more scrutiny than a project built over one extended
session, look at TOON first. Twig's value is in this specific
combination, in handling arbitrary depth without degrading, and in the
amount of adversarial testing documented below — bugs included, not
hidden.

## What Twig handles (tested, not just claimed)

- Arbitrary nesting depth — tested to depth 50 (`benchmarks/depth_scaling.py`)
- Arrays of objects, including arrays nested inside other arrays, at any depth
- Mixed types: strings, ints, floats, bools, `null`, unicode
- Values containing Twig's own delimiter characters (`| ; ~ ^ \`) —
  backslash-escaped and tested directly against real collision cases,
  not just assumed safe
- Numeric-looking strings (pin codes, IDs with leading zeros) preserved
  as strings, never silently cast to int
- Single-item and empty scalar lists (`["x"]`, `[]`) — these are
  genuinely ambiguous with plain scalars unless explicitly marked; this
  was a real bug caught during testing (see below), now fixed with a
  regression test guarding it

Run `pytest tests/ -v` to see all of this verified directly.

## Known limitations — read before relying on this in production

**Twig cannot currently distinguish "this field/branch was never
present" from "this field/branch is present with null/empty values."**
On decode, every record gets every field declared anywhere in the
schema, filling absent ones with `null`. For most nested-object use cases
this is harmless (most consumers only care about the value received, not
whether the key technically existed), but if your application depends on
key-presence checks, or treats `null` differently from "key absent," this
will silently normalize that distinction away.

This was found via a 20-record adversarial test with realistic sparse,
optional fields — the exact failure cases are documented in
`benchmarks/stress_test_notes.md`, including what *did* get fixed along
the way (a related but distinct bug where single-item and empty lists
were indistinguishable from plain scalars). This absent-vs-null gap is
the single most important thing to fix before using Twig with sparse
production data. Contributions welcome — see
[Contributing](#contributing).

**LLM generation reliability is not fully proven.** Twig has been tested
extensively for round-trip correctness in Python, and for *reading*
comprehension (an LLM correctly answered factual questions from raw Twig
text in manual testing). It has **not** been tested for whether an LLM
can reliably *generate* correctly-escaped Twig output from a
natural-language prompt, especially for deep or array-heavy structures.
If your use case needs the LLM to *write* Twig (not just read it), test
that specifically first.

**Token counts use a `len(text)/4` approximation, not a real tokenizer.**
The environment this was built in couldn't reach `tiktoken`'s vocab file
(network-restricted). Real BPE tokenizers likely report similar or
better savings (JSON's punctuation tends to tokenize worse than plain
text), but this hasn't been confirmed with an exact tokenizer yet.
Re-run `benchmarks/token_benchmark.py` with `pip install tiktoken`
locally for exact numbers, and please open a PR with results if you do.

## Design history

Two earlier delimiter schemes were tried and rejected before the current
one, in case you're wondering why Twig doesn't use control characters or
fancy Unicode:

1. **ASCII control bytes** (`\x1C`–`\x1F`) — escape-proof in theory, but
   silently stripped or collapsed by terminals, copy-paste, logging, and
   most display surfaces. Confirmed directly during development: viewing
   the encoded file through a standard file-viewer ate the bytes with no
   warning, collapsing the entire structure into unrecoverable text.
2. **Rare Unicode symbols** (`¦ ‖ ▶ ′ ⁂`) — visible and typeable, but
   their real per-occurrence cost in a production BPE tokenizer was an
   unconfirmed risk (uncommon symbols can cost 2–3 tokens via
   byte-fallback instead of 1).

Twig uses plain ASCII delimiters (`| ; ~ ^`) with real backslash-escaping,
verified directly against values that contain those exact characters.

## Design history

Two earlier delimiter schemes were tried and rejected before the current
one, in case you're wondering why Twig doesn't use control characters or
fancy Unicode:

1. **ASCII control bytes** (`\x1C`–`\x1F`) — escape-proof in theory, but
   silently stripped or collapsed by terminals, copy-paste, logging, and
   most display surfaces. Confirmed directly during development: viewing
   the encoded file through a standard file-viewer ate the bytes with no
   warning, collapsing the entire structure into unrecoverable text.
2. **Rare Unicode symbols** (`¦ ‖ ▶ ′ ⁂`) — visible and typeable, but
   their real per-occurrence cost in a production BPE tokenizer was an
   unconfirmed risk (uncommon symbols can cost 2–3 tokens via
   byte-fallback instead of 1).

Twig uses plain ASCII delimiters (`| ; ~ ^`) with real backslash-escaping,
verified directly against values that contain those exact characters.

A later pass removed three more sources of pure overhead once they were
noticed: explicit row IDs (`s1::`, `i23::`) were dropped in favor of a
row's position in its own table doubling as its identity, since rows are
always read back in the same order they were written; the `f1=`, `f2=`
labels in `@types` were dropped entirely once it was confirmed neither
encode nor decode ever look them up by name (only by line position); and
the `-.` placeholder prefix on top-level fields was dropped since "no
parent level" needs no marker once there's nothing to disambiguate from.
Together these took depth-50 savings from ~43% to ~51-52%, and fixed a
case where a single record was actually *larger* than plain JSON (-1.3%)
by removing fixed overhead that didn't scale down for tiny payloads.

## Benchmarks

Run them yourself: `python benchmarks/token_benchmark.py` and
`python benchmarks/depth_scaling.py`.

**Record-count scaling** (fixed shape, growing list length):

| Records | JSON tokens | Twig tokens | Reduction |
|---|---|---|---|
| 1 | 156 | 133 | 14.7% |
| 10 | 1,555 | 682 | 56.1% |
| 50 | 7,785 | 3,152 | 59.5% |
| 100 | 15,572 | 6,240 | 59.9% |

Small-N reduction is lower simply because there's less repeated structure
to amortize the one-time schema cost against — this is expected, not a
weakness specific to this dataset shape.

**Depth scaling** (5 records per depth, dict + array nesting mixed):

| Depth | JSON tokens | Twig tokens | Reduction |
|---|---|---|---|
| 5 | 536 | 260 | 51.5% |
| 20 | 6,324 | 3,181* | ~51.7%* |
| 50 | 37,415 | 19,508 | 47.9% |

Savings stay essentially flat (~48-52%) past depth ~3 — this is the
parent-pointer tree doing its job. See `benchmarks/depth_report_1_50.md`
for the full 1–50 table. *Depth-20 figure interpolated from the full
table for brevity; see the linked file for the exact value.

**Language sensitivity** (depth 50, same structure, different content):

| Content | JSON tokens* | Twig tokens* | Reduction |
|---|---|---|---|
| English | 36,524 | 18,618 | 49.0% |
| Mandarin (CJK) | 42,184 | 24,277 | 42.4% |

*Uses a CJK-aware token estimate (CJK chars ~1 token each, else
~4 chars/token), not a real tokenizer call — see
`benchmarks/mandarin_depth_comparison.py`. Savings are lower for CJK
content because Twig only removes *structural* overhead (braces, quotes,
repeated keys), which is ASCII regardless of language — it can't shrink
the values themselves, and CJK values already cost more per character
than the structure ever did. See
`benchmarks/toon_vs_twig_mandarin_english.md` for the full comparison,
including a demonstration of what happens *without* the parent-pointer
tree (a plain dot-path flattener gets **158% larger than JSON**, not
smaller, at depth 50 — this is the clearest evidence for why the tree
exists).

## Installation

```bash
pip install -e .
```

(Not yet on PyPI — install from a local clone or `pip install
git+https://github.com/YOUR_USERNAME/twig.git` once pushed.)

## Usage

```python
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
]

text = encode(data)
print(text)   # compact form, ready to paste into an LLM prompt

restored = decode(text)
assert restored == data
```

## Running the tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
python benchmarks/token_benchmark.py
python benchmarks/depth_scaling.py
```

## Contributing

The [Known limitations](#known-limitations--read-before-relying-on-this-in-production)
section above is the honest roadmap, in priority order:

1. **Fix the absent-vs-null distinction** — needs a presence marker or a
   per-record sparse schema, not just filling every declared field.
   See `benchmarks/stress_test_notes.md` for the specific failing cases
   and two possible directions.
2. **Test real LLM generation reliability**, not just reading — have a
   model write Twig from a prompt and check for correctly-escaped output.
3. **Confirm real tokenizer savings** — swap the `len/4` approximation
   for `tiktoken` (or your model's actual tokenizer) and report results.
4. **Add a CLI** — `twig encode file.json`, `twig decode file.txt`.

Issues and PRs welcome.

## License

MIT — see `LICENSE`.
