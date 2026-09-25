"""Classify node: two classifier backends, one interface, code thresholds.

PIPELINE POSITION (cross-reference to the other nodes)
------------------------------------------------------
Upstream: the measure node wrote state.evidence, a list of EvidenceRecord
  (criterion_id, criterion_paraphrase, status, excerpt, location).
  Classify reads those fields and nothing else.
Downstream:
  - trace reads verdict.gap_type, verdict.root_origin,
    verdict.considered_alternative (runner-up -> contributing-factor lead).
  - score reads verdict.verdict to decide what gets severity/RIS scoring.
    Classify never assigns severity.
  - the human interrupt reads check["needs_review"] (step 4).

THE TWO BACKENDS
----------------
"jev"  - TypeSafe's Jev via langchain-typesafe. A binary judge, so we ask
         one yes/no question per class and take the argmax. Closed API,
         needs TYPESAFE_API_KEY in the environment.
"laya" - Convai Innovations' open-source decision model (Apache 2.0),
         self-hosted. Its native `choice` questions return the full
         probability distribution over the classes in one call - no argmax
         trick needed. Needs `pip install laya` (lazy import: the Jev path
         never touches it). The 421M checkpoint downloads from Hugging Face
         on first use.

Both backends answer the same three questions per evidence record:
  (a) is this a gap?  (b) which ONE gap type?  (c) which ONE root origin?
and both return confidences. The step-3 threshold code is backend-agnostic,
so the LangSmith head-to-head compares backends fairly instead of comparing
two different pipelines.

Pick the backend with the CLASSIFY_BACKEND env var ("jev" if unset).

SEPARATION RULE (decision log)
------------------------------
The checker never sees the doer's reasoning. The classify backends receive
only the evidence artifact: criterion_id, criterion_paraphrase, status,
excerpt, location. They never receive the extractor LLM's chain-of-thought,
rationale, or thinking - not as text, not as a field. `_checker_input`
builds the backend input from an explicit allowlist and raises if a record
carries a reasoning-like field, so a leak fails loudly instead of being
silently classified. The measure node must strip the extractor's reasoning
before writing state.evidence.
"""

import os

from audit_engine.skills.iem_pm import (
    GAP_TYPE_DEFINITIONS,
    ROOT_ORIGIN_DEFINITIONS,
)
from audit_engine.state import GapVerdict, GapType, RootOrigin

# ---------------------------------------------------------------------------
# Step-3 thresholds. Plain Python, backend-agnostic. A threshold change is a
# one-line diff with a git history - not a prompt tweak nobody can audit.
# ---------------------------------------------------------------------------
GAP_THRESHOLD = 0.6     # P(gap) at or above this -> verdict is GAP.
REVIEW_GAP_PROB = 0.75  # GAP verdicts below this were borderline calls.
CLASS_THRESHOLD = 0.7   # Chosen type/origin below this -> human review.
REVIEW_MARGIN = 0.15    # Top-two type probabilities closer than this ->
                        # genuine ambiguity (the Tony case) -> human review.

# Lazy singletons: building either client is expensive (API session, or a
# 421M checkpoint download), so each is created once per process.
_jev = None
_laya_router = None


def _get_jev():
    global _jev
    if _jev is None:
        from langchain_typesafe import TypeSafeClassifier
        _jev = TypeSafeClassifier()  # reads TYPESAFE_API_KEY from env
    return _jev


def _get_laya_router():
    global _laya_router
    if _laya_router is None:
        try:
            from laya import Router
        except ImportError:
            raise RuntimeError(
                "backend 'laya' needs the laya package: pip install laya")
        _laya_router = Router()  # downloads the checkpoint on first use
    return _laya_router


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _field(item, name: str):
    """Read a field from either a Pydantic model or a plain dict."""
    if hasattr(item, name):
        return getattr(item, name)
    if isinstance(item, dict):
        return item.get(name, "")
    return ""


