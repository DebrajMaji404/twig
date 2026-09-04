"""
Twig -- a token-efficient text encoding for nested JSON, built for
sending structured data to LLMs cheaply.

    from twig import encode, decode

    text = encode(my_json_list_or_dict)   # -> compact string
    data = decode(text)                    # -> list[dict], round-trips exactly

See README.md for full documentation, benchmarks, and known limitations.
"""

from .codec import encode, decode

__version__ = "0.1.0"
__all__ = ["encode", "decode"]
