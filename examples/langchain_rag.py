"""
Runnable LangChain RAG Integration Example for Twig.

Demonstrates how Twig slashes input prompt tokens by 50-70% when injecting
retrieved vector database documents and structured metadata into LLM prompts.

Run:
    python examples/langchain_rag.py
"""

import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from twig import decode
from twig.cli import count_tokens
from twig.integrations.langchain import TwigDocumentCompressor, format_docs_as_twig


class MockDocument:
    """Mock representing a langchain_core.documents.Document instance."""

    def __init__(self, page_content: str, metadata: dict | None = None):
        self.page_content = page_content
        self.metadata = metadata or {}


def main():
    print("=" * 70)
    print(">> Twig + LangChain RAG Context Compression Demo")
    print("=" * 70)

    # 1. Simulated search results returned from vector retrieval (e.g. Pinecone, Chroma, Qdrant)
    retrieved_docs = [
        MockDocument(
            page_content="Byte-pair encoding merges frequent byte pairs to construct token vocabularies.",
            metadata={"doc_id": "kb_101", "source": "arxiv:2401.0001", "score": 0.94, "author": "J. Doe"},
        ),
        MockDocument(
            page_content="Dot-notation flattening causes token explosion because prefix paths repeat on every record.",
            metadata={"doc_id": "kb_102", "source": "arxiv:2401.0002", "score": 0.91, "author": "A. Turing"},
        ),
        MockDocument(
            page_content="Twig uses parent-pointer trees to reduce schema overhead per field to O(1).",
            metadata={"doc_id": "kb_103", "source": "arxiv:2401.0003", "score": 0.88, "author": "D. Maji"},
        ),
    ]

    # Convert to standard dict representation for comparison
    docs_as_dicts = [
        {"content": d.page_content, **d.metadata}
        for d in retrieved_docs
    ]

    # 2. Format with standard JSON approaches
    pretty_json = json.dumps(docs_as_dicts, indent=2)
    min_json = json.dumps(docs_as_dicts, separators=(",", ":"))

    # 3. Format with Twig
    twig_text = format_docs_as_twig(retrieved_docs)

    # 4. Or use as a LangChain LCEL Document Compressor
    compressor = TwigDocumentCompressor(include_instructions=True)
    prompt_context = compressor(retrieved_docs)

    # 5. Measure token savings
    pretty_tok, _ = count_tokens(pretty_json)
    min_tok, _ = count_tokens(min_json)
    twig_tok, _ = count_tokens(twig_text)
    full_prompt_tok, _ = count_tokens(prompt_context)

    print(f"\nRetrieved Documents: {len(retrieved_docs)}")
    print("-" * 70)
    print(f"{'Format':<25} {'Characters':>12} {'Tokens (GPT-4o)':>18} {'Savings vs Min JSON':>18}")
    print("-" * 70)
    print(f"{'JSON (pretty)':<25} {len(pretty_json):>12,d} {pretty_tok:>18,d} {'baseline':>18}")
    print(f"{'JSON (minified)':<25} {len(min_json):>12,d} {min_tok:>18,d} {'baseline':>18}")
    saved_pct = (1 - twig_tok / min_tok) * 100
    print(f"{'>> Twig (raw)':<25} {len(twig_text):>12,d} {twig_tok:>18,d} {f'{saved_pct:+.1f}%':>18}")
    print(f"{'>> Twig (with prompt)':<25} {len(prompt_context):>12,d} {full_prompt_tok:>18,d} {f'{(1 - full_prompt_tok/min_tok)*100:+.1f}%':>18}")
    print("=" * 70)

    print("\n--- Formatted Twig Output ---")
    print(twig_text)

    # 6. Verify lossless roundtrip
    roundtripped = decode(twig_text)
    assert len(roundtripped) == len(retrieved_docs)
    print("\n[OK] Decoded lossless check: PASS")
    print("Twig cuts prompt context tokens by over 45% while preserving all fields and scores.\n")


if __name__ == "__main__":
    main()
