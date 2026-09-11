"""
LangChain & LLM Context Compression Integration for Twig.

Provides utilities to format retrieved documents, tool outputs, and structured data
into compact Twig format, cutting prompt tokens by 50-70% in RAG and Agent pipelines.
"""

from __future__ import annotations

from typing import Any, Sequence
from ..codec import encode as twig_encode

TWIG_SYSTEM_PROMPT_PREFIX = (
    "The following data is serialized in Twig format (a token-efficient tabular representation "
    "where schema and nested trees are declared once, and columns are pipe-delimited).\n\n"
)


def format_docs_as_twig(
    documents: Sequence[Any],
    include_metadata: bool = True,
    page_content_key: str = "content",
) -> str:
    """Formats a list of LangChain Document objects or dictionaries into compact Twig.

    Args:
        documents: A list of LangChain Document instances or dicts.
        include_metadata: Whether to include metadata keys from Document.metadata.
        page_content_key: The field name to assign to Document.page_content.

    Returns:
        A compact Twig string representing the documents.
    """
    records: list[dict[str, Any]] = []

    for doc in documents:
        if hasattr(doc, "page_content"):
            # LangChain Document object
            rec: dict[str, Any] = {page_content_key: doc.page_content}
            if include_metadata and hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
                for k, v in doc.metadata.items():
                    if k != page_content_key:
                        rec[k] = v
            records.append(rec)
        elif isinstance(doc, dict):
            records.append(doc)
        else:
            records.append({page_content_key: str(doc)})

    if not records:
        return ""

    return twig_encode(records)


def to_prompt_context(
    data: Any,
    include_instructions: bool = False,
) -> str:
    """Encodes arbitrary structured data into Twig with optional LLM context guidance.

    Args:
        data: A dict, list of dicts, or JSON-compatible structured object.
        include_instructions: If True, prepends a brief explanation for the LLM.

    Returns:
        Twig string, optionally prepended with format explanation.
    """
    encoded = twig_encode(data)
    if include_instructions:
        return TWIG_SYSTEM_PROMPT_PREFIX + encoded
    return encoded


class TwigDocumentCompressor:
    """Document compressor for LangChain RAG pipelines.

    Usage with LangChain LCEL:
        compressor = TwigDocumentCompressor()
        rag_chain = retriever | compressor | prompt_template | llm
    """

    def __init__(
        self,
        include_metadata: bool = True,
        page_content_key: str = "content",
        include_instructions: bool = True,
    ) -> None:
        self.include_metadata = include_metadata
        self.page_content_key = page_content_key
        self.include_instructions = include_instructions

    def compress_documents(
        self,
        documents: Sequence[Any],
        query: str | None = None,
    ) -> str:
        """Compresses retrieved documents into a single compact Twig context string."""
        twig_text = format_docs_as_twig(
            documents,
            include_metadata=self.include_metadata,
            page_content_key=self.page_content_key,
        )
        if self.include_instructions and twig_text:
            return TWIG_SYSTEM_PROMPT_PREFIX + twig_text
        return twig_text

    def __call__(self, documents: Sequence[Any]) -> str:
        return self.compress_documents(documents)
