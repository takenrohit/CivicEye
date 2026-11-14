"""Management commands: `flask --app wsgi <command>`."""
from __future__ import annotations

import io
import random
import secrets
from datetime import timedelta

import click
from PIL import Image, ImageDraw

from .blueprints.auth import EMAIL_RE, validate_password
from .categories import CATEGORIES
from .extensions import db
from .models import (Assignment, Attachment, AuditEvent, CategoryDepartment, Complaint, Department, Feedback,
                     Notification,
                     ReopenRequest, Role, StatusEvent, User, utcnow)

DEFAULT_DEPARTMENTS = {
    "pothole": "Roads & Infrastructure (simulated)",
    "garbage": "Solid Waste Management (simulated)",
    "waterlogging": "Storm Water Drains (simulated)",
    "streetlight": "Electrical / Streetlights (simulated)",
    "other": "General Civic Desk (simulated)",
}


def ensure_departments() -> None:
    for cat, name in DEFAULT_DEPARTMENTS.items():
        dep = Department.query.filter_by(name=name).first()
        if dep is None:
            dep = Department(name=name, is_simulated=True)
            db.session.add(dep)
            db.session.flush()
        if db.session.get(CategoryDepartment, cat) is None:
            db.session.add(CategoryDepartment(category=cat, department_id=dep.id))
    db.session.commit()


