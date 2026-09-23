"""Deterministic extraction of standards text for the define node.

Reads the document list from registries/knowledge_index.json (written by the
baseline node) and pulls text from the source files in knowledge/.
Pure extraction - no LLM, no judgment.
"""
import json
from pathlib import Path

from pypdf import PdfReader
from docx import Document as DocxDocument

MAX_CHARS_PER_DOC = 12000
MAX_TOTAL_CHARS = 40000


def _text_from_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _text_from_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def load_baseline_text(knowledge_dir: str = "knowledge",
                       index_path: str = "registries/knowledge_index.json") -> str:
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    knowledge = Path(knowledge_dir)

    chunks, total = [], 0
    for name in index.get("documents", []):
        path = knowledge / name
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".md":
            text = path.read_text(encoding="utf-8")
        elif suffix == ".pdf":
            text = _text_from_pdf(path)
        elif suffix == ".docx":
            text = _text_from_docx(path)
        else:
            # xlsx/csv carry structure, not prose - pass it through as-is
            text = f"[structured file - see knowledge_index.json skeleton for {name}]"
        text = text[:MAX_CHARS_PER_DOC]
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        chunks.append(f"=== STANDARD: {name} ===\n{text}")
        total += len(text)
    return "\n\n".join(chunks)
