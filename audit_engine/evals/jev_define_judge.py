"""Jev-as-judge over the define node's output.

Jev never authors the registry - it scores it. Three typed questions per
item, one API call. Requires TYPESAFE_API_KEY in the environment.
"""
from langchain_typesafe import Noul, TypeSafeClassifier

_judge = TypeSafeClassifier()  # reads TYPESAFE_API_KEY from env


def grade_registry_item(item: dict, baseline_excerpt: str) -> dict:
    response = _judge.invoke(
        {
            "state": {
                "criterion_id": item["criterion_id"],
                "standard": item["standard"],
                "clause": item.get("clause"),
                "paraphrase": item["paraphrase"],
                "expected_evidence": item["expected_evidence"],
                "baseline_excerpt": baseline_excerpt,
            },
            "questions": {
                "faithful": Noul(instructions=(
                    "Does the one-sentence paraphrase faithfully capture a requirement "
                    "stated in the baseline excerpt? Answer yes only if nothing "
                    "material is added or dropped."
                )),
                "checkable": Noul(instructions=(
                    "Is the expected evidence concretely checkable against PMO artifacts "
                    "- a named artifact with observable content - rather than a vague "
                    "aspiration?"
                )),
                "grounded": Noul(instructions=(
                    "Is this criterion actually grounded in the baseline excerpt, "
                    "rather than invented by the model?"
                )),
            },
        }
    )
    return {
        "faithful": response.nouls["faithful"].noul,      # float 0..1
        "checkable": response.nouls["checkable"].noul,    # float 0..1
        "grounded": response.nouls["grounded"].noul,      # float 0..1
        "model": response.model,
    }


def define_quality_gate(item: dict, baseline_excerpt: str,
                        threshold: float = 0.7) -> tuple[bool, dict]:
    scores = grade_registry_item(item, baseline_excerpt)
    passed = all(scores[k] >= threshold for k in ("faithful", "checkable", "grounded"))
    return passed, scores
