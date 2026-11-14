from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..ai import text as text_ai
from ..ai.image import get_image_detector
from ..auth_utils import get_complaint_for_citizen_or_404, roles_required
from ..categories import CATEGORIES
from ..extensions import db, limiter
from ..models import (Attachment, Complaint, Feedback, InferenceRecord, Notification, ReopenRequest, Role,
                      StatusEvent, utcnow)
from ..services import priority
from ..services.geo import valid_coordinates
from ..services.storage import UploadError, safe_path, validate_and_store_image
from ..services.workflow import OPEN_STATUSES, notify, record_event

bp = Blueprint("citizen", __name__, url_prefix="/me")


def _parse_observed(value: str):
    tz = ZoneInfo(current_app.config["DISPLAY_TZ"])
    try:
        local = datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=tz)
    except (TypeError, ValueError):
        return None, "Enter the date and time you observed the issue."
    utc = local.astimezone(timezone.utc).replace(tzinfo=None)
    now = utcnow()
    if utc > now + timedelta(minutes=10):
        return None, "Observation time cannot be in the future."
    if utc < now - timedelta(days=365):
        return None, "Observation time must be within the last year."
    return utc, None


@bp.route("/")
@roles_required(Role.CITIZEN)
def dashboard():
    mine = Complaint.query.filter_by(reporter_id=current_user.id)
    counts = {
        "total": mine.count(),
        "open": mine.filter(Complaint.status.in_(OPEN_STATUSES)).count(),
        "resolved": mine.filter(Complaint.status == "resolved").count(),
    }
    recent = mine.order_by(Complaint.created_at.desc()).limit(5).all()
    return render_template("citizen/dashboard.html", counts=counts, recent=recent)


@bp.route("/complaints/new", methods=["GET", "POST"])
@roles_required(Role.CITIZEN)
@limiter.limit(lambda: current_app.config["SUBMIT_RATE_LIMIT"], methods=["POST"])
def new_complaint():
    cfg = current_app.config
    detector = get_image_detector(cfg)
    errors, form = {}, {}
    if request.method == "POST":
        form = request.form.to_dict()
        description = form.get("description", "").strip()
        landmark = form.get("landmark", "").strip()
        category = form.get("category", "")
        lat, lon = form.get("latitude"), form.get("longitude")
        source = form.get("location_source") if form.get("location_source") in ("geolocation", "manual") else "manual"

        if not (cfg["DESCRIPTION_MIN"] <= len(description) <= cfg["DESCRIPTION_MAX"]):
            errors["description"] = f"Description must be {cfg['DESCRIPTION_MIN']}–{cfg['DESCRIPTION_MAX']} characters."
        if len(landmark) > cfg["LANDMARK_MAX"]:
            errors["landmark"] = f"Landmark must be at most {cfg['LANDMARK_MAX']} characters."
        if category not in CATEGORIES:
            errors["category"] = "Choose a category."
        if not valid_coordinates(lat, lon):
            errors["location"] = "Set the location using your device or by clicking on the map."
        observed, err = _parse_observed(form.get("observed_at", ""))
        if err:
            errors["observed_at"] = err
        if not form.get("consent"):
            errors["consent"] = "Please confirm the consent statement."

        primary = request.files.get("image")
        extras = [f for f in request.files.getlist("extra_images") if f and f.filename]
        if not primary or not primary.filename:
            errors["image"] = "One photo of the issue is required."
        if len(extras) > cfg["MAX_EXTRA_IMAGES"]:
            errors["extra_images"] = f"At most {cfg['MAX_EXTRA_IMAGES']} additional photos."

        stored = []
        if not errors:
            try:
                stored.append(("evidence", validate_and_store_image(primary, cfg["UPLOAD_DIR"], cfg)))
                for f in extras:
                    stored.append(("evidence", validate_and_store_image(f, cfg["UPLOAD_DIR"], cfg)))
            except UploadError as exc:
                errors["image"] = str(exc)

        if errors:
            _cleanup(stored)
            return render_template("citizen/new_complaint.html", errors=errors, form=form, detector=detector), 400

        try:
            c = Complaint(reporter_id=current_user.id, description=description, landmark=landmark or None,
                          observed_at=observed, latitude=float(lat), longitude=float(lon), location_source=source,
                          submitted_category=category, consent_given_at=utcnow(), is_demo=current_user.is_demo)
            db.session.add(c)
            db.session.flush()
            for kind, s in stored:
                db.session.add(Attachment(complaint_id=c.id, uploaded_by_id=current_user.id, kind=kind,
                                          stored_name=s.stored_name, mime_type=s.mime_type, width=s.width,
                                          height=s.height, size_bytes=s.size_bytes))
            # Original automated outputs, stored separately from the citizen's choice.
            img_result = detector.predict(safe_path(cfg["UPLOAD_DIR"], stored[0][1].stored_name))
            db.session.add(InferenceRecord(complaint_id=c.id, kind="image", method=img_result.method,
                                           model_id=img_result.model_id, status=img_result.status,
                                           output_json=img_result.to_dict()))
            sugg = text_ai.suggest(description)
            db.session.add(InferenceRecord(complaint_id=c.id, kind="text", method=sugg.method, model_id=sugg.version,
                                           status="ok", output_json=sugg.to_dict()))
            db.session.add(StatusEvent(complaint_id=c.id, actor_id=current_user.id, event_type="status",
                                       from_status=None, to_status="submitted",
                                       public_note="Complaint submitted.",
                                       details={"category_suggestion_followed":
                                                sugg.category == category if sugg.category else None}))
            notify(current_user.id, c, f"Complaint {c.public_id} was received.")
            db.session.commit()
        except Exception:
            db.session.rollback()
            _cleanup(stored)
            raise
        return redirect(url_for("citizen.submitted", public_id=c.public_id))

    return render_template("citizen/new_complaint.html", errors=errors, form=form, detector=detector)


