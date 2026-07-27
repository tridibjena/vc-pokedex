"""Text chunking for the vector store."""
from loguru import logger

from config.settings import settings


def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """Split text into overlapping windows.

    Guards against overlap >= size, which would make the stride zero or negative
    and loop forever.
    """
    size = size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    if size <= 0:
        raise ValueError("chunk size must be positive")

    stride = size - overlap
    if stride <= 0:
        logger.warning(
            f"chunk_overlap ({overlap}) >= chunk_size ({size}); falling back to a "
            f"10% overlap to avoid a zero stride."
        )
        stride = max(1, size // 10 * 9)

    chunks = []
    start = 0
    n = len(text)
    while start < n:
        chunks.append(text[start : start + size])
        start += stride
    return chunks
