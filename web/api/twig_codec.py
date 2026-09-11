"""
compact-schema codec: a token-efficient text format for sending nested JSON
to LLMs.

Design history (all tested during development, kept here so the reasoning
isn't lost):
  1. ASCII control bytes as delimiters -- escape-proof in theory, but
     silently stripped/collapsed by terminals, copy-paste, logging, and
     most display surfaces. Rejected.
  2. Rare Unicode symbols -- visible, but unconfirmed/risky per-token BPE
     cost. Rejected in favor of...
  3. Plain ASCII delimiters (| ; ~ etc) with real backslash-escaping,
     verified safe even when real data contains the delimiter characters.
  4. Deep nesting (5-10 levels) revealed that repeating a full dotted path
     per field ("level2.level3...level10.field") becomes the dominant
     cost at depth, defeating the format's own purpose. Fixed with a
     parent-pointer TREE: each nesting level declares only its own
     immediate parent (once), and a field references only its own level
     -- full paths are reconstructed by walking the tree backward, so
     schema cost per field is O(1), not O(depth).
  5. This version generalizes that tree idea to also handle list-of-dict
     fields (arrays) at ANY depth, including arrays nested inside other
     arrays: every list-of-dicts field becomes its own linked child
     table (rows carry a _parent id and _idx position), recursively.
  6. BPE-aware null encoding: nulls are encoded as EMPTY fields (||)
     instead of a marker character. BPE tokenizers merge consecutive
     pipe characters into a single token (|||| = 1 tok), making null
     runs dramatically cheaper than any explicit marker. Empty strings
     are distinguished via the STR_MARK prefix ('). Measured: 6x
     cheaper null encoding on o200k_base.
  7. Compact section headers: @tree, @dict, @types all emit on a single
     comma-separated line instead of one-entry-per-line, saving ~33
     tokens of header overhead per table.

Delimiters:
    FIELD_SEP = |   -> between fields in one row
    LIST_SEP  = ^   -> between items of a scalar list value (e.g. tags)
Escaping: FIELD_SEP, LIST_SEP, a literal backslash, and a literal newline
appearing inside real data are backslash-escaped; splitting is done with
an escape-aware scanner, never naive str.split.

Public API:
    encode(data: dict | list) -> str
    decode(text: str) -> list[dict]   (always returns a list of records)
"""

from __future__ import annotations
import functools
import itertools
import re
from typing import Any

FIELD_SEP = "|"
LIST_SEP = "^"
LIST_MARK = "*"     # prefixes any list-encoded value, even 0 or 1 items --
                     # without this, ["priority"] and "priority" encode to
                     # the identical string (no separator needed to join a
                     # single item), and [] encodes to "" indistinguishable
                     # from an empty string. Found via testing (stress20).
TABLE_SEP = "\n===\n"   # separates table blocks

# BPE-aware null: encoded as EMPTY FIELD (nothing between delimiters).
# This is dramatically cheaper than any explicit marker because BPE merges
# consecutive pipe characters: ||| = 1 token vs |#|#| = 4+ tokens.
# The old NULL_TOKEN "#" is kept ONLY for backward-compat decoding and
# for use inside scalar-list values (where empty can't work).
NULL_TOKEN = ""      # empty string = null in a row cell
_OLD_NULL_TOKEN = "#"  # for backward-compatible decoding of old Twig text
ABSENT_TOKEN = "!"   # distinct from null: marks a field whose key was
                      # never present in the source record at all, vs. a key
                      # that's present with an explicit null value. Without
                      # this distinction, decode() always fills every
                      # declared schema field for every record, silently
                      # turning "key never existed" into "key is null" --
                      # a real bug found via adversarial sparse-data testing
                      # (see benchmarks/stress_test_notes.md).
STR_MARK = "'"
LIST_NULL = "#"      # null marker INSIDE scalar lists (e.g. *python^#^sql)
                      # can't use empty there since ^^ is ambiguous with
                      # a list of two empty strings
NEWLINE_ESCAPE = ("\n", "\\n")  # (real, escaped) -- handled outside the
                                 # generic char-escape loop since a naive
                                 # replace of "\n" with "\\"+"\n" would still
                                 # contain a real newline

# Sentinel returned by _decode_field for an ABSENT_TOKEN value, distinct
# from Python's None (which represents an explicit null). build_record
# checks for this exact object (via `is`) to omit the key entirely rather
# than setting it to any value at all.
ABSENT = object()

_SPECIAL_CHARS = (FIELD_SEP, LIST_SEP)
_NUM_RE = re.compile(r"-?[1-9]\d*|0")
_FLOAT_RE = re.compile(r"-?(?:\d+\.?\d*|\.\d+)[eE][+-]?\d+|-?\d+\.\d+")

try:
    import tiktoken as _tiktoken_mod
    _TIKTOKEN_ENC = _tiktoken_mod.get_encoding("o200k_base")
