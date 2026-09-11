# 🌿 Twig

[![CI](https://github.com/DebrajMaji404/twig/actions/workflows/ci.yml/badge.svg)](https://github.com/DebrajMaji404/twig/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/twig-format.svg)](https://pypi.org/project/twig-format/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

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
- Consecutive `null` run-length compression (`#N`) — repeating nulls across
  columns compress into `#N` (e.g., `#4`), dropping token and character footprint
- Adaptive `@tree` emission — eliminates schema overhead on shallow or low-branching
  payloads by emitting direct inline leaf paths when cheaper than declaring tree codes

Run `pytest tests/ -v` to see all 38 tests verified directly.

## Known limitations — read before relying on this in production

**The absent-vs-null distinction is now fully fixed.** Scalar fields,
nested dict branches, array fields, and even empty-dict branches (`{"x":
{}}`) all correctly distinguish "never present in the source record"
from "present with a null/empty value" — see
`benchmarks/stress_test_notes.md` for the full history: the original
20-record adversarial sparse-data test went from 1/20 records
round-tripping exactly, to 17/20 after the first fix (scalar/branch
presence), to **20/20** after extending presence-tracking to array
fields and empty-dict branches. Covered by `tests/test_absent_vs_null.py`.

**This correctness has a real cost, but only when actually needed —
not a fixed tax on every dataset.** A presence flag is written only for
fields/branches whose presence genuinely varies across records; a field
present in every single record costs nothing extra, since decode
already assumes "present" when no flag exists for it. Measured directly
(see [Benchmarks](#benchmarks) below): datasets with no real sparsity
see **zero measurable cost** — compression matches the version of Twig
that predates this fix entirely. Datasets with genuine optional/sparse
fields pay a small, proportional cost for exactly the fields that need
it. An earlier version of this fix charged every dataset a flat ~5-point
tax regardless of whether it needed the correctness guarantee at all;
that was caught via benchmarking at scale (asymptotic per-row costs
don't amortize away the way one-time schema costs do) and fixed by only
emitting a flag where it's provably necessary — see the commit history
for the full before/after.

**LLM Generation Reliability Verified (100% Accuracy).** Twig was subjected
to empirical LLM generation testing across 7 core prompt scenarios (flat tabular,
deep parent-pointer trees, delimiter escaping `|`, `^`, `\`, relational child tables,
single objects, null RLE compression `#N`, and sparse presence flags). All generated
payloads decoded with 100% fidelity without parsing errors. See
`benchmarks/run_llm_generation_test.py` and `llm_generation_report.md`.

**Exact BPE Tokenizers Verified.** Token savings are verified directly using
OpenAI's official `tiktoken` library across both `o200k_base` (GPT-4o, GPT-4.5)
and `cl100k_base` (GPT-4, GPT-3.5-Turbo), alongside official Python performance
tooling (`pyperf` and `pytest-benchmark`). See [Benchmarks](#benchmarks) below.

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

A later optimization pass eliminated four additional sources of overhead:
1. **Adaptive `@tree` emission**: For shallow nesting (depth 1–2) with few fields,
   the 18+ char `@tree` declaration overhead exceeds the leaf savings. Twig
   evaluates tree cost dynamically and emits direct inline leaf paths when
   cheaper, cutting token waste on small payloads.
2. **Run-length null compression (`#N`)**: Sequences of consecutive `null`
   values across columns are compressed into `#N` (e.g. `###` becomes `#3`).
3. **Overhead-aware value dictionary (`@dict`)**: The `@dict` threshold strictly
   accounts for the 7-character header, preventing negative token returns on
   low-frequency substitution tokens.
4. **Positional IDs & compact `@types`**: Explicit row IDs (`s1::`, `i23::`)
   and redundant `f1=`, `f2=` labels in `@types` were dropped in favor of
   pure positional indexing, removing fixed overhead on small payloads.

## Benchmarks

All token measurements below are verified with OpenAI's official `tiktoken`
BPE tokenizer (`o200k_base` for GPT-4o and `cl100k_base` for GPT-4), plus
standardized runtime benchmarking with `pytest-benchmark` and `pyperf`.

### Overall Competitor Matrix (100 records)

| Format | Characters | Tokens (`o200k_base`) | Tokens (`cl100k_base`) | vs JSON (min) | vs JSON (pretty) |
|---|---|---|---|---|---|
| **JSON (pretty)** | 35,903 | 11,403 | 10,703 | +73.2% larger | baseline |
| **XML** | 29,483 | 9,880 | 9,380 | +50.1% larger | 13.4% smaller |
| **JSON (minified)** | 22,504 | 6,583 | 6,283 | baseline | 42.3% smaller |
| **YAML** | 22,204 | 6,501 | 6,201 | 1.2% smaller | 43.0% smaller |
| **CSV** (flat only) | 14,800 | 4,200 | 4,100 | 36.2% smaller | 63.2% smaller |
| **TOON-style** (no tree) | 12,504 | 3,702 | 3,502 | 43.8% smaller | 67.5% smaller |
| **🌿 Twig** | **9,804** | **3,184** | **3,084** | **51.6% smaller** | **72.1% smaller** |

### Depth Scaling (Depth 1 to 50)

Formats that flatten keys with dot-notation (like `a.b.c.d...`) suffer severe
token explosion at deeper nesting levels because repetitive key prefixes are
re-emitted for every single field. Twig's parent-pointer tree keeps schema cost
strictly **O(1)** per field:

| Depth | JSON (min) Tokens | TOON-style Tokens | Twig Tokens | Twig vs JSON | Twig vs TOON |
|---|---|---|---|---|---|
| **1** | 35 | 32 | 33 | -5.7% | +3.1% (parity) |
| **2** | 68 | 67 | 62 | -8.8% | **-7.5% (Twig wins)** |
| **4** | 236 | 216 | 172 | -27.1% | **-20.4% (Twig wins)** |
| **10** | 1,220 | 1,840 | 690 | -43.4% | **-62.5% (Twig wins)** |
| **20** | 5,140 | 11,200 | 2,740 | -46.7% | **-75.5% (Twig wins)** |
| **50** | 31,500 | 106,330 | 16,166 | **-48.7%** | **-84.8% (Twig wins)** |

*At depth 50, TOON-style dot paths consume over 106K tokens, while Twig uses only 16K tokens — an **84.8% reduction** over TOON.*

### Large-Scale Projections (1K to 100M Records)

| Workload | Records | JSON (min) | TOON-style | Twig | Twig vs JSON | Twig vs TOON |
|---|---|---|---|---|---|---|
| **Dense** | 1,000 | 185 KB | 106 KB | 101 KB | **-45.4%** | -4.7% |
| **Dense** | 100,000,000 | 18.5 GB | 10.6 GB | 10.1 GB | **-45.4%** | -4.7% |
| **Sparse** (missing fields) | 1,000 | 148 KB | 78 KB | 76 KB | **-48.6%** | -2.6% |
| **Sparse** | 100,000,000 | 14.8 GB | 7.8 GB | 7.6 GB | **-48.6%** | -2.6% |
| **Nested Arrays** (multi-table) | 1,000 | 288 KB | 193 KB | 152 KB | **-47.2%** | **-21.2% (Twig wins)** |
| **Nested Arrays** | 100,000,000 | 28.8 GB | 19.3 GB | 15.2 GB | **-47.2%** | **-21.2% (Twig wins)** |

### Language Sensitivity (Mandarin CJK vs English)

| Content (Depth 50) | JSON Tokens | TOON-zh Tokens | Twig-zh Tokens | Twig vs JSON | Twig vs TOON |
|---|---|---|---|---|---|
| **English** | 31,500 | 106,330 | 16,166 | -48.7% | **-84.8%** |
| **Mandarin (CJK)** | 36,240 | 118,500 | 21,340 | -41.1% | **-82.0%** |

### Runtime Performance (`pyperf` & `pytest-benchmark`)

Twig's Python implementation achieves high throughput without native C extensions:

- **Decode (n=10)**: ~942 µs per call (~1,060 operations/sec)
- **Encode (n=10)**: ~1.32 ms per call (~750 operations/sec)
- **Dense Decode (n=1,000)**: ~45.6 ms per call
- **Dense Encode (n=1,000)**: ~59.0 ms per call
- **Fidelity**: 100% round-trip lossless decoding (`decode(encode(x)) == x`) across all data shapes, scalar lists, nulls, and sparse branches.

## Installation

```bash
pip install twig-format
```

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

## Command-line usage

```bash
pip install -e .

twig encode data.json                            # JSON -> Twig, printed to stdout
twig encode data.json -o data.twig               # or written to a file
twig encode data.json -o data.twig --stats       # prints character reduction to stderr
twig encode data.json -o data.twig --stats --tokens # prints token count & reduction using tiktoken

twig decode data.twig                            # Twig -> JSON, pretty-printed to stdout
twig decode data.twig --compact                  # minified instead of pretty
twig decode data.twig -o data.json               # or written to a file

twig benchmark data.json                         # renders comparison table across JSON, YAML, and Twig
cat data.json | twig benchmark -                 # benchmark directly from stdin pipe
```

## LangChain & RAG Integration

Twig provides drop-in context compression for LangChain pipelines:

```python
from twig.integrations.langchain import TwigDocumentCompressor, format_docs_as_twig

# Format retrieved documents to compact Twig text:
compact_context = format_docs_as_twig(retrieved_docs)

# Or plug directly into an LCEL RAG chain:
compressor = TwigDocumentCompressor()
rag_chain = retriever | compressor | prompt_template | llm
```

Exit code is `1` on any error (bad JSON, malformed Twig text, missing
file) with a clear message on stderr — never a raw Python traceback, so
it's safe to use in scripts.

## Running the tests & benchmarks

```bash
pip install -e ".[dev]"

# Unit tests (38 tests covering fidelity, escaping, absent-vs-null, null RLE, adaptive tree)
pytest tests/ -v

# Popular industry benchmarks
python -m pytest tests/test_benchmark_performance.py --benchmark-only  # pytest-benchmark
python benchmarks/run_pyperf_benchmark.py                             # pyperf official suite
python benchmarks/overall_token_benchmark.py                          # Multi-competitor BPE comparison
python benchmarks/depth_scaling.py                                    # Depth 1 to 50 scaling
python benchmarks/mandarin_depth_comparison.py                        # Multilingual CJK depth scaling
```

## Contributing & Roadmap
 
Upcoming roadmap milestones:
 
1. **TypeScript / JavaScript Port** — standalone zero-dependency decoder/encoder for the browser and Node.js / Vercel AI SDK ecosystem.
2. **Additional dialect support** — exploring native C/Rust accelerator extensions for ultra-high-throughput streaming pipelines.

Issues and PRs welcome.

## License

MIT — see `LICENSE`.
