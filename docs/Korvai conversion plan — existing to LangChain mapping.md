# Korvai Conversion Plan — What Existing Becomes What in LangChain

**Date:** 2026-09-17 · Source: IEM-PM v1.15.0 (`skills/intelligence-engine/`). Target: Korvai Audit v0.1 (first product under the Korvai brand) on the LangChain ecosystem.
**Rule:** deterministic logic is ported, never rewritten from memory. Judgment is re-expressed as graph nodes. Nothing with a working test gets redesigned — it gets relocated.

> Note: exact filenames under `scripts/` and `references/` to be confirmed in Phase 0 when the code is read line by line. The mapping below is at component level.

---

## A. The 11-stage state machine (SKILL.md) → LangGraph graph

| SKILL.md stage | Becomes in Korvai                            | How                                                                                                                                                                                               |
| -------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Baseline       | `baseline` node + startup guard              | Document loaders (PDF/MD/CSV) read the standards drop-zone. "No baseline, no audit" becomes a hard startup check — the CLI refuses to run on an empty baseline.                                   |
| Charter        | `propose_charter` node + `interrupt()`       | LLM drafts the charter from the baseline; the graph pauses; a human ratifies or edits; the graph resumes. What was a conversation becomes a checkpoint.                                           |
| Define         | `define` registry node                       | LLM call with `with_structured_output(RegistryItem)`: criterion id, standard, clause, one-sentence paraphrase, expected evidence. Output stored as the runtime registry (replaces `registries/`). |
| Measure        | `measure` node                               | Compares evidence against the registry. Fed by the evidence subagents' logs, not raw files.                                                                                                       |
| Classify       | `classify` node                              | Closed gap-type enum enforced at generation time. The "test in order, stop at first match" rule becomes prompt instruction + few-shot examples from `references/`.                                |
| Trace          | `trace` node                                 | Root origin enum (single accountable root) + optional contributing origins with confidence — the structure Ramani chose after Tony's review.                                                      |
| Score          | `score` node (LLM) → `compute` node (Python) | LLM proposes severity per finding; the deterministic RIS stays in plain Python. Severity 4/5 findings are flagged here, approved later at the interrupt.                                          |
| Synthesize     | `synthesize` node                            | Narrative + candidate gaps (observations without enough evidence stay out of the register — the existing escape hatch, now explicit). Injection flags land here.                                  |
| JSON           | `validate` node (plain Python)               | The ported schema validator. On failure → routes back to the failing node with the error (max 3 retries, then halt).                                                                              |
| Render         | `render` node (plain Python)                 | The ported renderer. HTML/TXT reports.                                                                                                                                                            |
| Summary        | CLI output                                   | The audit summary prints at the end of `korvai audit` and heads the report.                                                                                                                       |

The two human moments in the old flow (charter ratification, Major-finding approval) become the two `interrupt()` checkpoints. Everything else that was human-driven becomes graph edges.

## B. The Five Contracts → code boundaries (unchanged in spirit)

| Contract                | Becomes in Korvai                                                                     | Notes                                                                                                                                           |
| ----------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Standards (baseline)    | `knowledge/` drop-zone → loaded `Document`s with source metadata (file, page, clause) | Still gitignored, still local-only, still the user's own licensed content.                                                                      |
| PMO Data Charter        | `Charter` Pydantic model                                                              | Machine-proposed, human-ratified. Now versioned and hashed per run.                                                                             |
| Audit Manifest          | `Manifest` Pydantic model                                                             | Still THE boundary: everything before it is LLM judgment, everything after is deterministic code. This is the design rule that survives intact. |
| Canonical Findings JSON | `findings.py` output                                                                  | Ported converter, same JSON shape so old reports stay readable.                                                                                 |
| Schema Validator        | `validator.py` + validation node                                                      | Ported §10.3 rules, rule names preserved so errors stay explainable.                                                                            |

## C. `scripts/` (deterministic Python) → `korvai/deterministic/`