except Exception:
    _TIKTOKEN_ENC = None


def _token_length(text: str) -> int:
    """Returns exact token length if tiktoken is available, or an accurate BPE heuristic."""
    if _TIKTOKEN_ENC is not None:
        try:
            return len(_TIKTOKEN_ENC.encode(text, disallowed_special=()))
        except Exception:
            pass
    return max(1, len(re.findall(r"\w+|[^\w\s]|\s+", text)))


@functools.lru_cache(maxsize=4096)
def _split_path(path: str) -> tuple[str, ...]:
    """Splits a dotted path, respecting backslash-escaped dots (\\.) inside JSON keys."""
    if "." not in path:
        return (path.replace(r"\.", ".").replace(r"\\", "\\"),) if "\\" in path else (path,)
    if "\\" not in path:
        return tuple(path.split("."))
    parts = [re.sub(r"\\(.)", r"\1", p) for p in re.split(r"(?<!\\)\.", path)]
    return tuple(parts)


def _escape_key(k: str) -> str:
    """Escapes dots and backslashes in JSON keys to avoid conflation with path nesting."""
    if "." in k or "\\" in k:
        return k.replace("\\", "\\\\").replace(".", r"\.")
    return k


# ---------------------------------------------------------------------------
# escape-aware primitives
# ---------------------------------------------------------------------------

def _escape(s: str) -> str:
    s = s.replace("\\", "\\\\")
    s = s.replace("\n", "\\n")
    for ch in _SPECIAL_CHARS:
        s = s.replace(ch, "\\" + ch)
    return s


def _unescape(s: str) -> str:
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            nxt = s[i + 1]
            out.append("\n" if nxt == "n" else nxt)
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _aware_split(s: str, sep: str) -> list:
    if "\\" not in s:
        return s.split(sep)
    parts = []
    buf = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            buf.append(c)
            buf.append(s[i + 1])
            i += 2
            continue
        if c == sep:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


# ---------------------------------------------------------------------------
# scalar <-> string
# ---------------------------------------------------------------------------

def _scalar_to_str(v: Any) -> str:
    if v is None:
        return NULL_TOKEN    # empty string -> empty field between delimiters
    if isinstance(v, bool):
        return "T" if v else "F"
    if isinstance(v, str):
        needs_mark = (
            v in ("true", "false", "T", "F")
            or v == ""
            or v == ABSENT_TOKEN
            or v == _OLD_NULL_TOKEN
            or v.startswith(LIST_MARK)
            or v.startswith(STR_MARK)
            or v.startswith("&")
            or (v.startswith(ABSENT_TOKEN) and len(v) > 1 and v[1:].isdigit())
            or (v.startswith(_OLD_NULL_TOKEN) and len(v) > 1 and v[1:].isdigit())
            or _NUM_RE.fullmatch(v)
            or _FLOAT_RE.fullmatch(v)
        )
        escaped = _escape(v)
        return (STR_MARK + escaped) if needs_mark else escaped
    return str(v)


def _scalar_to_str_in_list(v: Any) -> str:
    """Encode a scalar inside a list value. Nulls use LIST_NULL (#) instead
    of empty, because ^^ inside a list is ambiguous."""
    if v is None:
        return LIST_NULL
    return _scalar_to_str(v) if v is not None else LIST_NULL


def _str_to_scalar(s: str) -> Any:
    if s.startswith(STR_MARK):
        return _unescape(s[len(STR_MARK):])
    if s == "" or s == _OLD_NULL_TOKEN:
        # Both empty field (new format) and "#" (old format) decode as null
        return None
    if s == "T" or s == "true":
        return True
    if s == "F" or s == "false":
        return False
    if _NUM_RE.fullmatch(s):
        return int(s)
    if _FLOAT_RE.fullmatch(s):
        return float(s)
    return _unescape(s)


def _str_to_scalar_in_list(s: str) -> Any:
    """Decode a scalar inside a list value. LIST_NULL (#) maps to None."""
    if s == LIST_NULL:
        return None
    return _str_to_scalar(s)


def _encode_field(v: Any) -> str:
    if isinstance(v, list):
        # LIST_MARK prefix is mandatory, not optional -- without it, a
        # single-item list and a plain scalar produce identical output
        # (no separator needed to join one item), and an empty list
        # produces "" indistinguishable from an empty string. Confirmed
        # as a real bug via the stress20 test before this fix.
        return LIST_MARK + LIST_SEP.join(_scalar_to_str_in_list(x) for x in v)
    return _scalar_to_str(v)


def _decode_field(s: str) -> Any:
    if s == ABSENT_TOKEN:
        return ABSENT
    if s.startswith(LIST_MARK):
        content = s[len(LIST_MARK):]
        if content == "":
            return []
        pieces = _aware_split(content, LIST_SEP)
        return [_str_to_scalar_in_list(p) for p in pieces]
    return _str_to_scalar(s)


