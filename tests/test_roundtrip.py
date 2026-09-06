"""Round-trip correctness tests: decode(encode(x)) == x, for progressively
messier data. Run with: pytest tests/test_roundtrip.py -v
"""

from twig.codec import encode, decode


def roundtrip(data):
    return decode(encode(data))


def test_real_dataset_two_people():
    data = [
        {
            "name": "ffs",
            "address": {
                "present": {"state": "West Bengal", "district": "Paschim Bardhaman",
                             "block": "Block-4", "landmark": "near temple", "pin": "713201"},
                "permanent": {"state": "West Bengal", "district": "Paschim Bardhaman",
                              "block": "Block-2", "landmark": "near school", "pin": "713301"},
            },
            "experience": [
                {"companyName": "Tata Steel", "role": "Engineer", "years": 2,
                 "state": "Jharkhand", "district": "East Singhbhum",
                 "block": "Block-9", "landmark": "near river"},
                {"companyName": "Infosys", "role": "Developer", "years": 3,
                 "state": "Karnataka", "district": "Bangalore Urban",
                 "block": "Block-1", "landmark": "near lake"},
            ],
        },
        {
            "name": "raj",
            "address": {
                "present": {"state": "Bihar", "district": "Patna",
                             "block": "Block-7", "landmark": "near market", "pin": "800001"},
                "permanent": {"state": "Bihar", "district": "Gaya",
                              "block": "Block-3", "landmark": "near well", "pin": "823001"},
            },
            "experience": [
                {"companyName": "Wipro", "role": "Analyst", "years": 1,
                 "state": "Telangana", "district": "Hyderabad",
                 "block": "Block-5", "landmark": "near park"},
            ],
        },
    ]
    assert roundtrip(data) == data


def test_values_containing_comma_pipe_colon():
    data = [{
        "name": "test1",
        "address": {
            "present": {"state": "WB", "district": "X", "block": "B1",
                         "landmark": "near Ram, Shyam shop | opp: temple gate", "pin": "700001"},
            "permanent": {"state": "WB", "district": "X", "block": "B1",
                          "landmark": "corner, of 5th & 6th | block::9", "pin": "700002"},
        },
        "experience": [
            {"companyName": "A, B & Co. | Pvt::Ltd", "role": "Eng,ineer", "years": 4,
             "state": "S", "district": "D", "block": "B", "landmark": "L"},
        ],
    }]
    assert roundtrip(data) == data


def test_unicode():
    data = [{
        "name": "রাজ কুমার 😀",
        "address": {
            "present": {"state": "पश्चिम बंगाल", "district": "দুর্গাপুর", "block": "ব-৪",
                         "landmark": "মন্দিরের কাছে", "pin": "713201"},
            "permanent": {"state": "बिहार", "district": "पटना", "block": "B-2",
                          "landmark": "स्कूल के पास", "pin": "800001"},
        },
        "experience": [
            {"companyName": "Zürich Insurance & Co.", "role": "工程师", "years": 5,
             "state": "S", "district": "D", "block": "B", "landmark": "近い川"},
        ],
    }]
    assert roundtrip(data) == data


def test_nulls_empty_strings_leading_zero_pins():
    data = [{
        "name": "empty test",
        "address": {
            "present": {"state": "WB", "district": None, "block": "",
                         "landmark": "near 0042 gate", "pin": "00713"},
            "permanent": {"state": "WB", "district": "D2", "block": "B2",
                          "landmark": "", "pin": "0"},
        },
        "experience": [],
    }]
    assert roundtrip(data) == data


def test_delimiter_characters_inside_values():
    """Values that contain the format's OWN delimiters (| ; ~ ^ \\)."""
    data = [{
        "name": "delim|test;name~with>chars^and\\backslash",
        "address": {
            "present": {"state": "A|B", "district": "C;D", "block": "E~F",
                         "landmark": "G>H^I", "pin": "700001"},
            "permanent": {"state": "back\\slash\\test", "district": "quote'mark",
                          "block": "B2", "landmark": "L2", "pin": "700002"},
        },
        "experience": [
            {"companyName": "A|B;C~D>E^F Co.", "role": "eng\\ineer", "years": 4,
             "state": "S", "district": "D", "block": "B", "landmark": "L"},
        ],
    }]
    assert roundtrip(data) == data


def test_fifty_records_varying_experience_lengths():
    many = []
    for i in range(50):
        many.append({
            "name": f"person{i}",
            "address": {
                "present": {"state": "S", "district": "D", "block": f"B{i}",
                             "landmark": f"landmark {i}, with comma", "pin": f"{700000+i}"},
                "permanent": {"state": "S2", "district": "D2", "block": f"B{i+1}",
                              "landmark": f"landmark {i}b", "pin": f"{800000+i}"},
            },
            "experience": [
                {"companyName": f"Co{j}", "role": "R", "years": j,
                 "state": "S", "district": "D", "block": "B", "landmark": "L"}
                for j in range(i % 3)  # 0, 1, or 2 items -- varying lengths incl. empty
            ],
        })
    assert roundtrip(many) == many


def test_single_item_and_empty_scalar_lists():
    """Regression test for a real bug: a single-item list and a plain
    scalar produced identical encoded output without an explicit list
    marker, and an empty list was indistinguishable from an empty string."""
    data = [
        {"name": "a", "tags": ["priority"]},
        {"name": "b", "tags": []},
        {"name": "c", "tags": ["x", "y", "z"]},
    ]
    assert roundtrip(data) == data


def test_single_dict_input_returns_single_dict_not_a_list():
    """Regression test for a real bug (found via live user testing): a
    single JSON object passed to encode() -- not a list -- came back
    from decode() wrapped in an extra list it never had, e.g.
    {"status": "ok", ...} became [{"status": "ok", ...}]. encode() now
    records whether the original input was a single dict or a list via
    a leading @shape: marker, and decode() restores the correct shape."""
    data = {
        "status": "success",
        "meta": {"current_page": 1, "per_page": 10, "total_records": 450},
        "data": [
            {"id": "usr_901", "name": "Alice Smith", "created_at": "2026-09-01T10:14:00Z"},
            {"id": "usr_902", "name": "Bob Jones", "created_at": "2026-09-02T11:22:00Z"},
        ],
    }
    result = roundtrip(data)
    assert result == data
    assert isinstance(result, dict)  # not wrapped in a list


def test_shape_marker_backward_compatible_with_unmarked_text():
    """Twig text without a leading @shape: marker (hand-written, or from
    a version of this codec predating the fix above) has no way to know
    the original shape, so it falls back to the historical default of
    always returning a list -- this is a deliberate, documented default,
    not a silent behavior change for existing unmarked text."""
    manual_text = "table:root\n@types\nname\n@rows\nffs"
    result = decode(manual_text)
    assert result == [{"name": "ffs"}]
    assert isinstance(result, list)
