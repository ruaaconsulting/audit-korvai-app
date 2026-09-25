"""LLM helpers for the define node.

Judgment lives here. Deterministic extraction lives in
tools/baseline_text.py. RegistryItem itself lives in state.py.
"""
import os

from pydantic import BaseModel

from audit_engine.state import RegistryItem
from audit_engine.config import get_model


class RegistryList(BaseModel):
    items: list[RegistryItem]


DEFINE_PROMPT = """You are deriving an audit registry from project management standards.
Read the standards text. Extract every checkable criterion as one registry item.
Rules:
- criterion_id is stable and unique, e.g. RISK-001, SCH-004.
- standard is the source document name. clause is the section reference.
- paraphrase is ONE sentence. Never copy standard text verbatim.
- expected_evidence must name a concrete PMO artifact (RAID log, schedule,
  status report) and observable content - not a vague aspiration.
- Skip anything you cannot check against evidence. Fewer, checkable items
  beat a long, wishful list.

STANDARDS:
{baseline_text}"""


def propose_registry(baseline_text: str) -> list[RegistryItem]:
    """LLM derives the criteria registry from the baseline text."""
    llm = get_model()
    structured = llm.with_structured_output(RegistryList)
    result: RegistryList = structured.invoke(
        DEFINE_PROMPT.format(baseline_text=baseline_text)
    )
    return result.items