# ---------------------------------------------------------------------------
# deep flatten: splits a record into (scalar leaf paths) and
# (list-of-dict leaf paths), recursing through plain dicts only
# ---------------------------------------------------------------------------

def _deep_flatten(d: dict, prefix: str = ""):
    """
    Recurses through plain dicts, returning:
      scalars: {path: value}          -- real scalar/scalar-list leaves
      lists:   {path: raw_list_value} -- fields that are Python lists
      empty_dicts: [path, ...]        -- dict-valued paths whose value
                                          was a literal empty dict {}
    A list is classified as a candidate "array of dicts" field if it's
    non-empty and contains dicts, OR if it's simply empty (ambiguous --
    resolved later by scanning across all rows/records). A non-empty
    list of plain scalars (e.g. tags) stays a scalar field.

    An empty dict contributes NOTHING to `scalars`/`lists` (the loop
    over its keys simply never runs), which loses the fact that the key
    existed at all -- `empty_dicts` exists specifically to recover that
    information, since a branch that's ALWAYS either absent or an empty
    dict (never populated with real content in any record) would
    otherwise never even get registered as a tree level in the first
    place, let alone get a presence flag.
    """
    scalars, lists, empty_dicts = {}, {}, []
    for k, v in d.items():
        escaped_k = _escape_key(k)
        path = f"{prefix}.{escaped_k}" if prefix else escaped_k
        if isinstance(v, dict):
            if not v:
                empty_dicts.append(path)
            else:
                sub_s, sub_l, sub_e = _deep_flatten(v, path)
                scalars.update(sub_s)
                lists.update(sub_l)
                empty_dicts.extend(sub_e)
        elif isinstance(v, list) and (not v or isinstance(v[0], dict)):
            lists[path] = v
        else:
            scalars[path] = v
    return scalars, lists, empty_dicts


_MISSING = object()  # internal-only marker, distinct from ABSENT (the
                      # public decode-side sentinel) -- used purely to walk
                      # dict.get() chains without confusing "key missing"
                      # with "key present, value happens to be None"


def _resolve_path(record: dict, path: str):
    """
    Walks a dotted path segment-by-segment through the ORIGINAL nested
    record dict (not the pre-flattened scalar/list maps), distinguishing
    "this path was never present" from "this path is present with value
    None". Returns (found: bool, value). If found is False, value is
    meaningless (always None).

    This exists because dict.get(path, default) alone can't make this
    distinction once the dict is nested: .get() on a flattened map
    conflates "key not in map" with "key in map, mapped to None" --
    exactly the bug this function fixes (see ABSENT_TOKEN docs above).
    """
    parts = _split_path(path)
    node = record
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return False, None
        node = node[p]
    return True, node


def _classify_paths(flat_pairs):
    """
    Resolves each candidate path (seen as either a scalar or a "list"
    candidate in _deep_flatten) to a final kind, scanning ALL rows so a
    field that's an empty list in every row isn't misclassified just
    because no single row has an informative example.
        'scalar' -> stays a normal field (possibly a scalar-list value)
        'array'  -> becomes a child table (list-of-dicts), even if every
                    row's list happens to be empty
    Returns (scalar_paths, list_paths) in first-seen order.
    """
    candidates = []  # first-seen order across both buckets
    for _, sc, ls in flat_pairs:
        for k in list(sc.keys()) + list(ls.keys()):
            if k not in candidates:
                candidates.append(k)

    kind = {}
    for path in candidates:
        resolved = None
        for _, sc, ls in flat_pairs:
            if path in ls and ls[path]:          # non-empty list-of-dicts: definitive
                resolved = "array"
                break
            if path in sc and isinstance(sc[path], list) and sc[path]:
                resolved = "scalar"               # non-empty scalar list: definitive
                break
        if resolved is None:
            # no informative example anywhere -- fall back to whichever
            # bucket it was seen in; prefer "array" if seen there at all,
            # since an empty list is the far more common real-world shape
            # for this ambiguous case (e.g. "experience: []")
            saw_list_bucket = any(path in ls for _, _, ls in flat_pairs)
            resolved = "array" if saw_list_bucket else "scalar"
        kind[path] = resolved

    scalar_paths = [p for p in candidates if kind[p] == "scalar"]
    list_paths = [p for p in candidates if kind[p] == "array"]
    return scalar_paths, list_paths


def _build_tree(paths: list) -> dict:
    """Parent-pointer chain over the dotted-path segments preceding each
    path's own leaf name (the leaf itself is never registered as a
    level -- only what comes before it). Returns level_parent only;
    level_codes is assigned separately, AFTER any empty-dict-derived
    levels (see _register_full_chain) are merged in, so every level
    gets a code regardless of which mechanism discovered it."""
    level_parent = {}
    for p in paths:
        chain = _split_path(p)[:-1]
        for i, seg in enumerate(chain):
            parent = chain[i - 1] if i > 0 else None
            level_parent[seg] = parent
    return level_parent


