"""Singleton FinBERT pipeline (Finance sentiment)."""

from __future__ import annotations

import threading
from typing import Any

from app.core.config import get_settings

_lock = threading.Lock()
_pipeline = None


def get_finbert() -> Any:
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    with _lock:
        if _pipeline is not None:
            return _pipeline
        from transformers import pipeline

        cfg = get_settings()
        device = int(cfg.finbert_device)
        if device >= 0:
            try:
                import torch as _torch  # noqa: F401

                if not _torch.cuda.is_available():
                    device = -1
            except Exception:
                device = -1

        _pipeline = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            return_all_scores=True,
            device=device,
            truncation=True,
            max_length=512,
        )
        return _pipeline


def score_single_with_pipe(pipe: Any, text: str) -> dict[str, float]:
    safe = text[:512].replace("\n", " ").strip()
    if not safe:
        return {"positive": 0.0, "negative": 0.0, "neutral": 1.0, "composite": 0.0}

    scores = pipe(safe)[0]
    pmap = {s["label"].lower(): float(s["score"]) for s in scores}
    labeled = sorted(scores, key=lambda x: -x["score"])[0]
    lbl = labeled["label"].lower()
    if lbl == "positive":
        composite = float(labeled["score"])
    elif lbl == "negative":
        composite = -float(labeled["score"])
    else:
        composite = 0.0

    return {
        "positive": pmap.get("positive", 0.0),
        "negative": pmap.get("negative", 0.0),
        "neutral": pmap.get("neutral", 0.0),
        "composite": composite,
    }


def score_headline(text: str) -> dict[str, float]:
    return score_single_with_pipe(get_finbert(), text)
