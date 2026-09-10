"""
Tests for LLM generation reliability.

Verifies that LLM-generated Twig text according to the specification
decodes with 100% fidelity into expected nested JSON structures,
handling escaping, tree structures, child tables, null compression,
and synthetic presence flags.
"""

import pytest
from twig import decode


def test_llm_gen_standard_tabular_and_lists():
    """LLM generation of flat tabular records with scalar lists and primitive types."""
    llm_twig = """table:root
@types
name
dept
title
salary
active
skills
@rows
Alice|Engineering|Manager|120000|true|*Python^Go
Bob|Design|Lead|110000|false|*Figma
"""
    expected = [
        {"name": "Alice", "dept": "Engineering", "title": "Manager", "salary": 120000, "active": True, "skills": ["Python", "Go"]},
        {"name": "Bob", "dept": "Design", "title": "Lead", "salary": 110000, "active": False, "skills": ["Figma"]}
    ]
    assert decode(llm_twig) == expected


def test_llm_gen_nested_tree():
    """LLM generation of nested objects using @tree parent-pointer hierarchy."""
    llm_twig = """table:root
@tree
l1=address^-
l2=present^l1
l3=permanent^l1
@types
id
name
l2.city
l2.state
l2.pin
l3.city
l3.state
l3.pin
@rows
101|Alice|Kolkata|West Bengal|'700001|Patna|Bihar|'800001
102|Bob|Mumbai|Maharashtra|'400001|Pune|Maharashtra|'411001
"""
    expected = [
        {
            "id": 101,
            "name": "Alice",
            "address": {
                "present": {"city": "Kolkata", "state": "West Bengal", "pin": "700001"},
                "permanent": {"city": "Patna", "state": "Bihar", "pin": "800001"},
            },
        },
        {
            "id": 102,
            "name": "Bob",
            "address": {
                "present": {"city": "Mumbai", "state": "Maharashtra", "pin": "400001"},
                "permanent": {"city": "Pune", "state": "Maharashtra", "pin": "411001"},
            },
        },
    ]
    result = decode(llm_twig)
    assert result == expected
    assert isinstance(result[0]["address"]["present"]["pin"], str)


def test_llm_gen_adversarial_escaping():
    """LLM generation containing reserved delimiters: |, ^, backslash, escaped nulls, and empty list."""
    llm_twig = r"""table:root
@types
user
comment
code
tag
empty_items
null_val
@rows
John\|Doe|Price: $50 \| 100\^2 \\ path|'1234|\#3|*|#
"""
    expected = [
        {
            "user": "John|Doe",
            "comment": r"Price: $50 | 100^2 \ path",
            "code": "1234",
            "tag": "#3",
            "empty_items": [],
            "null_val": None,
        }
    ]
    assert decode(llm_twig) == expected


def test_llm_gen_relational_child_tables():
    """LLM generation of nested arrays of objects using normalized linked tables."""
    llm_twig = """table:root
@types
orderId
customer
@arrays
a1=items
@rows
1|Alice
2|Bob
===
table:a1
@types
_parent
_idx
product
price
qty
@rows
0|0|Laptop|1200|1
0|1|Mouse|25|2
1|0|Keyboard|80|1
"""
    expected = [
        {
            "orderId": 1,
            "customer": "Alice",
            "items": [
                {"product": "Laptop", "price": 1200, "qty": 1},
                {"product": "Mouse", "price": 25, "qty": 2},
            ],
        },
        {
            "orderId": 2,
            "customer": "Bob",
            "items": [
                {"product": "Keyboard", "price": 80, "qty": 1},
            ],
        },
    ]
    assert decode(llm_twig) == expected


def test_llm_gen_single_object_shape():
    """LLM generation of a single object payload (@shape:single)."""
    llm_twig = """@shape:single
table:root
@types
status
code
healthy
notes
@rows
ok|200|true|#
"""
    expected = {
        "status": "ok",
        "code": 200,
        "healthy": True,
        "notes": None,
    }
    assert decode(llm_twig) == expected


def test_llm_gen_sparse_and_presence_flags():
    """LLM generation handling absent keys vs null/empty values using $has: and $lvl:."""
    llm_twig = """table:root
@tree
l1=meta^-
@types
$has:a1
$lvl:l1
id
l1.version
@arrays
a1=tags
@rows
false|true|1
false|false|2
true|false|3
===
table:a1
@types
_parent
_idx
tag
@rows
"""
    # Record 1 has empty meta {}, but missing tags key and missing version
    # Record 2 has missing meta, missing tags
    # Record 3 has missing meta, but present empty tags []
    expected = [
        {"id": 1, "meta": {}},
        {"id": 2},
        {"id": 3, "tags": []},
    ]
    assert decode(llm_twig) == expected


def test_llm_gen_consecutive_null_compression():
    """LLM generation with run-length null compression (#N)."""
    llm_twig = """table:root
@types
c1
c2
c3
c4
c5
@rows
start|#3|end
"""
    expected = [
        {"c1": "start", "c2": None, "c3": None, "c4": None, "c5": "end"}
    ]
    assert decode(llm_twig) == expected