def _register_full_chain(level_parent: dict, full_path: str) -> None:
    """
    Registers EVERY segment of `full_path` as a level, including the
    path's own final segment -- unlike _build_tree, which only ever
    registers segments that precede some OTHER leaf. This is what's
    needed for a branch that's always either absent or an empty dict in
    every record: it never has a leaf of its own underneath it, so
    _build_tree alone would never notice it exists at all, and it would
    never get a presence flag -- silently collapsing "present but
    empty" into "absent" for exactly the branches most likely to need
    that distinction.
    """
    segs = _split_path(full_path)
    for i, seg in enumerate(segs):
        if seg not in level_parent:
            level_parent[seg] = segs[i - 1] if i > 0 else None


def _immediate_level_and_leaf(path: str, level_codes: dict):
    chain = _split_path(path)
    leaf = _escape_key(chain[-1])
    immediate = level_codes.get(chain[-2]) if len(chain) > 1 else None
    return immediate, leaf


# ---------------------------------------------------------------------------
# ENCODE
# ---------------------------------------------------------------------------

def _process_table(records, table_code, table_id_counter, parent_meta=None):
    """
    Encodes one table (root, or a child table spawned by a list-of-dicts
    field) and recursively encodes any tables it spawns. Returns a list of
    table-block strings (this table's block first, then descendants).

    Rows carry NO explicit id -- a row's identity is simply its position
    in this table's @rows section (0-based). `parent_meta`, when given, is
    a list (same order as `records`) of {"_parent": parent_index, "_idx":
    position} for a CHILD table's own bookkeeping fields, where
    parent_index is the PARENT row's position in ITS OWN table.

    `table_id_counter` is a single counter SHARED across the entire
    recursion, so every child table gets a globally unique code.

    Presence flags (new): alongside real data fields, each row also
    carries a boolean per array field ("$has:<tablecode>") and per
    nesting level ("$lvl:<levelcode>") declared in this table, recording
    whether that array/branch was genuinely present in the source record
    -- not just inferable from whether any of its leaves happened to be
    set. This is what lets decode() tell "array field absent" apart from
    "array field present but empty", and "branch present as an empty
    dict" apart from "branch absent entirely" -- neither is inferable
    from the leaf data alone. This has a real, non-zero token cost (one
    extra boolean per array/level per row) -- see benchmarks/ for the
    measured trade-off.
    """
    flat_pairs = [_deep_flatten(rec) for rec in records]
    scalar_paths, list_paths = _classify_paths([(i, sc, ls) for i, (sc, ls, _) in enumerate(flat_pairs)])

    is_child_table = parent_meta is not None
    if is_child_table:
        scalar_paths = ["_parent", "_idx"] + scalar_paths

    all_paths_for_tree = [p for p in scalar_paths if p not in ("_parent", "_idx")] + list_paths
    level_parent = _build_tree(all_paths_for_tree)

    # Also register branches that are ALWAYS either absent or an empty
    # dict in every record (never populated with real content anywhere),
    # since _build_tree alone only discovers levels that have some real
    # leaf underneath them somewhere -- a branch with zero leaves ever
    # would otherwise never even become a registered level, let alone
    # get a presence flag.
    all_empty_dict_paths = set()
    for _, _, empty_dicts in flat_pairs:
        all_empty_dict_paths.update(empty_dicts)
    for ep in all_empty_dict_paths:
        _register_full_chain(level_parent, ep)

    level_codes = {name: f"l{i+1}" for i, name in enumerate(level_parent.keys())}

    def _level_full_path(name):
        chain = []
        cur = name
        while cur:
            chain.append(cur)
            cur = level_parent.get(cur)
        return ".".join(reversed(chain))

    array_codes = {p: f"t{next(table_id_counter)}" for p in list_paths}

    real_scalar_paths = [p for p in scalar_paths if p not in ("_parent", "_idx")]

    # ---- frequency-sort: most-present real fields first ----
    # This maximizes trailing-truncation savings (see row building below):
    # the rarest fields (most likely absent) cluster at the tail where
    # they can be dropped entirely.
    _path_freq = {}
    for p in real_scalar_paths:
        _path_freq[p] = sum(1 for r in records if _resolve_path(r, p)[0])
    real_scalar_paths.sort(key=lambda p: -_path_freq[p])
    # Rebuild scalar_paths with the new sorted order (tree/level code
    # computation above used the old order but only cares about the SET
    # of paths, not their sequence).
    if is_child_table:
        scalar_paths = ["_parent", "_idx"] + real_scalar_paths
    else:
        scalar_paths = list(real_scalar_paths)

    # Only fields/branches whose presence actually VARIES across records
    # get a flag at all -- one that's present in every single record
    # costs nothing extra, since decode already defaults to "present"
    # when no flag exists for it. This matters a lot in practice: most
    # fields in real data are consistently present, and only a minority
    # are genuinely optional, so this keeps the presence-tracking cost
    # proportional to actual sparsity instead of a fixed per-row tax
    # that never amortizes away, even at very large record counts.
    array_needs_flag = {
        p: not all(_resolve_path(r, p)[0] for r in records)
        for p in list_paths
    }

    # A level only needs a flag for the specific ambiguous case: present
    # as a dict, but with NONE of its own leaf fields populated for that
    # record (the case that would otherwise silently collapse to
    # "absent"). A level that's always either fully absent, or always
    # accompanied by real leaf content when present, needs no flag --
    # natural leaf-based reconstruction already handles both correctly.
    level_own_leaves = {
        name: [p for p in real_scalar_paths if p.startswith(_level_full_path(name) + ".")]
        for name in level_codes
    }
    level_needs_flag = {}
    for name in level_codes:
        path = _level_full_path(name)
        leaves = level_own_leaves[name]
        needs = False
        for r in records:
            found, value = _resolve_path(r, path)
            if found and isinstance(value, dict) and not any(_resolve_path(r, lf)[0] for lf in leaves):
                needs = True
                break
        level_needs_flag[name] = needs

    # Adaptive parent-pointer tree: only emit @tree if the savings from
    # shortening leaf paths in @types/@arrays exceeds the declaration cost
    # of the tree itself, or if empty-dict presence flags ($lvl:) require
    # level codes. For shallow nesting with few fields, direct dotted paths
    # consume fewer tokens and avoid fixed header overhead.
    requires_tree = any(level_needs_flag.values())
    use_tree = True
    if not requires_tree and level_parent:
        # Compact format: @tree:l1=address^-,l2=employment^- (single line)
        tree_entries = [
            f"{level_codes[name]}={name}^{level_codes[parent] if parent else '-'}"
            for name, parent in level_parent.items()
        ]
        tree_decl_cost = len("@tree:") + sum(len(e) for e in tree_entries) + len(tree_entries) - 1 + 1  # commas + newline
        tree_savings = 0
        for p in real_scalar_paths + list_paths:
            chain = _split_path(p)
            if len(chain) > 1:
                full_prefix = ".".join(chain[:-1])
                code = level_codes.get(chain[-2], "")
                tree_savings += max(0, len(full_prefix) - len(code))
        if tree_savings <= tree_decl_cost:
            use_tree = False
            level_codes = {}

    tree_lines = []
    if use_tree:
        for name, parent in level_parent.items():
            parent_code = level_codes[parent] if parent else "-"
            tree_lines.append(f"{level_codes[name]}={name}^{parent_code}")

    array_lines = []
    for p in list_paths:
        tcode = array_codes[p]
        lvl, leaf = _immediate_level_and_leaf(p, level_codes)
        path_repr = f"{lvl}.{leaf}" if lvl else p
        array_lines.append(f"{tcode}={path_repr}")

    # Presence-flag field names, appended to the real scalar fields.
    # "$has:<tcode>" / "$lvl:<levelcode>" can't collide with a real
    # dotted path (those never contain "$" or ":" unless a source JSON
    # key itself does, an accepted narrow edge case shared with the
    # other reserved tokens in this codec, e.g. NULL_TOKEN/STR_MARK).
    has_flag_paths = {p: f"$has:{array_codes[p]}" for p in list_paths if array_needs_flag[p]}
    lvl_flag_paths = {name: f"$lvl:{code}" for name, code in level_codes.items() if level_needs_flag.get(name, False)}
    meta_extra_paths = list(has_flag_paths.values()) + list(lvl_flag_paths.values())

    def _is_meta(p):
        return p in ("_parent", "_idx") or p.startswith("$has:") or p.startswith("$lvl:")

    # Build @types in truncation-friendly order: bookkeeping fields
    # first (_parent/_idx, presence flags -- never absent), then real
    # data fields in frequency-sorted order (rarest last, where
    # trailing truncation can drop them).
    type_entries = []
    for p in scalar_paths:
        if p in ("_parent", "_idx"):
            type_entries.append(p)
    type_entries.extend(meta_extra_paths)
    for p in scalar_paths:
        if _is_meta(p):
            continue
        lvl, leaf = _immediate_level_and_leaf(p, level_codes)
        type_entries.append(f"{lvl}.{leaf}" if lvl else p)


    all_row_vals = []
    for i, (sc, ls, _) in enumerate(flat_pairs):
        vals = []

        # Bookkeeping fields first (never absent, won't block truncation).
        if is_child_table:
            m = parent_meta[i]
            vals.append(_encode_field(m["_parent"]))
            vals.append(_encode_field(m["_idx"]))

        # Array presence flags: only for fields whose presence actually
        # varies across records (see array_needs_flag above).
        for p in list_paths:
            if not array_needs_flag[p]:
                continue
            found, _ = _resolve_path(records[i], p)
            vals.append(_encode_field(found))

        # Level (branch) presence flags: only for levels that genuinely
        # need one (see level_needs_flag above).
        for name in level_codes:
            if not level_needs_flag[name]:
                continue
            found, value = _resolve_path(records[i], _level_full_path(name))
            vals.append(_encode_field(found and isinstance(value, dict)))

        # Real data fields last, in frequency-sorted order (rarest fields
        # at the tail). Resolve each field against the ORIGINAL record
        # dict so "key never existed" (ABSENT_TOKEN) is distinguished
        # from "key exists, value is None" (NULL_TOKEN).
        real_paths = [p for p in scalar_paths if not _is_meta(p)]
        for p in real_paths:
            found, value = _resolve_path(records[i], p)
            vals.append(ABSENT_TOKEN if not found else _encode_field(value))

        # Trailing truncation: drop trailing ABSENT_TOKEN values from
        # the row. The decoder pads short rows with ABSENT, so missing
        # trailing positions are implicitly absent -- saving one token
        # of overhead (the marker + delimiter) per dropped field per row.
        while vals and vals[-1] == ABSENT_TOKEN:
            vals.pop()

        all_row_vals.append(vals)

    # Build Value Dictionary (@dict)
    value_counts = {}
    for vals in all_row_vals:
        for val in vals:
            if (
                val != ABSENT_TOKEN
                and val != NULL_TOKEN
                and val != "T"
                and val != "F"
                and not val.startswith("&")
                and not (val.startswith(ABSENT_TOKEN) and len(val) > 1 and val[1:].isdigit())
            ):
                value_counts[val] = value_counts.get(val, 0) + 1

    # Candidate filtering rules:
    # 1. Frequency rule: must appear more than once (count > 1)
    # 2. Short character exemption: len(val) > 2 (bypasses 'A', 'AA')
    # 3. Net byte savings: account for @dict section header on first entry
    # 4. Net token savings: ref (&N) is >= 2 tokens; val must have > ref tokens
    #    so that replacing val with &N never inflates per-row tokens.
    candidates = [(val, cnt) for val, cnt in value_counts.items() if cnt > 1 and len(val) > 2]
    candidates.sort(key=lambda x: -(x[1] * len(x[0])))

    dict_entries = []
    val_to_ref = {}

    for val, count in candidates:
        ref = f"&{len(val_to_ref)}"
        if len(ref) < len(val):
            val_toks = _token_length(val)
            ref_toks = _token_length(ref)
            if val_toks <= ref_toks:
                continue

            # Compact dict: @dict: prefix + comma-separated entries on one line
            header_cost = 6 if not dict_entries else 1  # "@dict:" or ","
            dict_decl_cost = len(ref) + 1 + len(val) + header_cost
            savings = count * (len(val) - len(ref))
            if savings > dict_decl_cost:
                val_to_ref[val] = ref
                dict_entries.append(f"{ref}={val}")

    row_lines = []
    for vals in all_row_vals:
        if val_to_ref:
            vals = [val_to_ref.get(v, v) for v in vals]

        # Run-length compression for absent runs only.
        # Null runs are NOT RLE'd because empty fields (||||) are already
        # ultra-cheap in BPE -- consecutive pipes merge into 1-2 tokens
        # regardless of count. RLE would actually INCREASE tokens by
        # replacing |||| (1 tok) with a multi-char marker.
        compressed_vals = []
        idx = 0
        n = len(vals)
        while idx < n:
            if vals[idx] == ABSENT_TOKEN:
                run_start = idx
                while idx < n and vals[idx] == ABSENT_TOKEN:
                    idx += 1
                run_len = idx - run_start
                if run_len >= 2:
                    compressed_vals.append(f"{ABSENT_TOKEN}{run_len}")
                else:
                    compressed_vals.append(ABSENT_TOKEN)
            else:
                compressed_vals.append(vals[idx])
                idx += 1

        row_lines.append(FIELD_SEP.join(compressed_vals))

    # Compact block assembly: all sections on single lines
    block = f"T:{table_code}\n"
    if tree_lines:
        block += "@tree:" + ",".join(tree_lines) + "\n"
    if dict_entries:
        block += "@dict:" + ",".join(dict_entries) + "\n"
    block += "@types:" + ",".join(type_entries) + "\n"
    if array_lines:
        block += "@arrays:" + ",".join(array_lines) + "\n"
    block += "@rows\n" + "\n".join(row_lines)

    blocks = [block]

    for lpath in list_paths:
        tcode = array_codes[lpath]
        child_records = []
        child_meta = []
        for i, (sc, ls, _) in enumerate(flat_pairs):
            items = ls.get(lpath) or []
            for idx, item in enumerate(items):
                child_records.append(item)
                child_meta.append({"_parent": i, "_idx": idx})
        blocks.extend(_process_table(child_records, tcode, table_id_counter, parent_meta=child_meta))

    return blocks


