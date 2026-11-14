"""Role and object-level access helpers. Every protected route uses these server-side."""
from functools import wraps

from flask import abort
from flask_login import current_user, login_required

from .models import Complaint


def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def get_complaint_for_citizen_or_404(public_id: str) -> Complaint:
    """Owner-only access. Returns 404 (not 403) so IDs cannot be probed."""
    c = Complaint.query.filter_by(public_id=public_id).first()
    if c is None or c.reporter_id != current_user.id:
        abort(404)
    return c


def can_view_complaint(user, complaint: Complaint) -> bool:
    return user.is_authenticated and (user.is_staff or complaint.reporter_id == user.id)
