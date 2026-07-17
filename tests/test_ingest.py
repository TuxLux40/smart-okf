"""Tests for the ingest pipeline's reserved-filename guard."""

from pathlib import Path

import pytest

from app.exceptions import DocumentIngestError
from app.services.ingest import co_located_markdown_path, ingest_document_file


class _StubLLMClient:
    def extract_structured(self, raw_text: str, context: str = "") -> str:
        return "---\ntype: Fact\n---\n\nBody"


@pytest.mark.parametrize("stem", ["index", "log"])
def test_ingest_rejects_reserved_companion_filename(tmp_path: Path, stem: str) -> None:
    source = tmp_path / f"{stem}.txt"
    source.write_text("raw content", encoding="utf-8")

    with pytest.raises(DocumentIngestError, match="reserved"):
        ingest_document_file(source, tmp_path, _StubLLMClient())  # type: ignore[arg-type]


def test_co_located_markdown_path_is_stem_plus_md(tmp_path: Path) -> None:
    source = tmp_path / "contract.pdf"
    assert co_located_markdown_path(source) == tmp_path / "contract.md"
