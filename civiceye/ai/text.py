"""Text category suggestion.

RULE-BASED KEYWORD BASELINE. This is not a trained model. Scores are keyword-hit
fractions, NOT calibrated probabilities, and have not been evaluated on real
data. A TF-IDF + logistic-regression model can replace this once a genuine,
explicitly prepared labelled dataset exists. This module never retrains itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

METHOD = "rule_based_keywords"
VERSION = "keywords-v1"

KEYWORDS = {
    "pothole": ["pothole", "pot hole", "crater", "road damage", "broken road", "crack", "cracked road",
                "uneven road", "gundi", "road caved", "tar"],
    "garbage": ["garbage", "trash", "litter", "waste", "dump", "rubbish", "plastic", "bin", "kasa", "smell",
                "stink", "debris"],
    "waterlogging": ["waterlogging", "water logging", "flooded", "flooding", "stagnant water", "water stagnation",
                     "puddle", "drain overflow", "clogged drain", "rain water"],
    "streetlight": ["streetlight", "street light", "lamp post", "light not working", "dark street", "no light",
                    "bulb", "lamp"],
}


@dataclass
class TextSuggestion:
    category: str | None
    score: float  # heuristic keyword score, not a probability
    matched: list[str]
    method: str = METHOD
    version: str = VERSION

    def to_dict(self):
        return {"category": self.category, "score": self.score, "matched": self.matched,
                "method": self.method, "version": self.version}


def suggest(text: str) -> TextSuggestion:
    t = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    hits = {}
    for cat, words in KEYWORDS.items():
        found = [w for w in words if re.search(r"\b" + re.escape(w) + r"\b", t)]
        if found:
            hits[cat] = found
    if not hits:
        return TextSuggestion(None, 0.0, [])
    total = sum(len(v) for v in hits.values())
    best = max(hits, key=lambda k: len(hits[k]))
    tied = [k for k in hits if len(hits[k]) == len(hits[best])]
    if len(tied) > 1:
        return TextSuggestion(None, 0.0, sorted({w for k in tied for w in hits[k]}))
    return TextSuggestion(best, round(len(hits[best]) / total, 2), hits[best])
