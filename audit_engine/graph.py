"""
audit_engine/graph.py

Audit engine ports one node from graph , ported from state.py. this is the real engine that runs the whole application

"""

import json, uuid

from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver

from audit_engine.state import AuditState, CharterProposal, IEMPMCanonicalState

from audit_engine.tools.render_helpers import compute_origin_counts, compute_severity_counts
from audit_engine.tools.scoring import compute_reporting_integrity_score
from audit_engine.tools.skeleton_extraction import EXTRACTORS, fingerprint
from audit_engine.tools.baseline_text import load_baseline_text
from audit_engine.tools.charter_validate import validate_ratified_charter
from audit_engine.tools.charter_brief import skeleton_brief

from audit_engine.nodes.charter import propose_charter
from audit_engine.nodes.define import propose_registry


def baseline_node(state: AuditState) -> dict:
    # a stub - no real logic yet, just proves the wiring works

    knowledge_dir = Path("knowledge")
    all_files = list(knowledge_dir.iterdir()) if knowledge_dir.exists() else []

    skeletons = []
    fingerprints = {}
    skipped = []

    for file in all_files:
        if file.is_dir():
            continue
        extractor = EXTRACTORS.get(file.suffix.lower())
        if extractor is None:
            skipped.append(file.name)
            continue
        skeletons.append(extractor(file))
        fingerprints[file.name] = fingerprint(file)

    if not skeletons:
        print("BASELINE_ABSENT - no standards found in knowledge/.")
        print("Place real standards (PDF/MD/DOCX/XLSX/CSV) in knowledge/ and re-run.")
        return {"validation_errors": ["BASELINE_ABSENT"]}

    if skipped:
        print(f"Unsupported formats skipped: {skipped}")

    Path("registries").mkdir(exist_ok=True)
    Path("registries/knowledge_index.json").write_text(
        json.dumps({
            "documents": list(fingerprints.keys()), 
            "fingerprints": fingerprints,
            "skipped": skipped,
            "skeletons": skeletons 
        }, indent=2),
        encoding="utf-8"
    )

    audit_id = f"IEM-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    print(f"baseline_node ran - {len(skeletons)} standard(s) found, {len(skipped)} skipped")
    return {
        "audit_id": audit_id,
        "baseline_standards": [s["document_id"] for s in skeletons]
    }

def charter_node(state: AuditState) -> dict:
    brief = skeleton_brief()
    if not brief.strip():
        return {"validation_errors": ["BASELINE_EMPTY"]}

    proposal, check = propose_charter(brief)

    # Human ratification. Resume with Command(resume=<charter dict>).
    # The human may edit any field; ratified_by / ratified_date / organization
    # must be filled in for real - validate_ratified_charter enforces it.
    human_response = interrupt({
        "action": "ratify_charter",
        "proposed_charter": proposal.model_dump(mode="json"),
        "jev_precheck": check,
    })
    data = validate_ratified_charter(human_response)
    ratified = CharterProposal.model_validate(data)
    print(f"charter_node ran - charter {ratified.charter_metadata.charter_status}")
    return {
        "charter_metadata": ratified.charter_metadata,
        "materiality_scope": ratified.materiality_scope,
        "waivers": ratified.waivers,
        "field_semantics_map": ratified.field_semantics_map,
        "chartered_artifact_ids": ratified.proposed_artifact_ids,
    }

def define_node(state: AuditState) -> dict:
    baseline_text = load_baseline_text()
    if not baseline_text.strip():
        return {"validation_errors": ["BASELINE_EMPTY"], "registry": []}
    items = propose_registry(baseline_text)
    print(f"define_node ran - {len(items)} criteria derived")
    return {"registry": items}

def measure_node(state: AuditState) -> dict:
    # its a stub
    print("Measure node ran - The Purpose of this node is Evaluate every applicable registry criterion against the delivery evidence; each failure becomes a gap.")
    return {}

def classify_node(state: AuditState) -> dict:
    # its a stub
    print("classify node ran - The Purpose of this node is Assign each gap exactly one of the 7 gap types (§7). No overlap, no duplicates.")
    return {}