def _slug(name: str) -> str:
    """'Definition / Taxonomy' -> 'definition_taxonomy'. Jev question keys."""
    return name.lower().replace(" / ", "_").replace(" ", "_").replace("-", "_")


def _shown_excerpt(excerpt: str) -> str:
    """Absence of evidence is stated explicitly - it is not an empty string."""
    if excerpt:
        return excerpt
    return "NO EVIDENCE - the source contained nothing for this criterion."


def _state_text(paraphrase: str, excerpt: str) -> str:
    """The single text block both backends classify. Same input, fair fight."""
    return f"Criterion: {paraphrase} Evidence: {_shown_excerpt(excerpt)}"


# The evidence artifact: the only fields the checker may see (separation rule).
CHECKER_FIELDS = ("criterion_id", "criterion_paraphrase", "status",
                  "excerpt", "location")
# Field names that smell like doer reasoning. If one shows up on a record,
# that is a leak - fail loudly so it gets fixed, never silently classified.
FORBIDDEN_FIELDS = ("reasoning", "rationale", "chain_of_thought", "thought",
                    "thinking", "scratchpad")


def _checker_input(record) -> str:
    """Build the backend input from the allowlist only (separation rule).

    The paraphrase here is the artifact's label - what the criterion expects,
    in one line - not the extractor's thinking. Anything resembling
    chain-of-thought raises ValueError: the measure node must strip the
    extractor's reasoning before writing state.evidence.
    """
    names = set(getattr(type(record), "model_fields", {}) or {})
    extra = getattr(record, "model_extra", None)  # Pydantic v2 extra fields
    if isinstance(extra, dict):
        names |= set(extra)
    if isinstance(record, dict):
        names |= set(record)
    else:
        # Catch-all: every public attribute name on the object, including
        # class-level ones. Method names (model_dump, ...) can never match a
        # forbidden field, so this cannot false-positive - it can only catch
        # a real reasoning leak.
        names |= {k for k in dir(record) if not k.startswith("_")}
    leaked = sorted(n for n in names if n.lower() in FORBIDDEN_FIELDS)
    if leaked:
        raise ValueError(
            f"separation rule violated: record "
            f"{_field(record, 'criterion_id')!r} carries reasoning field(s) "
            f"{leaked} - the checker must never see the doer's reasoning")
    return _state_text(_field(record, "criterion_paraphrase"),
                       _field(record, "excerpt"))


def _ranked(probs: dict) -> list:
    return sorted(probs.items(), key=lambda kv: kv[1], reverse=True)


# ---------------------------------------------------------------------------
# Backend: Jev (binary judge -> one question per class -> argmax)
# ---------------------------------------------------------------------------
def _jev_noul(state_text: str, name: str, instructions: str) -> float:
    from langchain_typesafe import Noul
    response = _get_jev().invoke(
        {"state": {"input": state_text},
         "questions": {name: Noul(instructions=instructions)}})
    return response.nouls[name].noul


