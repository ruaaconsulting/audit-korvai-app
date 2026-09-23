"""Deterministic skeleton brief for the charter draft.

Reads registries/knowledge_index.json (written by the baseline node) and
formats the skeleton structures as plain text for the charter prompt.
No LLM, no LangChain imports - pure extraction.
"""
import json
from pathlib import Path


def skeleton_brief(index_path: str = "registries/knowledge_index.json") -> str:
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    lines = []
    for s in index.get("skeletons", []):
        lines.append(f"--- {s['document_id']} ---")
        if "structure" in s:
            lines.append("headings: " + "; ".join(s["structure"][:300]))
        if "sheets" in s:
            for sh in s["sheets"]:
                cols = [str(c) for c in sh["columns"] if c]
                lines.append(f"sheet {sh['sheet_name']}: " + ", ".join(cols[:300]))
    return "\n".join(lines)
