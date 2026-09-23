"""Jev-as-judge over the charter proposal.

Pre-flight check: runs on the LLM's draft BEFORE the human sees it.
If the draft fails, the node re-drafts instead of wasting human time.
Jev never judges the human's ratification - the human is the authority.
Requires TYPESAFE_API_KEY in the environment.
"""
from langchain_typesafe import Noul, TypeSafeClassifier

_judge = TypeSafeClassifier()  # reads TYPESAFE_API_KEY from env


def precheck_charter(proposal: dict, baseline_brief: str) -> dict:
    response = _judge.invoke(
        {
            "state": {
                "proposed_artifact_ids": proposal.get("proposed_artifact_ids", []),
                "field_names": [
                    f["field_name"]
                    for f in proposal.get("field_semantics_map", [])
                ],
                "materiality_scope": proposal.get("materiality_scope", {}),
                "baseline_brief": baseline_brief,
            },
            "questions": {
                "coverage": Noul(instructions=(
                    "Does the proposed artifact list cover every document named in "
                    "the baseline brief? Answer yes only if no baseline document "
                    "is left without an artifact id."
                )),
                "grounded_fields": Noul(instructions=(
                    "Are the proposed field semantics grounded in the actual "
                    "skeleton structures (sheet columns, headings) from the "
                    "baseline brief, rather than invented field names?"
                )),
                "units": Noul(instructions=(
                    "Is every materiality threshold stated with an explicit unit "
                    "(percent, days, currency, count) rather than a bare number?"
                )),
            },
        }
    )
    return {
        "coverage": response.nouls["coverage"].noul,                # float 0..1
        "grounded_fields": response.nouls["grounded_fields"].noul,  # float 0..1
        "units": response.nouls["units"].noul,                      # float 0..1
        "model": response.model,
    }
