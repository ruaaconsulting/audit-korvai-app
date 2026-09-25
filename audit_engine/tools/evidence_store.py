"""Deterministic evidence handling for the measure node.

No LLM, no LangChain imports. Hashing, verbatim verification, and on-disk
storage only. If it needs judgment, it does not belong here.
"""

import hashlib
import json

from pathlib import Path


def _normalize(text: str) -> str:
    return " ".join(text.split())


def fingerprint_excerpt(excerpt: str) -> str:
    """SHA-256 over the whitespace-normalized excerpt."""
    return hashlib.sha256(_normalize(excerpt).encode("utf-8")).hexdigest()


def verify_verbatim(excerpt: str, source_text: str) -> bool:
    """True only if the excerpt appears word-for-word in the source.

    Quotation accuracy is checkable without judgment, so it is checked
    here - not by the Jev judge.
    """
    if not excerpt or not excerpt.strip():
        return False
    return _normalize(excerpt) in _normalize(source_text)


def store_evidence(records: list, run_dir: str = "registries/evidence") -> list:
    """Fingerprint FOUND records and write one JSON file per criterion.

    Returns the records with fingerprints attached, ready for graph state.
    """
    path = Path(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    for record in records:
        if record.status == "FOUND":
            record.fingerprint = fingerprint_excerpt(record.excerpt)
        (path / f"{record.criterion_id}.json").write_text(
            record.model_dump_json(indent=2)
        )
    return records
