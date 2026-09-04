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

NULL_TOKEN = "#"
STR_MARK = "'"
NEWLINE_ESCAPE = ("\n", "\\n")  # (real, escaped) -- handled outside the
                                 # generic char-escape loop since a naive
                                 # replace of "\n" with "\\"+"\n" would still
                                 # contain a real newline

_SPECIAL_CHARS = (FIELD_SEP, LIST_SEP)
_NUM_RE = re.compile(r"-?[1-9]\d*|0")
_FLOAT_RE = re.compile(r"-?\d+\.\d+")


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
        return NULL_TOKEN
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        needs_mark = (
            v in ("true", "false", "")
            or v == NULL_TOKEN
            or v.startswith(LIST_MARK)
            or _NUM_RE.fullmatch(v)
            or _FLOAT_RE.fullmatch(v)
        )
        escaped = _escape(v)
        return (STR_MARK + escaped) if needs_mark else escaped
    return str(v)


def _str_to_scalar(s: str) -> Any:
    if s.startswith(STR_MARK):
        return _unescape(s[len(STR_MARK):])
    if s == NULL_TOKEN:
        return None
    if s == "":
        return ""
    if s == "true":
        return True
    if s == "false":
        return False
    if _NUM_RE.fullmatch(s):
        return int(s)
    if _FLOAT_RE.fullmatch(s):
        return float(s)
    return _unescape(s)


def _encode_field(v: Any) -> str:
    if isinstance(v, list):
        # LIST_MARK prefix is mandatory, not optional -- without it, a
        # single-item list and a plain scalar produce identical output
        # (no separator needed to join one item), and an empty list
        # produces "" indistinguishable from an empty string. Confirmed
        # as a real bug via the stress20 test before this fix.
        return LIST_MARK + LIST_SEP.join(_scalar_to_str(x) for x in v)
    return _scalar_to_str(v)


