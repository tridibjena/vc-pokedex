"""Reference-library ingestion: extraction, upload route, and Dex isolation."""
import io

import pytest

from tools.documents import (
    MAX_CHARS,
    UnreadableDocument,
    UnsupportedDocument,
    extract,
    is_supported,
)


class TestExtraction:
    def test_plain_text_round_trips(self):
        assert extract("memo.txt", b"ARR is $5M.") == "ARR is $5M."

    def test_markdown_is_supported(self):
        assert extract("deck.md", b"# Deck\n\nARR $5M") == "# Deck\n\nARR $5M"

    def test_utf16_decodes_via_its_bom(self):
        assert extract("notes.txt", "burn €40k".encode("utf-16")) == "burn €40k"

    def test_utf8_bom_is_stripped(self):
        data = "ARR $5M".encode("utf-8-sig")
        assert data.startswith(b"\xef\xbb\xbf")
        assert extract("notes.txt", data) == "ARR $5M"

    def test_latin1_falls_through_without_raising(self):
        # Undecodable as utf-8; must not lose the file.
        assert "caf" in extract("notes.txt", b"caf\xe9 metrics")

    def test_even_length_latin1_is_not_mistaken_for_utf16(self):
        """Regression: UTF-16 decoding never raises on an even-length input.

        Trying encodings in a try/except ladder therefore turned every
        even-length Latin-1 file into CJK mojibake, embedded it, and poisoned
        retrieval silently. Encoding is now chosen by BOM, not by trial.
        """
        data = b"caf\xe9 metrics"
        assert len(data) % 2 == 0, "the bug only reproduces on even-length input"
        assert "metrics" in extract("notes.txt", data)

    def test_unsupported_suffix_names_what_is_accepted(self):
        with pytest.raises(UnsupportedDocument) as exc:
            extract("model.xlsx", b"...")
        assert ".pdf" in str(exc.value)

    def test_no_suffix_is_rejected(self):
        with pytest.raises(UnsupportedDocument):
            extract("README", b"text")

    def test_empty_file_is_rejected(self):
        with pytest.raises(UnreadableDocument):
            extract("empty.txt", b"   \n  ")

    def test_oversized_text_is_truncated_not_rejected(self):
        text = extract("big.txt", b"a" * (MAX_CHARS + 5_000))
        assert len(text) == MAX_CHARS

    def test_is_supported_is_case_insensitive(self):
        assert is_supported("DECK.PDF")
        assert not is_supported("deck.key")


class TestPdfExtraction:
    """A PDF of images is the failure mode that matters — a scanned deck."""

    def test_scanned_pdf_says_so_rather_than_indexing_nothing(self, monkeypatch):
        import tools.documents as documents

        class _Page:
            def extract_text(self):
                return ""

        class _Pdf:
            pages = [_Page(), _Page()]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        fake = type("m", (), {"open": staticmethod(lambda _: _Pdf())})
        monkeypatch.setitem(__import__("sys").modules, "pdfplumber", fake)

        with pytest.raises(UnreadableDocument) as exc:
            documents.extract("deck.pdf", b"%PDF-1.4")
        # Must not silently produce an empty document that chat then answers
        # "not mentioned" against.
        assert "scan" in str(exc.value).lower()

    def test_encrypted_pdf_reports_the_reason(self, monkeypatch):
        import tools.documents as documents

        def _boom(_):
            raise ValueError("file has not been decrypted")

        fake = type("m", (), {"open": staticmethod(_boom)})
        monkeypatch.setitem(__import__("sys").modules, "pdfplumber", fake)

        with pytest.raises(UnreadableDocument) as exc:
            documents.extract("secret.pdf", b"%PDF-1.4")
        assert "decrypted" in str(exc.value)