def _create_staff(email, name, role, password):
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise click.ClickException("Invalid email.")
    if User.query.filter_by(email=email).first():
        raise click.ClickException("A user with that email already exists.")
    if (msg := validate_password(password)):
        raise click.ClickException(msg)
    u = User(email=email, display_name=name, role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    db.session.add(AuditEvent(actor_id=None, action=f"cli.create_{role}", target=f"user:{u.id}"))
    db.session.commit()
    return u


def register(app):
    @app.cli.command("init-departments")
    def init_departments():
        """Create the default SIMULATED departments and category mapping (idempotent)."""
        ensure_departments()
        click.echo("Simulated departments ready.")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Display name", default="Administrator")
    @click.password_option(prompt="Password (min 10 chars)")
    def create_admin(email, name, password):
        """Create an administrator. Password is prompted (hidden), never a default."""
        u = _create_staff(email, name, Role.ADMIN, password)
        click.echo(f"Administrator {u.email} created.")

    @app.cli.command("create-reviewer")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt="Display name", default="Reviewer")
    @click.password_option(prompt="Password (min 10 chars)")
    def create_reviewer(email, name, password):
        """Create a reviewer (simulated project role unless officially authorised)."""
        u = _create_staff(email, name, Role.REVIEWER, password)
        click.echo(f"Reviewer {u.email} created.")

    @app.cli.command("seed-demo")
    @click.option("--count", default=24, show_default=True, type=click.IntRange(1, 500))
    @click.option("--seed", default=2026, show_default=True, help="Random seed for reproducible demo data.")
    @click.option("--yes", is_flag=True, help="Skip confirmation.")
    def seed_demo(count, seed, yes):
        """Add clearly labelled SYNTHETIC demo users and complaints. Never deletes real data."""
        if not yes:
            click.confirm(f"Add {count} synthetic DEMO complaints (labelled DEMO everywhere)?", abort=True)
        ensure_departments()
        rng = random.Random(seed)
        creds = []

        def demo_user(email, name, role):
            """Create or re-enable a demo account. A fresh random password is generated on
            every run, so lost demo passwords are recovered by re-running seed-demo."""
            u = User.query.filter_by(email=email).first()
            if u is not None and not u.is_demo:
                raise click.ClickException(f"{email} exists and is not a demo account; refusing to touch it.")
            if u is None:
                u = User(email=email, display_name=name, role=role, is_demo=True)
                db.session.add(u)
            u.is_active_account = True
            pw = secrets.token_urlsafe(12)
            u.set_password(pw)
            creds.append((email, role, pw))
            return u

        users = [demo_user(f"demo.citizen{i}@demo.civiceye.invalid", f"Demo Citizen {i}", Role.CITIZEN)
                 for i in range(1, 4)]
        reviewer = demo_user("demo.reviewer@demo.civiceye.invalid", "Demo Reviewer (simulated officer)",
                             Role.REVIEWER)
        db.session.flush()

        center_lat, center_lon = app.config["MAP_DEFAULT_CENTER"]
        cfg = app.config
        texts = {
            "pothole": ["DEMO: Large pothole near the bus stop, two-wheelers swerving.",
                        "DEMO: Broken road surface with cracks after rain."],
            "garbage": ["DEMO: Garbage dumped beside the compound wall, plastic spreading.",
                        "DEMO: Litter pile near the corner, bad smell."],
            "waterlogging": ["DEMO: Stagnant water on the road after rain, drain clogged."],
            "streetlight": ["DEMO: Street light not working for a week, dark street at night."],
            "other": ["DEMO: Fallen signboard partly blocking the footpath."],
        }
        cats = list(CATEGORIES)
        mapping = {m.category: m.department_id for m in CategoryDepartment.query.all()}
        for n in range(count):
            cat = rng.choices(cats, weights=[4, 4, 2, 2, 1])[0]
            created = utcnow() - timedelta(days=rng.uniform(0, 40), hours=rng.uniform(0, 23))
            c = Complaint(reporter=rng.choice(users), description=rng.choice(texts[cat]),
                          landmark="DEMO landmark", observed_at=created - timedelta(hours=rng.uniform(1, 12)),
                          latitude=center_lat + rng.uniform(-0.004, 0.004),
                          longitude=center_lon + rng.uniform(-0.004, 0.004),
                          location_source="manual", submitted_category=cat, consent_given_at=created,
                          is_demo=True, created_at=created)
            db.session.add(c)
            db.session.flush()
            stored = _demo_image(cfg["UPLOAD_DIR"], cat, n)
            db.session.add(Attachment(complaint_id=c.id, uploaded_by_id=c.reporter.id, kind="evidence",
                                      stored_name=stored, mime_type="image/png", width=480, height=320,
                                      created_at=created))
            db.session.add(StatusEvent(complaint_id=c.id, actor_id=c.reporter.id, from_status=None,
                                       to_status="submitted", public_note="Complaint submitted (DEMO).",
                                       created_at=created))
            # Walk some complaints through the workflow (simulated reviewer actions).
            path = rng.choice([[], ["under_review"], ["under_review", "assigned"],
                               ["under_review", "assigned", "in_progress"],
                               ["under_review", "assigned", "in_progress", "resolved"]])
            t = created
            prev = "submitted"
            for st in path:
                t = t + timedelta(hours=rng.uniform(2, 48))
                if t > utcnow():
                    break
                if st == "under_review":
                    c.reviewed_category = cat
                    c.reviewed_risk = rng.randint(1, 5)
                    c.location_sensitivity = rng.choice([0, 0, 1])
                    c.location_rationale = "DEMO rationale" if c.location_sensitivity else None
                if st == "assigned":
                    c.department_id = mapping.get(cat)
                note = None
                if st == "resolved":
                    note = "DEMO: simulated resolution. No actual repair occurred."
                    c.resolution_note = note
                    c.resolved_at = t
                db.session.add(StatusEvent(complaint_id=c.id, actor_id=reviewer.id, from_status=prev, to_status=st,
                                           public_note=note, created_at=t))
                c.status = prev = st
        db.session.add(AuditEvent(action="cli.seed_demo", details={"count": count, "seed": seed}))
        db.session.commit()
        click.echo(f"Added {count} DEMO complaints.")
        click.echo("Demo credentials, regenerated on every run (local demo only; never reuse in a deployment):")
        for e, role, p in creds:
            click.echo(f"  {role:<9} {e}  {p}")

    @app.cli.command("purge-demo")
    @click.option("--yes", is_flag=True)
    def purge_demo(yes):
        """Delete ONLY records flagged is_demo (and their files). Real data is untouched."""
        if not yes:
            click.confirm("Delete all DEMO complaints and DEMO users?", abort=True)
        import os
        from .services.storage import safe_path
        demo_complaints = Complaint.query.filter_by(is_demo=True).all()
        for c in demo_complaints:
            for a in c.attachments:
                try:
                    os.remove(safe_path(app.config["UPLOAD_DIR"], a.stored_name))
                except OSError:
                    pass
            Notification.query.filter_by(complaint_id=c.id).delete()
            Assignment.query.filter_by(complaint_id=c.id).delete()
            ReopenRequest.query.filter_by(complaint_id=c.id).delete()
            db.session.delete(c)
        db.session.flush()
        deleted = kept = 0
        for u in User.query.filter_by(is_demo=True).all():
            Notification.query.filter_by(user_id=u.id).delete()
            Feedback.query.filter_by(user_id=u.id).delete()
            # Audit events and actions on real complaints must not be rewritten, so a demo
            # account that appears in them is deactivated instead of deleted.
            referenced = any(q.first() is not None for q in (
                Complaint.query.filter((Complaint.reporter_id == u.id) | (Complaint.assigned_to_id == u.id)),
                StatusEvent.query.filter_by(actor_id=u.id),
                Assignment.query.filter((Assignment.assignee_id == u.id) | (Assignment.assigned_by_id == u.id)),
                Attachment.query.filter_by(uploaded_by_id=u.id),
                ReopenRequest.query.filter((ReopenRequest.requested_by_id == u.id) |
                                           (ReopenRequest.decided_by_id == u.id)),
                AuditEvent.query.filter_by(actor_id=u.id),
            ))
            if referenced:
                u.is_active_account = False
                kept += 1
            else:
                db.session.delete(u)
                deleted += 1
        db.session.add(AuditEvent(action="cli.purge_demo", details={"complaints": len(demo_complaints),
                                                                    "users_deleted": deleted,
                                                                    "users_deactivated": kept}))
        db.session.commit()
        click.echo(f"Removed {len(demo_complaints)} demo complaints; deleted {deleted} demo users, "
                   f"deactivated {kept} that appear in the audit log (re-enabled by seed-demo).")


def _demo_image(upload_dir, cat, n) -> str:
    """Synthetic placeholder image clearly marked as demo (not a real photo)."""
    import os
    colors = {"pothole": (90, 90, 90), "garbage": (110, 80, 40), "waterlogging": (40, 90, 150),
              "streetlight": (30, 30, 60), "other": (80, 110, 80)}
    img = Image.new("RGB", (480, 320), colors.get(cat, (100, 100, 100)))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 470, 310], outline=(255, 255, 255), width=3)
    d.text((24, 24), "SYNTHETIC DEMO IMAGE", fill=(255, 255, 0))
    d.text((24, 50), f"Category: {CATEGORIES[cat]}", fill=(255, 255, 255))
    d.text((24, 76), f"Not a real photograph  #{n}", fill=(255, 255, 255))
    os.makedirs(upload_dir, exist_ok=True)
    name = secrets.token_hex(16) + ".png"
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    with open(os.path.join(upload_dir, name), "xb") as fh:
        fh.write(buf.getvalue())
    return name