def _decode_field(s: str) -> Any:
    if s.startswith(LIST_MARK):
        content = s[len(LIST_MARK):]
        if content == "":
            return []
        pieces = _aware_split(content, LIST_SEP)
        return [_str_to_scalar(p) for p in pieces]
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
    A list is classified as a candidate "array of dicts" field if it's
    non-empty and contains dicts, OR if it's simply empty (ambiguous --
    resolved later by scanning across all rows/records, same fix applied
    to the original fixed-shape codec for this exact scenario: an empty
    list must not be silently misread as a scalar/empty-string). A
    non-empty list of plain scalars (e.g. tags) stays a scalar field,
    encoded with LIST_SEP as before.
    """
    scalars, lists = {}, {}
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            sub_s, sub_l = _deep_flatten(v, path)
            scalars.update(sub_s)
            lists.update(sub_l)
        elif isinstance(v, list) and (not v or isinstance(v[0], dict)):
            lists[path] = v
        else:
            scalars[path] = v
    return scalars, lists


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


def _build_tree(paths: list):
    """Parent-pointer tree over the dotted-path segments (excluding each
    path's own leaf name). Returns (level_parent, level_codes)."""
    level_parent = {}
    for p in paths:
        chain = p.split(".")[:-1]
        for i, seg in enumerate(chain):
            parent = chain[i - 1] if i > 0 else None
            level_parent[seg] = parent
    level_codes = {name: f"l{i+1}" for i, name in enumerate(level_parent.keys())}
    return level_parent, level_codes


def _immediate_level_and_leaf(path: str, level_codes: dict):
    chain = path.split(".")
    leaf = chain[-1]
    immediate = level_codes[chain[-2]] if len(chain) > 1 else None
    return immediate, leaf


# ---------------------------------------------------------------------------
# ENCODE
# ---------------------------------------------------------------------------

def _process_table(id_record_pairs, table_code, child_id_counter, table_id_counter, meta=None):
    """
    Encodes one table (root, or a child table spawned by a list-of-dicts
    field) and recursively encodes any tables it spawns. Returns a list of
    table-block strings (this table's block first, then descendants).

    `meta`, when given, is {row_id: {"_parent": parent_id, "_idx": idx}}
    for a CHILD table's own bookkeeping fields. These are kept structurally
    separate from each row's real data (never merged into the item dict
    itself) so they can never collide with -- or be double-counted
    alongside -- a real field of the same row.

    `table_id_counter` is a single counter SHARED across the entire
    recursion (not reset per call), so every child table gets a globally
    unique code. Without this, two different array fields at different
    nesting depths could both get named "t1" locally and collide in the
    decoder's flat table lookup -- exactly this bug was caught and fixed
    during testing (see test_nested_arrays.py).
    """
    flat_pairs = [(rid, *_deep_flatten(rec)) for rid, rec in id_record_pairs]
    scalar_paths, list_paths = _classify_paths(flat_pairs)

    is_child_table = meta is not None
    if is_child_table:
        scalar_paths = ["_parent", "_idx"] + scalar_paths

    all_paths_for_tree = [p for p in scalar_paths if p not in ("_parent", "_idx")] + list_paths
    level_parent, level_codes = _build_tree(all_paths_for_tree)

    tree_lines = []
    for name, parent in level_parent.items():
        parent_code = level_codes[parent] if parent else "-"
        tree_lines.append(f"{level_codes[name]}={name}^{parent_code}")

    field_codes = {p: f"f{i+1}" for i, p in enumerate(scalar_paths)}
    type_lines = []
    for p in scalar_paths:
        if p in ("_parent", "_idx"):
            type_lines.append(f"{field_codes[p]}=-.{p}")
            continue
        lvl, leaf = _immediate_level_and_leaf(p, level_codes)
        type_lines.append(f"{field_codes[p]}={lvl or '-'}.{leaf}")

    array_codes = {}
    array_lines = []
    for p in list_paths:
        tcode = f"t{next(table_id_counter)}"   # globally unique, not local
        array_codes[p] = tcode
        lvl, leaf = _immediate_level_and_leaf(p, level_codes)
        array_lines.append(f"{tcode}={lvl or '-'}.{leaf}")

    row_lines = []
    for rid, sc, ls in flat_pairs:
        real_paths = [p for p in scalar_paths if p not in ("_parent", "_idx")]
        # A path classified globally as "scalar" can still have landed in
        # THIS row's `ls` bucket if this specific row's value was an empty
        # list (_deep_flatten routes ALL empty lists to `ls` per-row,
        # before the global scalar-vs-array classification is known). Fall
        # back to `ls` so an empty-list value isn't silently lost as None.
        # Confirmed as a real bug via stress20 testing before this fix.
        def _lookup(p):
            if p in sc:
                return sc[p]
            if p in ls:
                return ls[p]
            return None
        vals = [_encode_field(_lookup(p)) for p in real_paths]
        if is_child_table:
            m = meta[rid]
            vals = [_encode_field(m["_parent"]), _encode_field(m["_idx"])] + vals
        row_lines.append(f"{rid}::" + FIELD_SEP.join(vals))

    block = f"table:{table_code}\n"
    if tree_lines:
        block += "@tree\n" + "\n".join(tree_lines) + "\n"
    block += "@types\n" + "\n".join(type_lines) + "\n"
    if array_lines:
        block += "@arrays\n" + "\n".join(array_lines) + "\n"
    block += "@rows\n" + "\n".join(row_lines)

    blocks = [block]

    for lpath in list_paths:
        tcode = array_codes[lpath]
        child_pairs = []
        child_meta = {}
        for rid, _, ls in flat_pairs:
            items = ls.get(lpath) or []
            for idx, item in enumerate(items):
                child_id = f"i{next(child_id_counter)}"
                child_pairs.append((child_id, item))
                child_meta[child_id] = {"_parent": rid, "_idx": idx}
        blocks.extend(_process_table(child_pairs, tcode, child_id_counter, table_id_counter, meta=child_meta))

    return blocks


def encode(data) -> str:
    records = data if isinstance(data, list) else [data]
    if not records:
        return ""
    ids = [f"s{i+1}" for i in range(len(records))]
    id_record_pairs = list(zip(ids, records))
    child_id_counter = itertools.count(1)
    table_id_counter = itertools.count(1)
    blocks = _process_table(id_record_pairs, "root", child_id_counter, table_id_counter, meta=None)
    return TABLE_SEP.join(blocks)


# ---------------------------------------------------------------------------
# DECODE
# ---------------------------------------------------------------------------

def _parse_table_block(block: str):
    lines = block.split("\n")
    assert lines[0].startswith("table:")
    table_code = lines[0][len("table:"):]

    sections = {}
    current = None
    for line in lines[1:]:
        if line.startswith("@"):
            current = line[1:]
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    level_name, level_parent_code = {}, {}
    for line in sections.get("tree", []):
        if not line:
            continue
        code, rest = line.split("=", 1)
        name, parent_code = rest.split("^", 1)
        level_name[code] = name
        level_parent_code[code] = None if parent_code == "-" else parent_code

    def full_path(lvl_code, leaf):
        chain = []
        code = lvl_code
        while code:
            chain.append(level_name[code])
            code = level_parent_code.get(code)
        return ".".join(list(reversed(chain)) + [leaf])

    field_path = {}
    field_order = []
    for line in sections.get("types", []):
        if not line:
            continue
        fcode, rest = line.split("=", 1)
        lvl, leaf = rest.rsplit(".", 1)
        field_path[fcode] = leaf if lvl == "-" else full_path(lvl, leaf)
        field_order.append(fcode)

    array_path = {}
    array_order = []
    for line in sections.get("arrays", []):
        if not line:
            continue
        acode, rest = line.split("=", 1)
        lvl, leaf = rest.rsplit(".", 1)
        array_path[acode] = leaf if lvl == "-" else full_path(lvl, leaf)
        array_order.append(acode)

    rows = {}
    for line in sections.get("rows", []):
        if not line or "::" not in line:
            continue
        rid, valstr = line.split("::", 1)
        vals = _aware_split(valstr, FIELD_SEP) if valstr else []
        row = {}
        for fcode, v in zip(field_order, vals):
            row[fcode] = _decode_field(v)
        rows[rid] = row

    return table_code, field_path, array_order, array_path, rows


def _unflatten(flat: dict) -> dict:
    root = {}
    for path, val in flat.items():
        parts = path.split(".")
        node = root
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val
    return root


def decode(text: str) -> list:
    if not text:
        return []

    tables = {}
    for block in text.split(TABLE_SEP):
        block = block.strip("\n")
        if not block:
            continue
        table_code, field_path, array_order, array_path, rows = _parse_table_block(block)
        tables[table_code] = (field_path, array_order, array_path, rows)

    def build_record(table_code, rid):
        field_path, array_order, array_path, rows = tables[table_code]
        row = rows[rid]
        flat = {}
        for fcode, path in field_path.items():
            if path in ("_parent", "_idx"):
                continue
            flat[path] = row.get(fcode)
        record = _unflatten(flat)

        for acode in array_order:
            child_table_code = acode  # array field code doubles as child table code (t1, t2...)
            arr_field_path = array_path[acode]
            if child_table_code not in tables:
                record_items = []
            else:
                c_field_path, c_array_order, c_array_path, c_rows = tables[child_table_code]
                # find _parent/_idx field codes in child table
                parent_fcode = idx_fcode = None
                for fc, p in c_field_path.items():
                    if p == "_parent":
                        parent_fcode = fc
                    elif p == "_idx":
                        idx_fcode = fc
                matching = [
                    (int(_str_to_scalar_safe(r[idx_fcode])), crid)
                    for crid, r in c_rows.items()
                    if r.get(parent_fcode) == rid
                ]
                matching.sort(key=lambda x: x[0])
                record_items = [build_record(child_table_code, crid) for _, crid in matching]
            _set_dotted(record, arr_field_path, record_items)

        return record

    def _set_dotted(record, path, value):
        parts = path.split(".")
        node = record
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value

    def _str_to_scalar_safe(v):
        return v if not isinstance(v, str) else v

    root_field_path, root_array_order, root_array_path, root_rows = tables["root"]
    return [build_record("root", rid) for rid in root_rows.keys()]