def _cleanup(stored):
    for _, s in stored:
        try:
            os.remove(safe_path(current_app.config["UPLOAD_DIR"], s.stored_name))
        except (OSError, UploadError):
            pass


@bp.route("/complaints/<public_id>/submitted")
@roles_required(Role.CITIZEN)
def submitted(public_id):
    c = get_complaint_for_citizen_or_404(public_id)
    return render_template("citizen/submitted.html", c=c)


@bp.route("/complaints")
@roles_required(Role.CITIZEN)
def my_complaints():
    items = (Complaint.query.filter_by(reporter_id=current_user.id)
             .order_by(Complaint.created_at.desc()).all())
    return render_template("citizen/my_complaints.html", items=items)


@bp.route("/complaints/<public_id>")
@roles_required(Role.CITIZEN)
def complaint_detail(public_id):
    c = get_complaint_for_citizen_or_404(public_id)
    pr = priority.for_complaint(c, current_app.config, utcnow())
    pending = ReopenRequest.query.filter_by(complaint_id=c.id, state="pending").first()
    return render_template("citizen/complaint_detail.html", c=c, pr=pr, pending_reopen=pending,
                           open_statuses=OPEN_STATUSES)


@bp.route("/complaints/<public_id>/category", methods=["POST"])
@roles_required(Role.CITIZEN)
def correct_category(public_id):
    c = get_complaint_for_citizen_or_404(public_id)
    new = request.form.get("category", "")
    if c.status != "submitted":
        flash("The category can only be corrected before review starts. Add a clarification instead.", "warning")
    elif new not in CATEGORIES:
        flash("Choose a valid category.", "danger")
    elif new != c.submitted_category:
        old = c.submitted_category
        c.submitted_category = new
        record_event(c, current_user, "category", public_note=f"Citizen corrected category to {CATEGORIES[new]}.",
                     details={"from": old, "to": new, "by": "citizen"})
        db.session.commit()
        flash("Category updated.", "success")
    return redirect(url_for("citizen.complaint_detail", public_id=public_id))


