from flask import Blueprint, render_template
from sqlalchemy import func

from ..extensions import db
from ..models import Complaint

bp = Blueprint("public", __name__)


@bp.route("/")
def home():
    # Privacy-preserving aggregates only (no locations, identities or evidence).
    rows = (db.session.query(Complaint.is_demo, Complaint.submitted_category, func.count())
            .group_by(Complaint.is_demo, Complaint.submitted_category).all())
    stats = {"real": {}, "demo": {}}
    for is_demo, cat, n in rows:
        stats["demo" if is_demo else "real"][cat] = n
    resolved = dict(db.session.query(Complaint.is_demo, func.count())
                    .filter(Complaint.status == "resolved").group_by(Complaint.is_demo).all())
    return render_template("public/home.html", stats=stats, resolved=resolved)


@bp.route("/guidance")
def guidance():
    return render_template("public/guidance.html")


@bp.route("/privacy")
def privacy():
    return render_template("public/privacy.html")
