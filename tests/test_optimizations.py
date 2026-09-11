"""
Unit tests for Value Dictionary (@dict), Short Character Exemption, Compact Booleans (T/F),
and Run-Length Absent Compression (!N).
"""

from twig.codec import encode, decode


def test_compact_booleans_roundtrip():
    data = [
        {"id": 1, "active": True, "verified": False},
        {"id": 2, "active": False, "verified": True},
    ]
    encoded = encode(data)
    assert "|T|" in encoded or "|F|" in encoded or encoded.endswith("|T") or encoded.endswith("|F")
    assert "true" not in encoded
    assert "false" not in encoded
    decoded = decode(encoded)
    assert decoded == data


def test_short_char_not_tokenized():
    # Single char 'A' and 2-char 'AA' repeated many times should NOT be in @dict
    data = [{"code": "A", "group": "AA"} for _ in range(10)]
    encoded = encode(data)
    assert "@dict" not in encoded
    decoded = decode(encoded)
    assert decoded == data


def test_word_used_once_not_tokenized():
    # Word used only once should NOT be in @dict
    data = [
        {"id": 1, "title": "UniqueTitleOne"},
        {"id": 2, "title": "UniqueTitleTwo"},
    ]
    encoded = encode(data)
    assert "@dict" not in encoded
    decoded = decode(encoded)
    assert decoded == data


def test_repeating_words_tokenized_when_saving_bytes():
    # Word "Senior Software Engineer" repeated 5 times SHOULD be tokenized
    data = [{"title": "Senior Software Engineer", "dep": "Engineering & Product"} for _ in range(5)]
    encoded = encode(data)
    assert "@dict" in encoded
    assert "&0=Senior Software Engineer" in encoded or "&0=Engineering & Product" in encoded
    decoded = decode(encoded)
    assert decoded == data


def test_run_length_absent_compression():
    # Multiple interior absent fields should be compressed into !N
    data = [
        {"a": 1, "b": None, "c": None, "d": None, "e": 5},
        {"a": 2, "e": 6},  # b, c, d are absent in this row
    ]
    encoded = encode(data)
    decoded = decode(encoded)
    assert decoded == data


def test_string_literal_escapes_roundtrip():
    # Test literal strings starting with &, T, F, !, #, ' to ensure zero collisions
    data = [
        {"val": "&0"},
        {"val": "T"},
        {"val": "F"},
        {"val": "!3"},
        {"val": "#3"},
        {"val": "'quoted"},
    ]
    encoded = encode(data)
    decoded = decode(encoded)
    assert decoded == data


def test_run_length_null_compression():
    # Multiple interior explicit null fields should be encoded as empty fields (||)
    # BPE-aware optimization: |||| is 1 token vs |#|#|#| at 6+ tokens
    data = [
        {"a": 1, "b": None, "c": None, "d": None, "e": 5},
        {"a": 2, "b": None, "c": None, "d": 4, "e": 5},
    ]
    encoded = encode(data)
    # Consecutive nulls produce consecutive empty fields (|||)
    assert "|||" in encoded
    decoded = decode(encoded)
    assert decoded == data


def test_adaptive_tree_omitted_for_shallow_nesting():
    # Shallow depth-2 record where tree declaration cost exceeds leaf savings
    # should omit @tree and use direct dotted paths, saving header tokens
    data = [
        {"id": 1, "meta": {"code": "A1"}},
        {"id": 2, "meta": {"code": "A2"}},
    ]
    encoded = encode(data)
    assert "@tree" not in encoded
    assert "meta.code" in encoded
    decoded = decode(encoded)
    assert decoded == data


def test_pipe_separated_types_decode():
    # Twig text with pipe-separated fields in @types decodes correctly
    text = "@shape:list\ntable:root\n@types\nid|name\n@rows\n1|Alice\n2|Bob"
    decoded = decode(text)
    assert decoded == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