def trace_node(state: AuditState) -> dict:
    # its a stub
    print("trace node ran - The Purpose of this node is Trace each gap to exactly one of the 7 root origins (§8) — the earliest point the gap entered the system.")
    return {}

def score_node(state: AuditState) -> dict:
    # its a stub
    print("score node ran - The Purpose of this node is for every finding and assign its severity, using the four-part diagnostic (Evidence · Impact · Why/Who/Scope · Fix-at-source) ")
    return {}

def synthesize_node(state: AuditState) -> dict:
    # its a stub
    print("synthesize node ran - The Purpose of this node is Write the complete Audit Manifest to disk (§10) — the compaction-survival gate. Everything after this is deterministic. ")
    return {}

def findings_node(state: AuditState) -> dict:
    # its a stub

    canonical = state.to_canonical()
    score = compute_reporting_integrity_score(canonical.findings,canonical.artifacts_examined)
    canonical_with_score = canonical.model_copy(update={"reporting_integrity_score":score})

    Path("audit_engine/output").mkdir(exist_ok=True)
    Path("audit_engine/output/findings.json").write_text(
        canonical_with_score.model_dump_json(indent=2)
    )

    print(f"findings_node ran - RIS: {score.score}")
    return {}   

def render_node(state: AuditState) -> dict:
    # The Purpose of this node is convert the  findings to HTML file
    # Stage 9 - deterministic. No LLM, no judgment - pure substitution.

    canonical = IEMPMCanonicalState.model_validate_json(
        Path("audit_engine/output/findings.json").read_text()
    )

    baseline_view = SimpleNamespace(
        standards_declared = canonical.baseline_standards,
        artifacts_examined = canonical.artifacts_examined,
        scope=[]
    )

    audit_view = SimpleNamespace(
        **canonical.model_dump(),
        baseline = baseline_view,
        charter_version = canonical.charter_metadata.charter_version
    )

    env = Environment(loader=FileSystemLoader("audit_engine/assets"))
    template = env.get_template("report_template.html")

    html = template.render(
        audit = audit_view,
        generated_at = canonical.generated_at.isoformat(),
        findings_count= len(canonical.findings),
        artifact_count = len(canonical.artifacts_examined),
        origin_counts = compute_origin_counts(canonical.findings),
        severity_counts = compute_severity_counts(canonical.findings),
        ris_components = canonical.reporting_integrity_score.components.model_dump(),
        ris_limitations = canonical.reporting_integrity_score.limitations
    )

    #text = render

    Path("audit_engine/output").mkdir(exist_ok=True)
    Path("audit_engine/output/report.html").write_text(html)

    print("render node ran - The Purpose of this node is convert the  findings to HTML file ")
    return {}

def summarise_node(state: AuditState) -> dict:
    # its a stub
    print("summarise node ran - The Purpose of this node is Print the TXT summary and the output file pointers; confirm the run checklist (§12). ")
    return {}

graph = StateGraph(AuditState)

graph.add_node("baseline", baseline_node)
graph.add_node("charter", charter_node)
graph.add_node("define", define_node)
graph.add_node("measure", measure_node)
graph.add_node("classify", classify_node)
graph.add_node("trace", trace_node)
graph.add_node("score", score_node)
graph.add_node("synthesize", synthesize_node)
graph.add_node("findings", findings_node)
graph.add_node("render", render_node)
graph.add_node("summarise", summarise_node)

graph.set_entry_point("baseline")

graph.add_edge("baseline", "charter")     
graph.add_edge("charter","define" )
graph.add_edge("define","measure" )
graph.add_edge("measure","classify" )
graph.add_edge("classify","trace" )
graph.add_edge("trace","score" )
graph.add_edge("score","synthesize" )
graph.add_edge("synthesize","findings" )
graph.add_edge("findings","render" )
graph.add_edge("render","summarise" )
graph.add_edge("summarise", END)         

# --- interrupts need a checkpointer to survive the pause ---
checkpointer = MemorySaver()
compiled = graph.compile(checkpointer=checkpointer) 
