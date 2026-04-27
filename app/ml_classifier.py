"""Second-tier emotion classifier using ``SamLowe/roberta-base-go_emotions``.

This wraps a pretrained 28-emotion classifier and maps a subset of the
negative-affect labels to the existing :class:`RiskLevel` taxonomy. The
intent is to catch oblique distress that the regex-based first tier misses
("ugh today was rough", "I just keep messing things up") without claiming
clinical capability the model doesn't have.

Design choices documented in ``docs/ethics-mapping.md``:

- The classifier can only ELEVATE to ``LOW``. ``MEDIUM`` and ``HIGH`` stay
  reserved for explicit ideation / plan / means signals from the regex
  tier — an emotion classifier shouldn't fabricate clinical urgency from
  emotional tone alone.
- Per-label scores above threshold are returned in ``matched`` so a
  reviewer can audit *why* the classifier flagged.
- Loaded lazily and behind a config flag so the container can boot even
  if the model is unavailable; if loading fails we log a warning and
  fall back to the regex-only path (fail open, don't block the chat).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from threading import Lock

from .config import settings
from .guardrail import RiskLevel

log = logging.getLogger(__name__)

# Distress-relevant labels from the 28-label go_emotions taxonomy. Picked
# deliberately and conservatively — these are the labels whose presence
# tracks the kind of phrasings the regex tier was missing on
# ("feeling really down", "no friends", "I just keep failing").
_DISTRESS_LABELS = frozenset({
    "sadness",
    "grief",
    "disappointment",
    "remorse",
    "fear",
    "nervousness",
})

_pipeline = None
_pipeline_lock = Lock()
_load_failed = False


def _get_pipeline():
    global _pipeline, _load_failed
    if _pipeline is not None or _load_failed:
        return _pipeline
    with _pipeline_lock:
        if _pipeline is not None or _load_failed:
            return _pipeline
        try:
            # Local import keeps the cold path cheap — importing transformers
            # eagerly slows tests + boot when the classifier is disabled.
            from transformers import pipeline as hf_pipeline
            _pipeline = hf_pipeline(
                "text-classification",
                model=settings.ml_classifier_model,
                top_k=None,
                truncation=True,
                max_length=256,
            )
            log.info("ml_classifier loaded: %s", settings.ml_classifier_model)
        except Exception as e:
            log.warning(
                "ml_classifier failed to load (%s); falling back to regex-only.", e
            )
            _load_failed = True
    return _pipeline


@dataclass
class MLAssessment:
    risk: RiskLevel = RiskLevel.NONE
    matched: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)


def assess_ml(text: str) -> MLAssessment:
    """Run the emotion classifier on a single message.

    Returns NONE risk + empty matches if the classifier is disabled, the
    model failed to load, the text is too short to be meaningful, or no
    distress label crosses the configured threshold.
    """
    if not settings.enable_ml_classifier or not text or not text.strip():
        return MLAssessment()
    if len(text.split()) < settings.ml_classifier_min_words:
        return MLAssessment()
    pipe = _get_pipeline()
    if pipe is None:
        return MLAssessment()

    try:
        out = pipe(text)
    except Exception as e:
        log.warning("ml_classifier inference error: %s", e)
        return MLAssessment()

    # transformers pipelines return [[{label, score}, ...]] for top_k=None.
    raw = out[0] if (out and isinstance(out[0], list)) else out
    scores = {item["label"]: float(item["score"]) for item in raw}
    threshold = settings.ml_classifier_threshold
    matched = sorted(
        (
            f"ml:{label}={scores[label]:.2f}"
            for label in _DISTRESS_LABELS
            if scores.get(label, 0.0) >= threshold
        ),
        key=lambda s: -float(s.rsplit("=", 1)[1]),
    )
    risk = RiskLevel.LOW if matched else RiskLevel.NONE
    return MLAssessment(risk=risk, matched=matched, scores=scores)
