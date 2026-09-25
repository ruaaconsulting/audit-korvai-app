"""Jev-as-judge over the measure node's output.

Jev never collects the evidence - it scores it. Two typed questions per
FOUND record, one API call. Whether the excerpt is a verbatim quote is
checked deterministically in tools/evidence_store.py, not by the judge.
Requires TYPESAFE_API_KEY in the environment.
"""
from langchain_typesafe import Noul, TypeSafeClassifier

from audit_engine.tools.evidence_store import verify_verbatim

_judge = TypeSafeClassifier()  # reads TYPESAFE_API_KEY from env


def grade_evidence_item(record: dict, source_excerpt: str) -> dict:
    response = _judge.invoke(
        {
            "state": {
                "criterion_id": record["criterion_id"],
                "criterion_paraphrase": record.get("criterion_paraphrase", ""),
                "excerpt": record["excerpt"],
                "location": record["location"],
                "source_document": record["source_document"],
                "source_excerpt": source_excerpt,
            },
            "questions": {
                "supports": Noul(instructions=(
                    "Does the quoted excerpt actually provide evidence for the stated "
                    "criterion? Answer yes only if the excerpt speaks to the requirement "
                    "itself, not merely mentions a related word."
                )),
                "located": Noul(instructions=(
                    "Is the cited location consistent with where this excerpt appears "
                    "in the source excerpt? Answer yes only if the location plausibly "
                    "matches the excerpt's position."
                )),
            },
        }
    )
    return {
        "supports": response.nouls["supports"].noul,  # float 0..1
        "located": response.nouls["located"].noul,    # float 0..1
        "model": response.model,
    }


def precheck_evidence(records: list, source_text: str) -> dict:
    """Quality gate over one propose_evidence draft.

    verbatim is deterministic (exact substring match). supports and located
    are Jev judgments over FOUND records only. found_rate is reported, not
    gated - absence of evidence is a downstream finding, not a draft failure.
    """
    found = [r for r in records if r.get("status") == "FOUND"]
    verbatim_hits = sum(
        1 for r in found if verify_verbatim(r.get("excerpt", ""), source_text)
    )
    supports_scores, located_scores, model = [], [], "jev"
    excerpt = source_text[:8000]
    for record in found:
        grades = grade_evidence_item(record, excerpt)
        supports_scores.append(grades["supports"])
        located_scores.append(grades["located"])
        model = grades["model"]
    n = len(records)
    return {
        "verbatim": verbatim_hits / len(found) if found else 1.0,
        "supports": (sum(supports_scores) / len(supports_scores)
                     if supports_scores else 1.0),
        "located": (sum(located_scores) / len(located_scores)
                    if located_scores else 1.0),
        "found_rate": len(found) / n if n else 0.0,
        "records_checked": n,
        "model": model,
    }
