"""Tests for arrays nested inside arrays (and mixed with deep dicts),
including globally-unique table-code assignment across recursion depth.
Run with: pytest tests/test_nested_arrays.py -v
"""

from twig.codec import encode, decode


def roundtrip(data):
    return decode(encode(data))


def test_array_nested_inside_array_with_empty_case():
    data = [
        {
            "name": "ffs",
            "orders": [
                {
                    "orderId": "O1",
                    "items": [
                        {"sku": "A1", "qty": 2, "price": 100},
                        {"sku": "A2", "qty": 1, "price": 250},
                    ],
                },
                {
                    "orderId": "O2",
                    "items": [{"sku": "B1", "qty": 5, "price": 20}],
                },
            ],
        },
        {
            "name": "raj",
            "orders": [{"orderId": "O3", "items": []}],  # empty nested array
        },
    ]
    assert roundtrip(data) == data


def test_scalar_list_and_array_of_dicts_at_same_depth():
    data = [{
        "name": "test",
        "profile": {
            "region": {
                "zone": {
                    "tags": ["vip", "priority", "new"],
                    "history": [
                        {"event": "signup", "year": 2020},
                        {"event": "upgrade", "year": 2022},
                    ],
                }
            }
        },
    }]
    assert roundtrip(data) == data


def test_triple_nested_arrays():
    data = [{
        "name": "org",
        "departments": [
            {
                "deptName": "Engineering",
                "teams": [
                    {
                        "teamName": "Backend",
                        "members": [
                            {"person": "Alice", "role": "lead"},
                            {"person": "Bob", "role": "dev"},
                        ],
                    },
                    {
                        "teamName": "Frontend",
                        "members": [{"person": "Carol", "role": "dev"}],
                    },
                ],
            },
            {"deptName": "Sales", "teams": []},
        ],
    }]
    assert roundtrip(data) == data


def test_table_codes_stay_globally_unique_across_recursion():
    """Regression test for a real bug: table codes (t1, t2...) were
    assigned LOCALLY within each recursive call, so two unrelated array
    fields at different nesting depths could both get named 't1' and
    collide in the decoder's flat table lookup. This specifically
    exercises two sibling-level array fields plus one nested-inside-array
    field, which triggers the collision if the fix regresses."""
    data = [{
        "name": "collision_check",
        "fieldA": [{"x": 1}, {"x": 2}],
        "fieldB": [
            {"y": 1, "nested": [{"z": 1}, {"z": 2}]},
        ],
    }]
    assert roundtrip(data) == data
