"""
Text extraction for user-supplied reference documents.

Deliberately narrow: PDF and plain text. Anything else is rejected with a
message naming what is accepted, rather than indexed as mojibake that quietly
poisons retrieval.

pdfplumber (MIT, over pdfminer.six) rather than PyMuPDF: PyMuPDF is AGPL-3.0,
which would be incompatible with this repository's MIT licence. It is faster,
but extraction happens once per upload in a background task, so speed is not
the binding constraint here.
"""
import io
from pathlib import Path

from loguru import logger

PDF_SUFFIXES = {".pdf"}
TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".csv"}
SUPPORTED_SUFFIXES = PDF_SUFFIXES | TEXT_SUFFIXES

# Comfortably above a long fund memo, low enough that a pathological PDF cannot
# push a single record past what the embedder and Mongo will accept.
MAX_CHARS = 400_000


class UnsupportedDocument(Exception):
    """The file type is not one we can read."""


class UnreadableDocument(Exception):
    """The file type is right but no text came out of it."""


def suffix_of(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def is_supported(filename: str) -> bool:
    return suffix_of(filename) in SUPPORTED_SUFFIXES


def _extract_pdf(data: bytes) -> str:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise UnreadableDocument(
            "PDF support needs pdfplumber. Run: pip install -r requirements.txt"
        ) from exc

    pages: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
    except Exception as exc:
        # Password-protected and structurally broken files both land here.
        raise UnreadableDocument(f"Could not read this PDF: {exc}") from exc

    text = "\n\n".join(p for p in pages if p.strip())
    if not text.strip():
        # A scanned deck is a PDF of images. Say so, rather than indexing
        # nothing and letting chat answer "the document does not mention that".
        raise UnreadableDocument(
            "No selectable text in this PDF — it looks like a scan. "
            "OCR it first, or upload a text version."
        )
    return text


# UTF-16 must be selected by BOM, never by trial. Any even-length byte string
# decodes as UTF-16 without raising, so putting it in a try/except ladder turns
# every Latin-1 file with an even byte count into silent CJK mojibake — which
# then gets embedded and quietly poisons retrieval.
BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


def _extract_text(data: bytes) -> str:
    for bom, encoding in BOMS:
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError as exc:
                raise UnreadableDocument(
                    f"File declares a {encoding} byte-order mark but is not valid "
                    f"{encoding}: {exc}"
                ) from exc

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # Last resort. latin-1 maps every byte to a code point, so this cannot
        # raise; worst case a few characters are wrong rather than the whole
        # document being lost.
        logger.warning("Not valid UTF-8; falling back to latin-1.")
        return data.decode("latin-1")


def extract(filename: str, data: bytes) -> str:
    """Return the plain text of an uploaded document.

    Raises UnsupportedDocument for the wrong file type and UnreadableDocument
    when the type is right but yields nothing usable.
    """
    suffix = suffix_of(filename)
    if suffix not in SUPPORTED_SUFFIXES:
        accepted = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise UnsupportedDocument(
            f"'{suffix or filename}' is not supported. Accepted: {accepted}"
        )

    text = _extract_pdf(data) if suffix in PDF_SUFFIXES else _extract_text(data)
    text = text.strip()
    if not text:
        raise UnreadableDocument("The file is empty.")

    if len(text) > MAX_CHARS:
        logger.warning(f"'{filename}' truncated from {len(text)} to {MAX_CHARS} chars.")
        text = text[:MAX_CHARS]

    logger.info(f"Extracted {len(text)} chars from '{filename}'.")
    return text
