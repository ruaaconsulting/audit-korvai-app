import json
from pathlib import Path


def skeleton_brief() -> str:
    index = json.loads(
        Path("registries/knowledge_index.json").read_text(encoding="utf-8")
    )
    lines = []
    for s in index.get("skeletons", []):
        lines.append(f"--- {s['document_id']} ---")
        if "structure" in s:
            lines.append("headings: " + "; ".join(s["structure"][:40]))
        if "sheets" in s:
            for sh in s["sheets"]:
                cols = [str(c) for c in sh["columns"] if c]
                lines.append(f"sheet {sh['sheet_name']}: " + ", ".join(cols[:30]))
    return "\n".join(lines)