@pytest.fixture
def client(monkeypatch):
    """TestClient with Mongo and the vector store faked out."""
    from fastapi.testclient import TestClient

    import api.routes.library as library

    saved: list[dict] = []
    indexed: list[tuple] = []

    class FakeMongo:
        async def save_library_doc(self, record):
            saved.append(record)
            return "objid"

        async def list_library_docs(self, limit=200):
            return list(saved)

        async def get_library_doc(self, file_id):
            return next((d for d in saved if d["file_id"] == file_id), None)

        async def set_library_status(self, file_id, status, error=None, **extra):
            for d in saved:
                if d["file_id"] == file_id:
                    d.update(status=status, error=error, **extra)

        async def delete_library_doc(self, file_id):
            before = len(saved)
            saved[:] = [d for d in saved if d["file_id"] != file_id]
            return len(saved) < before

    monkeypatch.setattr(library, "mongo_client", FakeMongo())
    monkeypatch.setattr(library, "upsert_chunks", lambda payload: (indexed.extend(payload), len(payload))[1])
    monkeypatch.setattr(library, "delete_by_file_id", lambda fid: 3)

    from api.main import app

    with TestClient(app) as c:
        c.saved = saved       # type: ignore[attr-defined]
        c.indexed = indexed   # type: ignore[attr-defined]
        yield c


class TestUploadRoute:
    def test_upload_indexes_and_returns_202(self, client):
        res = client.post(
            "/library/documents",
            files={"file": ("memo.md", io.BytesIO(b"# Memo\n\nARR is $5M."), "text/markdown")},
        )
        assert res.status_code == 202
        body = res.json()
        assert body["filename"] == "memo.md"
        assert body["status"] == "processing"

        # TestClient runs BackgroundTasks on response close, so by now the
        # chunks exist and the record has been flipped to complete.
        assert client.indexed, "background indexing never ran"
        assert client.saved[0]["status"] == "complete"

    def test_chunks_are_tagged_as_library(self, client):
        client.post(
            "/library/documents",
            files={"file": ("terms.txt", io.BytesIO(b"1x non-participating."), "text/plain")},
        )
        _, _, meta = client.indexed[0]
        assert meta["kind"] == "library"
        assert meta["file_id"]

    def test_unsupported_type_returns_415(self, client):
        res = client.post(
            "/library/documents",
            files={"file": ("model.xlsx", io.BytesIO(b"PK\x03\x04"), "application/vnd.ms-excel")},
        )
        assert res.status_code == 415

    def test_empty_file_returns_422_not_500(self, client):
        res = client.post(
            "/library/documents",
            files={"file": ("blank.txt", io.BytesIO(b"  "), "text/plain")},
        )
        assert res.status_code == 422

    def test_oversized_upload_returns_413(self, client, monkeypatch):
        from config.settings import settings

        monkeypatch.setattr(type(settings), "max_upload_bytes", property(lambda self: 32))
        res = client.post(
            "/library/documents",
            files={"file": ("big.txt", io.BytesIO(b"x" * 5000), "text/plain")},
        )
        assert res.status_code == 413

    def test_list_reports_accepted_types(self, client):
        res = client.get("/library/documents")
        assert res.status_code == 200
        assert ".pdf" in res.json()["accepted"]

    def test_delete_removes_record_and_chunks(self, client):
        upload = client.post(
            "/library/documents",
            files={"file": ("memo.txt", io.BytesIO(b"content here"), "text/plain")},
        ).json()

        res = client.delete(f"/library/documents/{upload['file_id']}")
        assert res.status_code == 200
        assert "3 chunk" in res.json()["message"]
        assert client.get("/library/documents").json()["total"] == 0

    def test_delete_unknown_returns_404(self, client):
        assert client.delete("/library/documents/nope").status_code == 404


class TestDexIsolation:
    """Uploads must not appear in the Dex as unscored silhouettes."""

    def test_library_writes_do_not_touch_the_documents_collection(self):
        import inspect

        import api.routes.library as library

        source = inspect.getsource(library)
        # `documents` backs the Dex grid; a library upload writing there would
        # render as a company stuck "scanning…" forever.
        assert "save_document_metadata" not in source
        assert "db.documents" not in source

    def test_library_prefix_is_not_swallowed_by_the_spa_catch_all(self):
        from api.main import API_PREFIXES

        assert "library" in API_PREFIXES