| Existing script                    | Becomes                      | Change                                                                                                                                                               |
| ---------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Manifest schema validation         | `validator.py`               | Port as-is. Called from the validation node. No LangChain import in this folder — enforced by grep in Phase 0 eval.                                                  |
| Manifest → findings converter      | `findings.py`                | Port as-is. Same JSON shape.                                                                                                                                         |
| Reporting Integrity Score          | `scoring.py`                 | Same math; formula, weights, and denominator published in the README (Tony's transparency item). Two-decimal output replaced by bands + confidence until calibrated. |
| Report renderer                    | `render.py`                  | Port as-is, plus the published formula block in the report.                                                                                                          |
| Checksum comparison (prior audits) | `provenance.py` (new, small) | Extended per Tony: SHA-256 of every evidence file + immutable run ID + model/prompt/params/code-version log, attached as LangSmith run metadata.                     |

## D. `references/` (appendices) → three jobs

| Content                               | Job 1: prompts                                                   | Job 2: evals                                                                    | Job 3: docs                                                                       |
| ------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| 7 gap types + disambiguation examples | System prompt of `classify` node (injected at runtime, few-shot) | Classification-accuracy eval dataset (the worked examples become labeled cases) | Taxonomy doc, rewritten to frame single classification as the action-forcing rule |
| 7 root origins                        | System prompt of `trace` node                                    | Boundary tests for origin pairs                                                 | Same doc                                                                          |
| Severity calibration (1–5)            | System prompt of `score` node                                    | Severity eval (expected vs assigned on the demo pack)                           | Calibration table in docs                                                         |
| Methodology appendices                | —                                                                | —                                                                               | `docs/` in the repo                                                               |

Single-sourcing rule: prompts load these files at runtime. Never hand-copy text into a prompt — the docs and the product must not drift.

## E. `assets/` (templates) → Jinja templates inside `render.py`

Report templates move with the renderer. No change in function.

## F. `knowledge/` + `registries/` (gitignored runtime dirs) → runtime dirs, still gitignored

- `knowledge/` stays the baseline drop-zone (user's standards, never committed).
- `registries/` (criteria derived at runtime) becomes the persisted registry — stored per-run via the LangGraph checkpointer or a local JSON store, still gitignored.

## G. What disappears or changes form

| Existing                                                                           | Change                                                                                                                       |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Claude Code skill wrapper (`SKILL.md` as the runner, `.claude-plugin/plugin.json`) | Replaced by the pip CLI: `korvai audit`, `korvai demo`. The product is no longer tied to Claude or Claude Code.              |
| Claude-only model dependency                                                       | Model-agnostic: one `--model` config value through `init_chat_model()`.                                                      |
| `Public/` (human docs)                                                             | Rewritten as README + `docs/` with corrected positioning ("emerging AI-assisted evidence-assurance framework, pilot-ready"). |
| `Audit/` (user's audit projects, gitignored)                                       | Becomes the user-supplied `--evidence` path. Nothing ships; the repo carries only `demo_pack/`.                              |
| `IEM-PM BLUEPRINT-1.md`, `STATUS.md`                                               | Superseded by this plan + the build plan + the architecture doc. Archived, not deleted.                                      |
| `_archive/`, `stakeholder/`                                                        | Do not move. History only, never published from.                                                                             |

## H. What is new (no existing counterpart)

- **Evidence subagents (Deep Agents):** one isolated subagent per artifact. New — the old skill relied on a judgment rule (Principle 8); the build enforces it mechanically.
- **LangSmith tracing + 6 evaluators + consistency harness:** new — the audit trail of the audit.
- **Release gates as runtime guards:** new — Tony's gates encoded as code, not documentation.
- **Docker image + pip package:** new — the shareable distribution the old skill never had.
- **Decision Context layer, blind-review mode, adjudication, corrective-action tracking, enterprise aggregation:** new in v0.2, specced during v0.1.

---

## Conversion order (matches the build plan)

1. **Phase 0:** C (scripts → deterministic/) + B (contracts → Pydantic models). No framework yet.
2. **Phase 1:** demo pack (new) + D-job-2 (references → eval datasets).
3. **Phase 2:** A (11 stages → graph) + B (Manifest boundary wired in).
4. **Phase 3:** H (subagents) — the one genuinely new architectural piece.
5. **Phase 4:** D-job-2 + H (evaluators, tracing, consistency harness).
6. **Phase 5:** E + G (templates, CLI, Docker, rewritten docs) + H (release gates).

_Companions: `korvai-build-plan-2026-09-17.md` (phases, evals, schedule), `iem-pm-langchain-architecture-2026-09-17.md` (design rationale)._