def encode(data) -> str:
    """
    Encodes `data` into compact Twig text. Accepts either a single dict
    (a "single record") or a list of dicts. The original shape is
    recorded in a leading shape marker (~L for list, ~S for single) so
    decode() can restore it exactly -- without this, encode(single_dict)
    and decode() would silently turn a single object into a one-item
    list, which is a real round-trip bug.
    """
    is_list_input = isinstance(data, list)
    records = data if is_list_input else [data]
    if not records:
        return ""
    table_id_counter = itertools.count(1)
    blocks = _process_table(records, "root", table_id_counter, parent_meta=None)
    shape = "~L" if is_list_input else "~S"
    return f"{shape}\n" + TABLE_SEP.join(blocks)


# ---------------------------------------------------------------------------
# DECODE
# ---------------------------------------------------------------------------

def _parse_table_block(block: str):
    lines = block.split("\n")
    # Support both new compact "T:" prefix and old "table:" prefix
    if lines[0].startswith("T:"):
        table_code = lines[0][2:]
    elif lines[0].startswith("table:"):
        table_code = lines[0][len("table:"):]
    else:
        raise ValueError(f"Malformed Twig text: expected a table block starting with 'T:' or 'table:', got {lines[0]!r}")

    # Parse sections: support both compact inline format (@section:content)
    # and old multi-line format (@section\ncontent\n...)
    sections = {}
    current = None
    for line in lines[1:]:
        if line.startswith("@"):
            # Check for compact inline format: @section:content
            if ":" in line and not line.startswith("@rows"):
                section_name, _, inline_content = line[1:].partition(":")
                sections[section_name] = [inline_content] if inline_content else []
                current = None  # don't collect more lines into this section
            else:
                # Old multi-line format or @rows (which is always multi-line)
                section_name = line[1:]
                sections[section_name] = []
                current = section_name
        elif current is not None:
            sections[current].append(line)

    level_name, level_parent_code = {}, {}
    # Parse @tree: supports both inline comma-separated and old multi-line
    for raw_line in sections.get("tree", []):
        # Split by comma for inline format, or process single entry per line
        entries = raw_line.split(",") if "," in raw_line else [raw_line]
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            code, rest = entry.split("=", 1)
            name, parent_code = rest.split("^", 1)
            level_name[code] = name
            level_parent_code[code] = None if parent_code == "-" else parent_code

    def full_path(lvl_code, leaf):
        if lvl_code in level_name:
            chain = []
            code = lvl_code
            while code:
                chain.append(_escape_key(level_name[code]))
                code = level_parent_code.get(code)
            return ".".join(list(reversed(chain)) + [leaf])
        return f"{lvl_code}.{leaf}"

    # Full dotted path for a LEVEL itself (not a field under it) -- used
    # to resolve "$lvl:<code>" presence flags back to the branch they
    # describe, e.g. to know that "$lvl:l2" means "the 'address.present'
    # branch".
    def level_only_path(lvl_code):
        chain = []
        code = lvl_code
        while code:
            chain.append(_escape_key(level_name[code]))
            code = level_parent_code.get(code)
        return ".".join(reversed(chain))

    level_full_paths = {code: level_only_path(code) for code in level_name}

    # @types lines are bare path specs now (no "fN=" label) -- a field's
    # identity is simply its position in this list, matching the same
    # position in every @rows line.
    field_order = []
    for line in sections.get("types", []):
        if line == "":
            continue  # skip empty
        # Support comma-separated (new compact), pipe-separated (old), or
        # one-per-line (old) formats
        if "," in line:
            items = line.split(",")
        elif FIELD_SEP in line:
            items = _aware_split(line, FIELD_SEP)
        else:
            items = [line]
        for item in items:
            item = item.strip()
            if not item:
                continue
            parts = re.split(r"(?<!\\)\.", item)
            if len(parts) > 1:
                lvl, leaf = ".".join(parts[:-1]), parts[-1]
                field_order.append(full_path(lvl, leaf))
            else:
                field_order.append(item)

    array_path = {}
    array_order = []
    for line in sections.get("arrays", []):
        if not line:
            continue
        # Support comma-separated (new compact) and old one-per-line
        entries = line.split(",") if "," in line else [line]
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            acode, rest = entry.split("=", 1)
            parts = re.split(r"(?<!\\)\.", rest)
            if len(parts) > 1:
                lvl, leaf = ".".join(parts[:-1]), parts[-1]
                array_path[acode] = full_path(lvl, leaf)
            else:
                array_path[acode] = rest
            array_order.append(acode)

    dict_map = {}
    for line in sections.get("dict", []):
        if not line:
            continue
        # Support comma-separated (new compact) and old one-per-line
        entries = line.split(",") if "," in line else [line]
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            ref, val = entry.split("=", 1)
            dict_map[ref] = val

    rows = []
    for line in sections.get("rows", []):
        raw_vals = _aware_split(line, FIELD_SEP) if line else []
        vals = []
        for v in raw_vals:
            if v in dict_map:
                v = dict_map[v]
            if v.startswith(ABSENT_TOKEN) and len(v) > 1 and v[1:].isdigit():
                vals.extend([ABSENT_TOKEN] * int(v[1:]))
            elif v == _OLD_NULL_TOKEN:
                # Old format null marker -- treat as null (empty string)
                vals.append(NULL_TOKEN)
            elif v.startswith(_OLD_NULL_TOKEN) and len(v) > 1 and v[1:].isdigit():
                # Old format null RLE (#N) -- expand to N empty strings
                vals.extend([NULL_TOKEN] * int(v[1:]))
            else:
                vals.append(v)
        row = {}
        for idx, path in enumerate(field_order):
            if idx < len(vals):
                row[path] = _decode_field(vals[idx])
            else:
                # Trailing truncation: the encoder drops trailing absent
                # values; any position beyond the row's actual length is
                # implicitly absent.
                row[path] = ABSENT
        rows.append(row)   # position in this list IS the row's identity

    return table_code, field_order, array_order, array_path, rows, level_full_paths