def _jev_record(state_text: str) -> dict:
    """One evidence record through Jev. Returns the normalized result dict."""
    gap_prob = _jev_noul(
        state_text, "is_gap",
        "Is this a gap? Answer yes if the evidence fails to satisfy the "
        "criterion, or if no evidence was found at all.")
    model = "jev"
    if gap_prob < GAP_THRESHOLD:
        return {"gap_prob": gap_prob, "gap_type": None, "type_probs": {},
                "root_origin": None, "root_probs": {}, "model": model}

    # 7 gap-type questions, one call, argmax.
    type_names = ", ".join(GAP_TYPE_DEFINITIONS)
    from langchain_typesafe import Noul
    questions = {
        _slug(name): Noul(instructions=(
            f"Gap types: {type_names}. Is this gap best described as {name}? "
            f"{definition} Answer yes only if {name} fits better than every "
            f"other listed type."))
        for name, definition in GAP_TYPE_DEFINITIONS.items()
    }
    response = _get_jev().invoke(
        {"state": {"input": state_text}, "questions": questions})
    model = response.model
    type_probs = {name: response.nouls[_slug(name)].noul
                  for name in GAP_TYPE_DEFINITIONS}
    gap_type = _ranked(type_probs)[0][0]

    # 7 root-origin questions, one call, argmax.
    origin_names = ", ".join(ROOT_ORIGIN_DEFINITIONS)
    questions = {
        _slug(name): Noul(instructions=(
            f"Root origins: {origin_names}. The gap was classified as "
            f"{gap_type}. Is the accountable root origin best described as "
            f"{name}? {definition} Answer yes only if {name} fits better "
            f"than every other listed origin."))
        for name, definition in ROOT_ORIGIN_DEFINITIONS.items()
    }
    response = _get_jev().invoke(
        {"state": {"input": state_text}, "questions": questions})
    root_probs = {name: response.nouls[_slug(name)].noul
                  for name in ROOT_ORIGIN_DEFINITIONS}
    root_origin = _ranked(root_probs)[0][0]

    return {"gap_prob": gap_prob, "gap_type": gap_type,
            "type_probs": type_probs, "root_origin": root_origin,
            "root_probs": root_probs, "model": model}


# ---------------------------------------------------------------------------
# Backend: Laya (native choice -> full distribution in one call)
# ---------------------------------------------------------------------------
def _laya_record(state_text: str) -> dict:
    """One evidence record through Laya. Same normalized result dict.

    Note: Laya's raw confidences are uncalibrated out of the box (its own
    checkpoint ships a warning saying so). The threshold code below treats
    them exactly like Jev's - which is why the head-to-head eval matters:
    it shows what uncalibrated confidence does to the review queue.
    """
    router = _get_laya_router()

    res = router.predict(state_text, {
        "is_gap": {"type": "noul", "instructions":
                   "Is this a gap? Answer yes if the evidence fails to "
                   "satisfy the criterion, or if no evidence was found at all."},
    })
    gap_prob = res["answers"]["is_gap"]["noul"]
    model = "laya/" + res.get("routing", {}).get("model", "english")
    if gap_prob < GAP_THRESHOLD:
        return {"gap_prob": gap_prob, "gap_type": None, "type_probs": {},
                "root_origin": None, "root_probs": {}, "model": model}

    res = router.predict(state_text, {
        "gap_type": {"type": "choice",
                     "instructions":
                     "Which single gap type best describes this gap - the one "
                     "that determines the corrective action?",
                     "criteria": dict(GAP_TYPE_DEFINITIONS)},
    })
    type_probs = dict(res["answers"]["gap_type"]["probabilities"])
    gap_type = _ranked(type_probs)[0][0]

    res = router.predict(state_text, {
        "root_origin": {"type": "choice",
                        "instructions":
                        f"The gap was classified as {gap_type}. Which single "
                        f"root origin is accountable - the underlying cause "
                        f"that must be fixed?",
                        "criteria": dict(ROOT_ORIGIN_DEFINITIONS)},
    })
    root_probs = dict(res["answers"]["root_origin"]["probabilities"])
    root_origin = _ranked(root_probs)[0][0]

    return {"gap_prob": gap_prob, "gap_type": gap_type,
            "type_probs": type_probs, "root_origin": root_origin,
            "root_probs": root_probs, "model": model}


_BACKENDS = {"jev": _jev_record, "laya": _laya_record}


# ---------------------------------------------------------------------------
# Step 3 - deterministic code: thresholds + citation check. Backend-agnostic.
# ---------------------------------------------------------------------------
def _citation_ok(record) -> bool:
    """A NOT_FOUND record cites its absence (location is the citation).
    A FOUND record with an empty excerpt is a broken citation."""
    if _field(record, "status") == "NOT_FOUND":
        return True
    return bool(_field(record, "excerpt"))


