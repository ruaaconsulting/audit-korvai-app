"""IEM-PM methodology skill (v0.1 stand-in).

WHERE THE METHODOLOGY LIVES
---------------------------
The IEM-PM methodology is consumed by agents as a SKILL. It is never
indexed as knowledge: knowledge/ holds WHAT is being audited (evidence,
client standards as data); this skill holds HOW the audit is done.

The enum names in audit_engine/state.py (GapType, RootOrigin) are the
contract. This file is the prose: the definitions the prompts and the
Jev classifier read. There is exactly one copy of each definition.

WHEN THE .md FILES ARRIVE
-------------------------
Replace the DEFINITIONS dicts below with the exact wording from the
IEM-PM taxonomy .md files. Keep the keys identical to the enum values
in state.py - the code matches on keys, so a renamed key breaks the
argmax mapping in nodes/classify.py.
"""

# Starter definitions drafted from the enum names. Replace with the exact
# wording from the IEM-PM §7 taxonomy doc when it arrives.
GAP_TYPE_DEFINITIONS = {
    "Missing": "The required artifact, data, or practice does not exist at all.",
    "Ignored": "It exists but is not used or followed in practice.",
    "Disconnected": "It exists but is not linked to the things that depend on it.",
    "Untrusted": "It exists but its accuracy or currency cannot be relied upon.",
    "Underutilized": "It exists and is trusted but its capability is not fully exploited.",
    "Misclassified": "It exists but is categorized or labeled in a way that misleads.",
    "Divergent": "Multiple versions or understandings exist and they disagree.",
}

# Starter definitions drafted from the enum names. Replace with the exact
# wording from the IEM-PM root-origin doc when it arrives.
ROOT_ORIGIN_DEFINITIONS = {
    "Capture": "The information was never captured in the first place.",
    "Integration": "It was captured but never integrated into the system that needed it.",
    "Definition / Taxonomy": "The term or category was defined ambiguously or inconsistently.",
    "Ownership": "No one owned it, so no one acted on it.",
    "Process / Cadence": "The process or rhythm that should have caught it did not exist or did not run.",
    "Tooling": "The tool needed to surface or enforce it was missing or inadequate.",
    "Behavior": "People knew but behaved otherwise - habit, incentives, or culture.",
}


def gap_taxonomy_brief() -> str:
    """One-line brief of all 7 gap types, for question prompts."""
    return "\n".join(
        f"{i + 1}. {name} - {definition}"
        for i, (name, definition) in enumerate(GAP_TYPE_DEFINITIONS.items())
    )


def root_origin_brief() -> str:
    """One-line brief of all 7 root origins, for question prompts."""
    return "\n".join(
        f"{i + 1}. {name} - {definition}"
        for i, (name, definition) in enumerate(ROOT_ORIGIN_DEFINITIONS.items())
    )
