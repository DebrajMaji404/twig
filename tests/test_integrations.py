"""
Tests for Twig framework integrations (LangChain, Prompt context).
"""

import pytest
from twig import decode
from twig.integrations import format_docs_as_twig, TwigDocumentCompressor, to_prompt_context


class MockDocument:
    def __init__(self, page_content, metadata=None):
        self.page_content = page_content
        self.metadata = metadata or {}


def test_format_docs_as_twig_from_dicts():
    docs = [
        {"title": "Doc 1", "content": "Hello world", "score": 0.95},
        {"title": "Doc 2", "content": "Deep research", "score": 0.88},
    ]
    encoded = format_docs_as_twig(docs)
    assert "T:root" in encoded
    decoded = decode(encoded)
    assert decoded == docs


def test_format_docs_as_twig_from_mock_documents():
    docs = [
        MockDocument(page_content="Context passage 1", metadata={"source": "wiki", "id": 101}),
        MockDocument(page_content="Context passage 2", metadata={"source": "news", "id": 102}),
    ]
    encoded = format_docs_as_twig(docs)
    assert "T:root" in encoded
    decoded = decode(encoded)
    assert len(decoded) == 2
    assert decoded[0]["content"] == "Context passage 1"
    assert decoded[0]["source"] == "wiki"
    assert decoded[0]["id"] == 101


def test_twig_document_compressor():
    compressor = TwigDocumentCompressor(include_instructions=True)
    docs = [
        MockDocument(page_content="Twig reduces prompt tokens.", metadata={"author": "Debraj"}),
    ]
    compressed = compressor(docs)
    assert "The following data is serialized in Twig format" in compressed
    assert "T:root" in compressed


def test_to_prompt_context():
    data = {"status": "active", "code": 200}
    res = to_prompt_context(data, include_instructions=True)
    assert "serialized in Twig format" in res
    assert "~S" in res
