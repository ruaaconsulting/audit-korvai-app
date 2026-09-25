#!/usr/bin/env python3
"""Run the Korvai audit pipeline, handling human approval pauses.

Copy this file to your project root (next to pyproject.toml), then:

    uv run python run_pipeline.py            # fresh run
    uv run python run_pipeline.py audit-1    # re-run under a fixed thread id

When the pipeline pauses for charter approval, the proposal is saved to
charter_proposal.json in the project root. Open it, review/edit it, fill in
ratified_by / ratified_date / organization, save, press Enter — the run
continues from where it paused.
"""
import json
import sys
import time

from langgraph.types import Command

from audit_engine.graph import compiled


def handle_charter_interrupt(payload):
    proposal = payload.get("proposed_charter", {})
    path = "charter_proposal.json"
    with open(path, "w") as f:
        json.dump(proposal, f, indent=2)
    print("\n--- HUMAN APPROVAL NEEDED: charter ---")
    print(f"Proposal saved to {path}.")
    print("Open it, review/edit, and fill in: ratified_by, ratified_date, organization.")
    input("Press Enter when the file is saved and ready... ")
    with open(path) as f:
        return json.load(f)


def main():
    thread_id = sys.argv[1] if len(sys.argv) > 1 else f"audit-{int(time.time())}"
    config = {"configurable": {"thread_id": thread_id}}
    print(f"Starting pipeline (thread_id={thread_id})...")

    resume_value = None
    first_run = True
    while True:
        stream_input = {} if first_run else Command(resume=resume_value)
        first_run = False
        paused = False
        for event in compiled.stream(stream_input, config):
            if "__interrupt__" in event:
                payload = event["__interrupt__"][0].value
                action = payload.get("action")
                print(f"\nPipeline paused: {action}")
                if action == "ratify_charter":
                    resume_value = handle_charter_interrupt(payload)
                else:
                    print("Unknown interrupt payload:",
                          json.dumps(payload, indent=2)[:2000])
                    raw = input("Paste resume JSON (or empty to abort): ").strip()
                    if not raw:
                        print("Aborted.")
                        return
                    resume_value = json.loads(raw)
                paused = True
                break
        if not paused:
            print("\nPipeline finished.")
            break


if __name__ == "__main__":
    main()
