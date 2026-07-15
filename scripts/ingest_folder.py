#!/usr/bin/env python
"""Basic one-shot ingest script for testing Phase 0/1.

Scans a folder, performs OCR/extraction via local LLM, writes co-located OKF MDs.
Run with: python scripts/ingest_folder.py /path/to/test/docs
"""

import sys
from pathlib import Path
import pdfplumber  # or your preferred OCR lib
from app.services.llm_client import LLMClient
from app.models.okf import OKFDocument, OKFFrontmatter

def ocr_file(file_path: Path) -> str:
    """Placeholder OCR. Replace with full pipeline (pdfplumber + easyocr or marker)."""
    if file_path.suffix.lower() == ".pdf":
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        return text
    # Add image handling etc.
    return file_path.read_text(encoding="utf-8", errors="ignore")

def main(folder: str):
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory")
        sys.exit(1)

    client = LLMClient()  # Configure model/endpoint as needed
    print(f"Scanning {root}...")

    for file_path in root.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in [".pdf", ".png", ".jpg", ".jpeg", ".txt"]:
            print(f"Processing: {file_path}")
            raw_text = ocr_file(file_path)
            if not raw_text.strip():
                continue

            # Extract via LLM
            extracted_md = client.extract_structured(raw_text, context=str(file_path.relative_to(root)))
            
            # Parse and ensure co-located output
            try:
                okf_doc = OKFDocument.from_markdown(extracted_md)
                # Ensure source
                if not okf_doc.frontmatter.source:
                    okf_doc.frontmatter.source = str(file_path.relative_to(root))
                if not okf_doc.frontmatter.title:
                    okf_doc.frontmatter.title = file_path.stem.replace("_", " ").title()

                # Co-located MD: same name + .md or in _kb/ subdir
                md_path = file_path.with_suffix(".md")  # Companion style
                # Alternative: md_path = file_path.parent / "_kb" / f"{file_path.stem}.md"
                md_path.parent.mkdir(exist_ok=True)
                md_path.write_text(okf_doc.to_markdown(), encoding="utf-8")
                print(f"  -> Wrote {md_path}")
            except Exception as e:
                print(f"  Error processing {file_path}: {e}")

    print("Ingest complete. Check co-located .md files and refine prompts as needed.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/ingest_folder.py /path/to/documents")
        sys.exit(1)
    main(sys.argv[1])
