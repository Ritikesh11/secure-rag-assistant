from pathlib import Path

from app.ingest import document_title, parse_metadata


def test_parse_metadata_from_folder_path() -> None:
    path = Path("data/sample_docs/marketing/confidential/brand-and-content-calendar.md")

    metadata = parse_metadata(path)

    assert metadata["department"] == "marketing"
    assert metadata["classification"] == "confidential"
    assert metadata["title"] == "Brand And Content Calendar"


def test_document_title_falls_back_to_readable_filename() -> None:
    title = document_title(Path("some-folder/q4-financial-report.pdf"))

    assert title == "Q4 Financial Report"
