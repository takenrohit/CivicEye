"""Authorised evidence serving. Raw upload paths are never exposed."""
from flask import Blueprint, abort, current_app, send_file
from flask_login import current_user, login_required

from ..auth_utils import can_view_complaint
from ..models import Attachment
from ..services.storage import UploadError, safe_path

bp = Blueprint("media", __name__)


@bp.route("/media/<public_id>")
@login_required
def attachment(public_id):
    att = Attachment.query.filter_by(public_id=public_id).first()
    if att is None or not can_view_complaint(current_user, att.complaint):
        abort(404)
    try:
        path = safe_path(current_app.config["UPLOAD_DIR"], att.stored_name)
    except UploadError:
        abort(404)
    if not path.is_file():
        abort(404)
    resp = send_file(path, mimetype=att.mime_type, as_attachment=False, max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp
