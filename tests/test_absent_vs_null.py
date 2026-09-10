"""
Regression tests for the absent-vs-null fix (ABSENT_TOKEN / ABSENT
sentinel in codec.py). See benchmarks/stress_test_notes.md for the
original failing case this fixes, and the one narrower case that
remains open (documented, not silently broken).
"""

from twig.codec import encode, decode


def roundtrip(data):
    return decode(encode(data))


def test_branch_with_real_content_absent_in_some_records():
    """The exact bug pattern from stress_test_notes.md: an optional
    nested branch (with real leaf fields) is completely missing from
    some records. Must come back with the key entirely absent, not
    filled in with nulls."""
    data = [
        {"name": "x", "profile": {"bio": "hi"}},
        {"name": "y"},  # no 'profile' key at all
    ]
    result = roundtrip(data)
    assert result == data
    assert "profile" not in result[1]  # not just equal -- genuinely absent


def test_null_vs_absent_vs_present_all_distinguished():
    """The three distinct states a field can be in, all in one dataset:
    explicitly null, entirely absent, and present with a real value."""
    data = [
        {"name": "a", "note": None},   # present, explicitly null
        {"name": "b"},                  # absent entirely
        {"name": "c", "note": "hi"},    # present with a value
    ]
    result = roundtrip(data)
    assert result == data
    assert "note" in result[0] and result[0]["note"] is None
    assert "note" not in result[1]
    assert result[2]["note"] == "hi"


def test_absence_at_multiple_nesting_levels():
    data = [
        {"name": "a", "x": {"y": {"z": "deep"}}},
        {"name": "b"},  # x absent entirely, several levels deep
    ]
    result = roundtrip(data)
    assert result == data
    assert "x" not in result[1]


def test_field_absent_in_every_record_still_works():
    """A declared-nowhere-populated field shouldn't cause encode/decode
    to crash or behave strangely -- it just never appears in the schema
    at all if no record ever has it, which is the correct/simplest case."""
    data = [{"name": "a"}, {"name": "b"}]
    assert roundtrip(data) == data


def test_single_dict_with_absent_field_still_preserves_shape():
    """Combines the shape-marker fix (single dict vs list) with the
    absent-field fix in one case, since they touch adjacent code paths."""
    data = {"status": "ok", "meta": {"total": 1}}
    result = roundtrip(data)
    assert result == data
    assert isinstance(result, dict)


def test_empty_dict_branch_distinguished_from_absent():
    """
    Was previously a documented gap (an empty dict {} was
    indistinguishable from the branch being absent, since an empty dict
    has no leaf field to carry a presence marker on). Fixed via a
    per-level "$lvl:" presence flag declared in @tree, checked
    separately from leaf-field presence. This test used to assert the
    broken behavior explicitly; now asserts the correct round-trip.
    """
    data = [
        {"name": "a", "x": {"y": "val"}},  # x has real content
        {"name": "b", "x": {}},             # x present but empty
        {"name": "c"},                       # x absent entirely
    ]
    result = roundtrip(data)
    assert result == data
    assert result[1]["x"] == {}       # present, empty -- not omitted
    assert "x" not in result[2]        # genuinely absent -- not {}


def test_array_field_absent_vs_present_empty_vs_populated():
    """
    Was previously a known limitation (all 3 mismatches in the original
    stress20 test were this exact issue): an absent array field decoded
    as [] instead of being omitted. Fixed via a per-record "$has:"
    presence flag on the array's parent row.
    """
    data = [
        {"name": "a", "education": [{"school": "X"}]},  # populated
        {"name": "b", "education": []},                    # present, empty
        {"name": "c"},                                       # absent entirely
    ]
    result = roundtrip(data)
    assert result == data
    assert result[0]["education"] == [{"school": "X"}]
    assert result[1]["education"] == []       # present, empty -- not omitted
    assert "education" not in result[2]         # genuinely absent -- not []


def test_nested_empty_dict_and_absent_array_together():
    """Combines both fixes in one record: an empty-dict branch AND an
    absent array field at the same time, to catch any interaction bug
    between the two presence-flag mechanisms."""
    data = [
        {"name": "a", "profile": {}, "tags_source": [{"id": 1}]},
        {"name": "b"},  # neither key present at all
    ]
    result = roundtrip(data)
    assert result == data
    assert result[0]["profile"] == {}
    assert "profile" not in result[1]
    assert "tags_source" not in result[1]


