"""Explainable priority engine (decision support, not a validated risk model).

    P = 0.45 R + 0.25 L + 0.20 A + 0.10 C        (all components in [0, 1])

R  human-reviewed safety risk, 1..5 mapped to (n-1)/4 → 0, .25, .5, .75, 1.
   Unknown (not yet reviewed) contributes 0 and marks the score PROVISIONAL.
   Model confidence is never used as R.
L  reviewed location sensitivity, 0 (none), 1 (some), 2 (high) → 0, .5, 1.
   Unknown contributes 0 and marks the score PROVISIONAL. There is no automatic
   school/hospital lookup; it must be set by a reviewer with a rationale.
A  unresolved age = min(age_days / AGE_CAP_DAYS, 1). Age is measured from
   submission to now (or to resolution time, if resolved). Computed on read.
C  corroboration = min(distinct_other_reporters / CORROBORATION_CAP, 1).
   Only distinct accounts other than the original reporter, from reviewer-
   confirmed duplicate links, count. Repeat submissions by one account count once.

A staff override replaces P (with a mandatory reason recorded in history).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

RISK_LABELS = {1: "1 – Minimal", 2: "2 – Low", 3: "3 – Moderate", 4: "4 – High", 5: "5 – Severe"}
LOCATION_LABELS = {0: "0 – No special sensitivity", 1: "1 – Some (busy road, junction)",
                   2: "2 – High (reviewed: school/hospital entrance, main crossing)"}


def normalize_risk(level: int | None) -> float | None:
    if level is None:
        return None
    if level not in RISK_LABELS:
        raise ValueError("risk level must be 1..5")
    return (level - 1) / 4


def normalize_location(level: int | None) -> float | None:
    if level is None:
        return None
    if level not in LOCATION_LABELS:
        raise ValueError("location sensitivity must be 0..2")
    return level / 2


def normalize_age(created_at: datetime, now: datetime, cap_days: int, resolved_at: datetime | None = None) -> float:
    end = resolved_at or now
    days = max((end - created_at).total_seconds() / 86400.0, 0.0)
    return min(days / cap_days, 1.0) if cap_days > 0 else 1.0


def normalize_corroboration(reporter_ids, original_reporter_id: int, cap: int) -> float:
    distinct = {r for r in reporter_ids if r is not None and r != original_reporter_id}
    return min(len(distinct) / cap, 1.0) if cap > 0 else 0.0


@dataclass
class PriorityResult:
    components: dict
    weights: dict
    computed: float
    total: float
    band: str
    provisional: bool
    overridden: bool
    missing: list = field(default_factory=list)
    rationale: list = field(default_factory=list)


def band_for(score: float, bands) -> str:
    for threshold, name in bands:
        if score >= threshold:
            return name
    return bands[-1][1]


def compute(*, risk_level, location_level, created_at, now, resolved_at=None,
            corroborating_reporter_ids=(), reporter_id=None, override=None, config) -> PriorityResult:
    w = config["PRIORITY_WEIGHTS"]
    r = normalize_risk(risk_level)
    l_ = normalize_location(location_level)
    a = normalize_age(created_at, now, config["PRIORITY_AGE_CAP_DAYS"], resolved_at)
    c = normalize_corroboration(corroborating_reporter_ids, reporter_id, config["PRIORITY_CORROBORATION_CAP"])

    missing = []
    rationale = []
    if r is None:
        missing.append("R")
        rationale.append("Safety risk not yet reviewed; R counted as 0 (unknown, not 'low').")
    else:
        rationale.append(f"Reviewed risk {RISK_LABELS[risk_level]} → R = {r:.2f}.")
    if l_ is None:
        missing.append("L")
        rationale.append("Location sensitivity not yet reviewed; L counted as 0 (unknown).")
    else:
        rationale.append(f"Location sensitivity {LOCATION_LABELS[location_level]} → L = {l_:.2f}.")
    rationale.append(f"Age capped at {config['PRIORITY_AGE_CAP_DAYS']} days → A = {a:.2f}.")
    rationale.append(f"Distinct corroborating reporters (cap {config['PRIORITY_CORROBORATION_CAP']}) → C = {c:.2f}.")

    comps = {"R": r, "L": l_, "A": a, "C": c}
    computed = sum(w[k] * (v or 0.0) for k, v in comps.items())
    computed = round(min(max(computed, 0.0), 1.0), 4)
    total = computed
    overridden = override is not None
    if overridden:
        total = round(min(max(float(override), 0.0), 1.0), 4)
        rationale.append(f"Staff override applied: {total:.2f} (computed {computed:.2f}).")
    return PriorityResult(components=comps, weights=w, computed=computed, total=total,
                          band=band_for(total, config["PRIORITY_BANDS"]), provisional=bool(missing) and not overridden,
                          overridden=overridden, missing=missing, rationale=rationale)


def for_complaint(complaint, config, now, corroborating_reporter_ids=()) -> PriorityResult:
    return compute(risk_level=complaint.reviewed_risk, location_level=complaint.location_sensitivity,
                   created_at=complaint.created_at, now=now, resolved_at=complaint.resolved_at,
                   corroborating_reporter_ids=corroborating_reporter_ids, reporter_id=complaint.reporter_id,
                   override=complaint.priority_override, config=config)