@bp.route("/complaints/<public_id>/clarify", methods=["POST"])
@roles_required(Role.CITIZEN)
def clarify(public_id):
    c = get_complaint_for_citizen_or_404(public_id)
    cfg = current_app.config
    if c.status not in OPEN_STATUSES:
        flash("Clarifications can only be added to open complaints.", "warning")
        return redirect(url_for("citizen.complaint_detail", public_id=public_id))
    note = request.form.get("note", "").strip()
    f = request.files.get("image")
    if not note and not (f and f.filename):
        flash("Add a note or a photo.", "danger")
        return redirect(url_for("citizen.complaint_detail", public_id=public_id))
    if len(note) > cfg["DESCRIPTION_MAX"]:
        flash("Clarification is too long.", "danger")
        return redirect(url_for("citizen.complaint_detail", public_id=public_id))
    existing = sum(1 for a in c.attachments if a.uploaded_by_id == current_user.id)
    stored = None
    if f and f.filename:
        if existing >= cfg["MAX_EXTRA_IMAGES"] + 2:
            flash("Photo limit for this complaint reached.", "danger")
            return redirect(url_for("citizen.complaint_detail", public_id=public_id))
        try:
            stored = validate_and_store_image(f, cfg["UPLOAD_DIR"], cfg)
        except UploadError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("citizen.complaint_detail", public_id=public_id))
        db.session.add(Attachment(complaint_id=c.id, uploaded_by_id=current_user.id, kind="clarification",
                                  stored_name=stored.stored_name, mime_type=stored.mime_type, width=stored.width,
                                  height=stored.height, size_bytes=stored.size_bytes))
    record_event(c, current_user, "clarification", public_note=note or "Citizen added a photo.",
                 details={"photo": bool(stored)})
    db.session.commit()
    flash("Clarification added.", "success")
    return redirect(url_for("citizen.complaint_detail", public_id=public_id))


@bp.route("/complaints/<public_id>/reopen", methods=["GET", "POST"])
@roles_required(Role.CITIZEN)
def reopen(public_id):
    c = get_complaint_for_citizen_or_404(public_id)
    if c.status != "resolved":
        flash("Only resolved complaints can be reopened.", "warning")
        return redirect(url_for("citizen.complaint_detail", public_id=public_id))
    if ReopenRequest.query.filter_by(complaint_id=c.id, state="pending").first():
        flash("A reopening request is already pending review.", "info")
        return redirect(url_for("citizen.complaint_detail", public_id=public_id))
    error = None
    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        if not (10 <= len(reason) <= 1000):
            error = "Explain why the issue is not resolved (10–1000 characters)."
        else:
            req = ReopenRequest(complaint_id=c.id, requested_by_id=current_user.id, reason=reason)
            db.session.add(req)
            record_event(c, current_user, "reopen_request", public_note=f"Citizen requested reopening: {reason}")
            db.session.commit()
            flash("Reopening request sent for review. The complaint stays Resolved until a reviewer decides.",
                  "success")
            return redirect(url_for("citizen.complaint_detail", public_id=public_id))
    return render_template("citizen/reopen.html", c=c, error=error), (400 if error else 200)


@bp.route("/notifications", methods=["GET", "POST"])
@roles_required(Role.CITIZEN, Role.REVIEWER, Role.ADMIN)
def notifications():
    q = Notification.query.filter_by(user_id=current_user.id)
    if request.method == "POST":
        q.filter_by(is_read=False).update({"is_read": True})
        db.session.commit()
        return redirect(url_for("citizen.notifications"))
    items = q.order_by(Notification.created_at.desc()).limit(100).all()
    return render_template("citizen/notifications.html", items=items)


@bp.route("/feedback", methods=["GET", "POST"])
@roles_required(Role.CITIZEN, Role.REVIEWER, Role.ADMIN)
def feedback():
    error = None
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        rating = request.form.get("rating", type=int)
        if not (5 <= len(msg) <= 2000):
            error = "Feedback must be 5–2000 characters."
        elif rating is not None and not 1 <= rating <= 5:
            error = "Rating must be 1–5."
        else:
            db.session.add(Feedback(user_id=current_user.id, rating=rating, message=msg))
            db.session.commit()
            flash("Thank you for your feedback.", "success")
            return redirect(url_for("citizen.feedback"))
    return render_template("citizen/feedback.html", error=error), (400 if error else 200)
