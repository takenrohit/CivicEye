"""Reviewer / administrator views."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from ..auth_utils import roles_required
from ..blueprints.auth import EMAIL_RE, validate_password
from ..categories import CATEGORIES
from ..extensions import db
from ..models import (Assignment, Attachment, AuditEvent, CategoryDepartment, Complaint, Department, Feedback,
                      ReopenRequest, Role, User, utcnow)
from ..services import priority
from ..services.exports import to_csv
from ..services.nearby import find_nearby
from ..services.storage import UploadError, validate_and_store_image
from ..services.workflow import (OPEN_STATUSES, STATUS_LABELS, WorkflowError, allowed_next, approve_reopen,
                                 change_status, decline_reopen, notify, record_event)

bp = Blueprint("staff", __name__, url_prefix="/staff")
STAFF = (Role.REVIEWER, Role.ADMIN)


def can_act(user, c: Complaint) -> bool:
    """Object-level permission to modify a complaint."""
    if user.is_admin:
        return True
    if c.assigned_to_id in (None, user.id):
        return True
    return bool(user.department_id and c.department_id == user.department_id)


def _get(public_id) -> Complaint:
    c = Complaint.query.filter_by(public_id=public_id).first()
    if c is None:
        abort(404)
    return c


def _require_act(c):
    if not can_act(current_user, c):
        abort(403)


def _priority(c, now=None):
    return priority.for_complaint(c, current_app.config, now or utcnow())


def _data_filter(q, data):
    if data == "real":
        return q.filter(Complaint.is_demo.is_(False))
    if data == "demo":
        return q.filter(Complaint.is_demo.is_(True))
    return q


def _parse_date(s, end=False):
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=ZoneInfo(current_app.config["DISPLAY_TZ"]))
    except ValueError:
        return None
    if end:
        d += timedelta(days=1)
    return d.astimezone(timezone.utc).replace(tzinfo=None)


def _filtered_query(args):
    q = _data_filter(Complaint.query, args.get("data", "all"))
    if (cat := args.get("category")) in CATEGORIES:
        q = q.filter(db.func.coalesce(Complaint.reviewed_category, Complaint.submitted_category) == cat)
    if (st := args.get("status")) in STATUS_LABELS:
        q = q.filter(Complaint.status == st)
    if (dep := args.get("department", type=int)):
        q = q.filter(Complaint.department_id == dep)
    if (d := _parse_date(args.get("from"))):
        q = q.filter(Complaint.created_at >= d)
    if (d := _parse_date(args.get("to"), end=True)):
        q = q.filter(Complaint.created_at < d)
    if args.get("mine"):
        q = q.filter(Complaint.assigned_to_id == current_user.id)
    if (lm := args.get("landmark", "").strip()):
        q = q.filter(Complaint.landmark.ilike(f"%{lm[:60]}%"))
    return q.order_by(Complaint.created_at.desc())


@bp.route("/")
@roles_required(*STAFF)
def dashboard():
    data = request.args.get("data", "all")
    base = _data_filter(Complaint.query, data)
    total = base.count()
    by_status = dict(_data_filter(db.session.query(Complaint.status, func.count()), data)
                     .group_by(Complaint.status).all())
    cat_expr = func.coalesce(Complaint.reviewed_category, Complaint.submitted_category)
    by_category = dict(_data_filter(db.session.query(cat_expr, func.count()), data).group_by(cat_expr).all())
    unreviewed = base.filter(Complaint.status == "submitted").order_by(Complaint.created_at).limit(10).all()
    now = utcnow()
    open_items = base.filter(Complaint.status.in_(OPEN_STATUSES)).all()
    scored = sorted(((c, _priority(c, now)) for c in open_items), key=lambda t: -t[1].total)
    high = [(c, p) for c, p in scored if p.band == "High"][:10]
    resolved = base.filter(Complaint.status == "resolved", Complaint.resolved_at.isnot(None)).all()
    res_days = [(c.resolved_at - c.created_at).total_seconds() / 86400 for c in resolved]
    resolution = {"n": len(res_days),
                  "median_days": round(sorted(res_days)[len(res_days) // 2], 1) if res_days else None,
                  "unresolved": len(open_items)}
    reopened_count = by_status.get("reopened", 0)
    pending_reopen = ReopenRequest.query.filter_by(state="pending").count()
    return render_template("staff/dashboard.html", total=total, by_status=by_status, by_category=by_category,
                           unreviewed=unreviewed, high=high, resolution=resolution, data=data,
                           reopened_count=reopened_count, pending_reopen=pending_reopen,
                           provisional_count=sum(1 for _, p in scored if p.provisional))


@bp.route("/complaints")
@roles_required(*STAFF)
def complaints():
    q = _filtered_query(request.args)
    items = q.limit(500).all()
    now = utcnow()
    rows = [(c, _priority(c, now)) for c in items]
    band = request.args.get("band")
    if band in {b for _, b in current_app.config["PRIORITY_BANDS"]}:
        rows = [r for r in rows if r[1].band == band and not r[1].provisional]
    return render_template("staff/complaints.html", rows=rows, departments=Department.query.all(),
                           args=request.args)


@bp.route("/complaints/export.csv")
@roles_required(*STAFF)
def export_csv():
    items = _filtered_query(request.args).all()
    now = utcnow()
    header = ["complaint_id", "data_label", "created_utc", "status", "submitted_category", "reviewed_category",
              "department", "approx_lat", "approx_lon", "reviewed_risk", "location_sensitivity",
              "priority", "priority_band", "provisional", "landmark", "description"]
    rows = []
    for c in items:
        p = _priority(c, now)
        rows.append([c.public_id, "DEMO" if c.is_demo else "REAL", c.created_at.isoformat(), c.status,
                     c.submitted_category, c.reviewed_category or "", c.department.name if c.department else "",
                     round(c.latitude, 4), round(c.longitude, 4), c.reviewed_risk if c.reviewed_risk else "",
                     c.location_sensitivity if c.location_sensitivity is not None else "", p.total, p.band,
                     p.provisional, c.landmark or "", c.description])
    db.session.add(AuditEvent(actor_id=current_user.id, action="export.complaints_csv",
                              details={"rows": len(rows), "filters": request.args.to_dict()}))
    db.session.commit()
    # Reporter identities are deliberately excluded.
    return Response(to_csv(header, rows), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=civiceye_complaints.csv"})


@bp.route("/complaints/<public_id>")
@roles_required(*STAFF)
def review(public_id):
    c = _get(public_id)
    cfg = current_app.config
    nearby = find_nearby(c.latitude, c.longitude, radius_m=cfg["DUPLICATE_RADIUS_M"],
                         window_days=cfg["DUPLICATE_WINDOW_DAYS"], exclude_id=c.id, category=c.effective_category)
    for n in nearby:
        n["same_reporter"] = n["complaint"].reporter_id == c.reporter_id
    reviewers = User.query.filter(User.role.in_(STAFF), User.is_active_account.is_(True)).all()
    reopen_reqs = ReopenRequest.query.filter_by(complaint_id=c.id).order_by(ReopenRequest.created_at.desc()).all()
    mapped = db.session.get(CategoryDepartment, c.effective_category)
    suggested_dep = c.department_id or (mapped.department_id if mapped else None)
    return render_template("staff/review.html", c=c, pr=_priority(c), nearby=nearby, can_act=can_act(current_user, c),
                           suggested_dep=suggested_dep,
                           next_statuses=allowed_next(c.status), departments=Department.query.all(),
                           reviewers=reviewers, reopen_reqs=reopen_reqs, risk_labels=priority.RISK_LABELS,
                           location_labels=priority.LOCATION_LABELS, cfg=cfg)


def _back(c):
    return redirect(url_for("staff.review", public_id=c.public_id))


@bp.route("/complaints/<public_id>/category", methods=["POST"])
@roles_required(*STAFF)
def set_category(public_id):
    c = _get(public_id)
    _require_act(c)
    new = request.form.get("category")
    if new not in CATEGORIES:
        flash("Choose a valid category.", "danger")
        return _back(c)
    old = c.reviewed_category
    c.reviewed_category = new
    record_event(c, current_user, "category", public_note=f"Category confirmed by reviewer: {CATEGORIES[new]}.",
                 internal_note=request.form.get("internal_note", "").strip() or None,
                 details={"from": old, "to": new, "submitted": c.submitted_category, "by": "reviewer"})
    db.session.commit()
    flash("Reviewed category saved.", "success")
    return _back(c)


@bp.route("/complaints/<public_id>/risk", methods=["POST"])
@roles_required(*STAFF)
def set_risk(public_id):
    c = _get(public_id)
    _require_act(c)
    risk = request.form.get("reviewed_risk", type=int)
    loc = request.form.get("location_sensitivity")
    loc = int(loc) if loc not in (None, "", "unknown") and loc.isdigit() else None
    rationale = request.form.get("location_rationale", "").strip()[:255]
    if risk is not None and risk not in priority.RISK_LABELS:
        flash("Invalid risk level.", "danger")
        return _back(c)
    if loc is not None and loc not in priority.LOCATION_LABELS:
        flash("Invalid location sensitivity.", "danger")
        return _back(c)
    if loc and not rationale:
        flash("Give a rationale for non-zero location sensitivity (e.g. reviewed nearby school entrance).", "danger")
        return _back(c)
    before = {"risk": c.reviewed_risk, "location": c.location_sensitivity}
    c.reviewed_risk, c.location_sensitivity, c.location_rationale = risk, loc, rationale or None
    record_event(c, current_user, "risk", internal_note=request.form.get("internal_note", "").strip() or None,
                 details={"before": before, "after": {"risk": risk, "location": loc, "rationale": rationale}})
    db.session.commit()
    flash("Risk and location context saved.", "success")
    return _back(c)


@bp.route("/complaints/<public_id>/override", methods=["POST"])
@roles_required(*STAFF)
def set_override(public_id):
    c = _get(public_id)
    _require_act(c)
    reason = request.form.get("reason", "").strip()
    clear = request.form.get("clear")
    if not reason:
        flash("A priority override (or clearing one) requires a reason.", "danger")
        return _back(c)
    before = c.priority_override
    if clear:
        c.priority_override, c.priority_override_reason = None, None
    else:
        val = request.form.get("value", type=float)
        if val is None or not 0 <= val <= 1:
            flash("Override must be between 0 and 1.", "danger")
            return _back(c)
        c.priority_override, c.priority_override_reason = val, reason[:255]
    record_event(c, current_user, "priority_override", internal_note=reason,
                 details={"before": before, "after": c.priority_override})
    db.session.commit()
    flash("Priority override updated.", "success")
    return _back(c)


@bp.route("/complaints/<public_id>/assign", methods=["POST"])
@roles_required(*STAFF)
def assign(public_id):
    c = _get(public_id)
    _require_act(c)
    dep_id = request.form.get("department_id", type=int)
    assignee_id = request.form.get("assignee_id", type=int)
    dep = db.session.get(Department, dep_id) if dep_id else None
    assignee = db.session.get(User, assignee_id) if assignee_id else None
    if dep is None:
        flash("Choose a department.", "danger")
        return _back(c)
    if assignee is not None and not assignee.is_staff:
        flash("Assignee must be a reviewer.", "danger")
        return _back(c)
    c.department_id = dep.id
    c.assigned_to_id = assignee.id if assignee else None
    db.session.add(Assignment(complaint_id=c.id, department_id=dep.id, assignee_id=c.assigned_to_id,
                              assigned_by_id=current_user.id))
    record_event(c, current_user, "assignment", public_note=f"Routed to {dep.name}.",
                 details={"department_id": dep.id, "assignee_id": c.assigned_to_id})
    if assignee and assignee.id != current_user.id:
        notify(assignee.id, c, f"Complaint {c.public_id} was assigned to you.")
    db.session.commit()
    flash("Assignment saved.", "success")
    return _back(c)


@bp.route("/complaints/<public_id>/status", methods=["POST"])
@roles_required(*STAFF)
def set_status(public_id):
    c = _get(public_id)
    _require_act(c)
    try:
        change_status(c, request.form.get("status", ""), current_user,
                      public_note=request.form.get("public_note", ""),
                      internal_note=request.form.get("internal_note", ""))
        f = request.files.get("resolution_image")
        if c.status == "resolved" and f and f.filename:
            s = validate_and_store_image(f, current_app.config["UPLOAD_DIR"], current_app.config)
            db.session.add(Attachment(complaint_id=c.id, uploaded_by_id=current_user.id, kind="resolution",
                                      stored_name=s.stored_name, mime_type=s.mime_type, width=s.width,
                                      height=s.height, size_bytes=s.size_bytes))
        db.session.commit()
        flash(f"Status changed to {STATUS_LABELS[c.status]}.", "success")
    except (WorkflowError, UploadError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return _back(c)


@bp.route("/complaints/<public_id>/note", methods=["POST"])
@roles_required(*STAFF)
def add_note(public_id):
    c = _get(public_id)
    note = request.form.get("note", "").strip()
    visible = request.form.get("visibility") == "public"
    if not note:
        flash("Note is empty.", "danger")
        return _back(c)
    if visible:
        _require_act(c)
        record_event(c, current_user, "note", public_note=note[:2000])
        notify(c.reporter_id, c, f"New update on complaint {c.public_id}.")
    else:
        record_event(c, current_user, "note", internal_note=note[:2000])
    db.session.commit()
    flash("Note added.", "success")
    return _back(c)


@bp.route("/reopen-requests")
@roles_required(*STAFF)
def reopen_requests():
    items = ReopenRequest.query.order_by(ReopenRequest.state != "pending", ReopenRequest.created_at.desc()).limit(200).all()
    return render_template("staff/reopen_requests.html", items=items)


@bp.route("/reopen-requests/<int:req_id>", methods=["POST"])
@roles_required(*STAFF)
def decide_reopen(req_id):
    req = db.session.get(ReopenRequest, req_id) or abort(404)
    _require_act(req.complaint)
    note = request.form.get("note", "").strip()
    try:
        if request.form.get("decision") == "approve":
            approve_reopen(req, current_user, note)
        else:
            decline_reopen(req, current_user, note)
        db.session.commit()
        flash("Reopening request decided.", "success")
    except WorkflowError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(request.form.get("back") == "review" and url_for("staff.review", public_id=req.complaint.public_id)
                    or url_for("staff.reopen_requests"))


@bp.route("/map")
@roles_required(*STAFF)
def map_view():
    data = request.args.get("data", "all")
    items = _data_filter(Complaint.query, data).filter(Complaint.status != "rejected").all()
    now = utcnow()
    points = []
    for c in items:
        p = _priority(c, now)
        points.append({"id": c.public_id, "lat": c.latitude, "lon": c.longitude, "category": c.effective_category,
                       "category_label": CATEGORIES.get(c.effective_category), "status": STATUS_LABELS[c.status],
                       "priority": p.total, "band": p.band, "provisional": p.provisional, "demo": c.is_demo,
                       "url": url_for("staff.review", public_id=c.public_id)})
    return render_template("staff/map.html", points=points, data=data)


# ---------------- Administrator ----------------

@bp.route("/admin/users", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def admin_users():
    errors = {}
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            email = request.form.get("email", "").strip().lower()
            name = request.form.get("display_name", "").strip()
            pw = request.form.get("password", "")
            dep_id = request.form.get("department_id", type=int)
            if not EMAIL_RE.match(email):
                errors["email"] = "Invalid email."
            elif User.query.filter_by(email=email).first():
                errors["email"] = "Email already in use."
            if not 2 <= len(name) <= 80:
                errors["display_name"] = "Name must be 2–80 characters."
            if (m := validate_password(pw)):
                errors["password"] = m
            if not errors:
                u = User(email=email, display_name=name, role=Role.REVIEWER, department_id=dep_id or None)
                u.set_password(pw)
                db.session.add(u)
                db.session.flush()
                db.session.add(AuditEvent(actor_id=current_user.id, action="user.create_reviewer",
                                          target=f"user:{u.id}"))
                db.session.commit()
                flash("Reviewer account created (simulated project role).", "success")
                return redirect(url_for("staff.admin_users"))
        elif action == "toggle":
            u = db.session.get(User, request.form.get("user_id", type=int)) or abort(404)
            if u.id == current_user.id:
                flash("You cannot deactivate your own account.", "danger")
            else:
                u.is_active_account = not u.is_active_account
                db.session.add(AuditEvent(actor_id=current_user.id, action="user.toggle_active",
                                          target=f"user:{u.id}", details={"active": u.is_active_account}))
                db.session.commit()
                flash("Account updated.", "success")
            return redirect(url_for("staff.admin_users"))
    users = User.query.order_by(User.role, User.created_at).all()
    return render_template("staff/admin_users.html", users=users, departments=Department.query.all(),
                           errors=errors), (400 if errors else 200)


@bp.route("/admin/departments", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def admin_departments():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("name", "").strip()
            if not 2 <= len(name) <= 120 or Department.query.filter_by(name=name).first():
                flash("Enter a new, unique department name.", "danger")
            else:
                db.session.add(Department(name=name, is_simulated=True))
                db.session.add(AuditEvent(actor_id=current_user.id, action="department.add", target=name))
                db.session.commit()
                flash("Department added.", "success")
        elif action == "map":
            for cat in CATEGORIES:
                dep_id = request.form.get(f"map_{cat}", type=int)
                row = db.session.get(CategoryDepartment, cat)
                if dep_id:
                    if row:
                        row.department_id = dep_id
                    else:
                        db.session.add(CategoryDepartment(category=cat, department_id=dep_id))
                elif row:
                    db.session.delete(row)
            db.session.add(AuditEvent(actor_id=current_user.id, action="department.mapping_update"))
            db.session.commit()
            flash("Category mapping saved.", "success")
        return redirect(url_for("staff.admin_departments"))
    mapping = {m.category: m.department_id for m in CategoryDepartment.query.all()}
    return render_template("staff/admin_departments.html", departments=Department.query.all(), mapping=mapping)


@bp.route("/admin/feedback")
@roles_required(Role.ADMIN)
def admin_feedback():
    items = Feedback.query.order_by(Feedback.created_at.desc()).limit(200).all()
    return render_template("staff/admin_feedback.html", items=items)


@bp.route("/admin/audit")
@roles_required(Role.ADMIN)
def admin_audit():
    items = AuditEvent.query.order_by(AuditEvent.created_at.desc()).limit(300).all()
    return render_template("staff/admin_audit.html", items=items)