def _unflatten(flat: dict) -> dict:
    root = {}
    for path, val in flat.items():
        parts = _split_path(path)
        node = root
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return root


def decode(text: str):
    """
    Decodes compact Twig text back to Python data. Returns a single dict
    if the text was produced by encode() on a single dict (signaled by a
    leading "~S" marker), or a list of dicts otherwise -- matching
    whatever shape was originally passed to encode().

    Supports both new compact markers (~L/~S) and old markers
    (@shape:list/@shape:single) for backward compatibility.
    """
    if not text:
        return []

    shape = "list"
    if text.startswith("~L"):
        text = text[3:]  # skip "~L\n"
        shape = "list"
    elif text.startswith("~S"):
        text = text[3:]  # skip "~S\n"
        shape = "single"
    elif text.startswith("@shape:"):
        marker_line, _, text = text.partition("\n")
        shape = marker_line[len("@shape:"):].strip()

    tables = {}
    for block in text.split(TABLE_SEP):
        block = block.strip("\n")
        if not block:
            continue
        table_code, field_order, array_order, array_path, rows, level_full_paths = _parse_table_block(block)
        tables[table_code] = (field_order, array_order, array_path, rows, level_full_paths)

    def _set_dotted(record, path, value):
        parts = _split_path(path)
        node = record
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value

    def build_record(table_code, row_index):
        field_order, array_order, array_path, rows, level_full_paths = tables[table_code]
        row = rows[row_index]
        # Skip ABSENT fields, and the "_parent"/"_idx"/"$has:"/"$lvl:"
        # bookkeeping fields, entirely -- not even setting them to None.
        # `is` comparison for ABSENT is intentional: it's a specific
        # sentinel object, never a value that could equal it by coincidence.
        flat = {
            path: val for path, val in row.items()
            if not (path in ("_parent", "_idx") or path.startswith("$has:") or path.startswith("$lvl:"))
            and val is not ABSENT
        }
        record = _unflatten(flat)

        # Level (branch) presence: force-create an empty dict for a
        # branch that's flagged present but has none of its own leaves
        # set (an empty dict has no leaf field to have carried this
        # information any other way). Skipped if the branch already got
        # created by some leaf under it -- this only fills the gap for
        # the genuinely-empty-dict case. Old Twig text without "$lvl:"
        # flags (predating this fix) simply has no such entries in
        # `row`, so this loop does nothing for it -- falls back to the
        # previous behavior (an empty-dict branch collapses to absent).
        for path, val in row.items():
            if not path.startswith("$lvl:") or val is not True:
                continue
            code = path[len("$lvl:"):]
            branch_path = level_full_paths.get(code)
            if branch_path is None:
                continue
            found, _ = _resolve_path(record, branch_path)
            if not found:
                _set_dotted(record, branch_path, {})

        for acode in array_order:
            # Array presence: was this array key in the source record at
            # all? Missing "$has:" entries (old Twig text predating this
            # fix) default to True, preserving the previous behavior of
            # always setting the array (never omitting it).
            has_flag = row.get(f"$has:{acode}", True)
            if has_flag is False:
                continue  # genuinely absent -- do not set this key at all

            child_table_code = acode  # array field code doubles as child table code (t1, t2...)
            arr_field_path = array_path[acode]
            if child_table_code not in tables:
                record_items = []
            else:
                _, _, _, c_rows, _ = tables[child_table_code]
                matching = [
                    (r["_idx"], i)
                    for i, r in enumerate(c_rows)
                    if r.get("_parent") == row_index
                ]
                matching.sort(key=lambda x: x[0])
                record_items = [build_record(child_table_code, i) for _, i in matching]
            _set_dotted(record, arr_field_path, record_items)

        return record

    _, _, _, root_rows, _ = tables["root"]
    result = [build_record("root", i) for i in range(len(root_rows))]

    if shape == "single":
        return result[0] if result else {}
    return result
