import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from audit_engine.graph import compiled

config = {"configurable": {"thread_id": "charter-test-1"}}

try:
    compiled.invoke({"baseline_standards": ["demo"]}, config)
except GraphInterrupt:
    pass  # expected: the charter node paused for ratification

payload = compiled.get_state(config).interrupts[0].value
print("Jev precheck:", payload["jev_precheck"])

charter = payload["proposed_charter"]
charter["charter_metadata"].update({
    "organization": "Test Org",
    "ratified_by": "Ramani",
    "ratified_date": "2026-09-23",
    "charter_status": "RATIFIED",
})

try:
    compiled.invoke(Command(resume=charter), config)
except Exception as e:
    print("Stopped as expected:", type(e).__name__,
          "(findings node needs the later stages)")

snap = compiled.get_state(config)
print("status:", snap.values["charter_metadata"].charter_status)
print("artifacts:", snap.values["chartered_artifact_ids"])
print("registry items:", len(snap.values["registry"]))