def _build_verdict(record, result: dict) -> GapVerdict:
    criterion_id = _field(record, "criterion_id")
    paraphrase = _field(record, "criterion_paraphrase")
    excerpt = _field(record, "excerpt")
    gap_prob = result["gap_prob"]

    if result["gap_type"] is None:
        return GapVerdict(
            criterion_id=criterion_id, verdict="SATISFIED",
            gap_confidence=gap_prob, criterion_paraphrase=paraphrase,
            evidence_excerpt=excerpt)

    ranked = _ranked(result["type_probs"])
    type_conf = ranked[0][1]
    runner_up, runner_up_conf = ranked[1]
    root_ranked = _ranked(result["root_probs"])
    root_conf = root_ranked[0][1]

    review_reasons = []
    if gap_prob < REVIEW_GAP_PROB:
        review_reasons.append(f"borderline gap call (P={gap_prob:.2f})")
    if type_conf < CLASS_THRESHOLD:
        review_reasons.append(f"low type confidence (P={type_conf:.2f})")
    if root_conf < CLASS_THRESHOLD:
        review_reasons.append(f"low origin confidence (P={root_conf:.2f})")
    if type_conf - runner_up_conf < REVIEW_MARGIN:
        # Two types nearly tied: the Tony case, decided by a human.
        review_reasons.append(
            f"ambiguous between {ranked[0][0]} and {runner_up} "
            f"(margin {type_conf - runner_up_conf:.2f})")
    if not _citation_ok(record):
        review_reasons.append("citation check failed: empty excerpt")

    return GapVerdict(
        criterion_id=criterion_id, verdict="GAP",
        gap_type=GapType(result["gap_type"]), gap_confidence=gap_prob,
        type_confidence=type_conf,
        root_origin=RootOrigin(result["root_origin"]),
        root_confidence=root_conf,
        # The runner-up is not a second label - it is trace's starting lead
        # on contributing factors.
        considered_alternative=f"{runner_up} (P={runner_up_conf:.2f})",
        needs_human_review=bool(review_reasons),
        review_reason="; ".join(review_reasons),
        criterion_paraphrase=paraphrase, evidence_excerpt=excerpt)


def classify_evidence(evidence: list, backend: str = "jev") -> tuple[list, dict]:
    """Run steps 2+3 over every evidence record with the chosen backend.

    Returns (verdicts, check). check carries the backend name, gap rate,
    mean type confidence, the human-review list (step 4), the model name,
    and the thresholds applied.
    """
    if backend not in _BACKENDS:
        raise ValueError(f"unknown backend {backend!r}; want one of "
                         f"{sorted(_BACKENDS)}")
    run_record = _BACKENDS[backend]

    verdicts, needs_review, model = [], [], backend
    for record in evidence:
        # Separation rule: the checker input is built from the allowlist
        # only. A reasoning leak raises here, before any backend call.
        result = run_record(_checker_input(record))
        model = result["model"]
        verdict = _build_verdict(record, result)
        verdicts.append(verdict)
        if verdict.needs_human_review:
            needs_review.append(verdict.criterion_id)

    gaps = [v for v in verdicts if v.verdict == "GAP"]
    check = {
        "backend": backend,
        "gap_rate": len(gaps) / len(verdicts) if verdicts else 0.0,
        "mean_type_confidence": (
            sum(v.type_confidence for v in gaps) / len(gaps) if gaps else 0.0),
        "needs_review": needs_review,  # step 4 reads this.
        "model": model,
        "thresholds": {
            "gap": GAP_THRESHOLD, "review_gap_prob": REVIEW_GAP_PROB,
            "class": CLASS_THRESHOLD, "margin": REVIEW_MARGIN,
        },
    }
    return verdicts, check


def default_backend() -> str:
    """CLASSIFY_BACKEND env var, "jev" if unset. Lets the whole pipeline flip
    backends without a code change."""
    return os.environ.get("CLASSIFY_BACKEND", "jev")
