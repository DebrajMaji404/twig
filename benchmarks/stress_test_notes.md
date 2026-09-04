# Stress test notes: the absent-vs-null limitation

This documents the test that found the format's main known limitation,
so the claim in the README is backed by a reproducible example rather
than just asserted.

## Setup

20 records were generated with deliberately varied structure -- not just
deep nesting, but fields that are sometimes present and sometimes
completely absent per record: optional `profile` branches, optional
`education` arrays, address items with or without a `geo` sub-object,
scalar lists that are sometimes empty. This is much closer to real-world
sparse data than a uniform fixed-schema dataset.

Generator: `gen_stress20.py` in the project history (not included in this
package to keep it lean -- the pattern is straightforward to recreate:
random.choice over "include this optional field or not" per record).

## What broke

Round-trip test (`decode(encode(records)) == records`) failed on 19/20
records. All failures fell into one root cause:

**The codec has no way to represent "this key was not in the original
record" -- it always reconstructs every field/branch declared anywhere in
the schema, filling missing ones with `null`.**

Concretely:
- A record where `profile` was entirely absent decoded with
  `profile: {"bio": {"short": null, "long": null}, "social": {"twitter": null}}`
  instead of no `profile` key at all.
- A record where `education` was `null` (key present, no value) decoded
  as `education: []` instead.
- Address items missing an optional `geo` sub-object got
  `geo: {"lat": null, "lng": null}` added back in.

## What did NOT break (already fixed, confirmed via this same test)

Before a fix (see the main codebase history / commit that added
`LIST_MARK`), this same test also showed:
- `"tags": ["priority"]` (single-item list) decoding as the bare string
  `"priority"`, because a single-item list and a plain scalar produce
  identical encoded output without an explicit list marker.
- `"tags": []` (empty list) decoding as `null`, for the same reason.

Both are fixed as of this package version (`LIST_MARK` prefix, see
`twig/codec.py`), and the `tags`-related mismatches are confirmed
gone when re-running the same 20-record test. Only the absent-vs-null
issue (a structurally different, harder problem) remains open.

## Why this wasn't caught earlier

Every previous test in this project's development used either uniform
schemas (all records have the same fields) or arrays that, while varying
in *length*, never had entire branches missing. Sparse/optional fields
are a genuinely different failure mode from "deep" or "many array items,"
and only showed up once a test was specifically designed to include them.
This is a reminder that round-trip testing needs deliberately messy,
partially-populated data, not just "bigger" or "deeper" clean data.

## What a fix would need

The field-presence information would need to travel alongside the value,
not be inferred from "the schema declares this field, therefore every
record has it." Two directions worth exploring:
1. A per-record presence bitmap or explicit "absent" sentinel distinct
   from `null`, transmitted per row.
2. A more radical redesign where the schema itself is closer to
   per-record than global -- declared once per *distinct shape* seen in
   the data, with records grouped by which shape they match. More
   complex, but avoids paying for a presence-marker on every field of
   every row.

Neither is implemented yet. Contributions welcome.
