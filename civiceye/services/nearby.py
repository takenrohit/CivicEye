"""Nearby-report lookup (phase 1 foundation for potential-duplicate review).

Location proximity alone is NOT proof of a duplicate. Nothing here links,
merges, rejects or deletes complaints.
"""
from __future__ import annotations

from datetime import timedelta

from ..models import Complaint, utcnow
from .geo import bounding_box, haversine_m


def find_nearby(lat: float, lon: float, *, radius_m: float, window_days: int, is_demo: bool,
                exclude_id: int | None = None, category: str | None = None, include_rejected: bool = True,
                limit: int = 10):
    """Reports within radius_m and window_days, from the same data set (demo or real) only."""
    lo_lat, hi_lat, lo_lon, hi_lon = bounding_box(lat, lon, radius_m)
    since = utcnow() - timedelta(days=window_days)
    q = Complaint.query.filter(Complaint.latitude.between(lo_lat, hi_lat),
                               Complaint.longitude.between(lo_lon, hi_lon),
                               Complaint.created_at >= since,
                               Complaint.is_demo.is_(bool(is_demo)))
    if not include_rejected:
        q = q.filter(Complaint.status != "rejected")
    if exclude_id is not None:
        q = q.filter(Complaint.id != exclude_id)
    out = []
    for c in q.all():
        d = haversine_m(lat, lon, c.latitude, c.longitude)
        if d <= radius_m:
            same = category is None or c.effective_category == category
            out.append({"complaint": c, "distance_m": round(d, 1), "same_category": same})
    out.sort(key=lambda r: (not r["same_category"], r["distance_m"]))
    return out[:limit]
