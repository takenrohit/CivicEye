"""Small JSON endpoints used by the complaint form. Authenticated; no personal data returned."""
from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from ..ai import text as text_ai
from ..categories import CATEGORIES
from ..extensions import limiter
from ..services.geo import valid_coordinates
from ..services.nearby import find_nearby
from ..services.workflow import STATUS_LABELS

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/suggest-category", methods=["POST"])
@login_required
@limiter.limit("60 per minute")
def suggest_category():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", ""))[:2000]
    s = text_ai.suggest(text)
    return jsonify({
        **s.to_dict(),
        "category_label": CATEGORIES.get(s.category) if s.category else None,
        "disclaimer": "Keyword rule, not a trained AI model. The score is not a probability.",
    })


@bp.route("/nearby")
@login_required
@limiter.limit("60 per minute")
def nearby():
    lat, lon = request.args.get("lat"), request.args.get("lon")
    if not valid_coordinates(lat, lon):
        return jsonify({"error": "invalid coordinates"}), 400
    cfg = current_app.config
    cat = request.args.get("category")
    # Same data set as the user's own reports (demo accounts see demo data only);
    # rejected reports are not "existing reports" for the citizen.
    rows = find_nearby(float(lat), float(lon), radius_m=cfg["DUPLICATE_RADIUS_M"],
                       window_days=cfg["DUPLICATE_WINDOW_DAYS"], is_demo=current_user.is_demo,
                       category=cat if cat in CATEGORIES else None, include_rejected=False)
    # Deliberately excludes IDs, reporter, description, images and exact coordinates.
    return jsonify({
        "radius_m": cfg["DUPLICATE_RADIUS_M"], "window_days": cfg["DUPLICATE_WINDOW_DAYS"],
        "results": [{"distance_m": round(r["distance_m"]), "category": CATEGORIES.get(r["complaint"].effective_category),
                     "status": STATUS_LABELS[r["complaint"].status], "same_category": r["same_category"]}
                    for r in rows],
    })
