import io
import os

from PIL import Image

from civiceye.models import Attachment, Complaint, InferenceRecord, Notification, StatusEvent

from .conftest import image_bytes, login, submit


def test_submit_without_ai_weights(client, citizen, app):
    login(client, citizen.email)
    r = submit(client)
    assert r.status_code == 302, r.data
    c = Complaint.query.one()
    assert c.public_id.startswith("CE-") and len(c.public_id) == 15
    assert c.status == "submitted"
    assert c.submitted_category == "pothole" and c.reviewed_category is None
    img = InferenceRecord.query.filter_by(kind="image").one()
    assert img.status == "unavailable" and img.method == "unavailable"
    assert img.output_json["detections"] == []  # no fabricated predictions
    txt = InferenceRecord.query.filter_by(kind="text").one()
    assert txt.method == "rule_based_keywords" and txt.output_json["category"] == "pothole"
    assert StatusEvent.query.filter_by(complaint_id=c.id, to_status="submitted").count() == 1
    assert Notification.query.filter_by(user_id=citizen.id).count() == 1
    assert os.path.isfile(os.path.join(app.config["UPLOAD_DIR"], c.attachments[0].stored_name))
    page = client.get(f"/me/complaints/{c.public_id}/submitted")
    assert c.public_id.encode() in page.data


def test_citizen_choice_kept_separate_from_suggestion(client, citizen):
    login(client, citizen.email)
    submit(client, description="Garbage dumped and litter everywhere near wall", category="other")
    c = Complaint.query.one()
    assert c.submitted_category == "other"
    assert InferenceRecord.query.filter_by(kind="text").one().output_json["category"] == "garbage"


def test_exif_removed(client, citizen, app):
    login(client, citizen.email)
    submit(client, image=(image_bytes(exif_gps=True), "gps.jpg"))
    a = Attachment.query.one()
    with Image.open(os.path.join(app.config["UPLOAD_DIR"], a.stored_name)) as im:
        assert len(im.getexif()) == 0


def test_random_storage_name(client, citizen):
    login(client, citizen.email)
    submit(client, image=(image_bytes(), "../../etc/passwd.jpg"))
    a = Attachment.query.one()
    assert "passwd" not in a.stored_name and "/" not in a.stored_name and ".." not in a.stored_name


def test_invalid_uploads_rejected(client, citizen, app):
    login(client, citizen.email)
    r = submit(client, image=(io.BytesIO(b"<?php echo 1; ?>"), "shell.jpg"))
    assert r.status_code == 400
    r = submit(client, image=(image_bytes(size=(20, 20)), "tiny.jpg"))
    assert r.status_code == 400
    gif = io.BytesIO()
    Image.new("RGB", (100, 100)).save(gif, format="GIF")
    gif.seek(0)
    r = submit(client, image=(gif, "x.gif"))
    assert r.status_code == 400
    assert Complaint.query.count() == 0
    assert os.listdir(app.config["UPLOAD_DIR"]) == []  # nothing left behind


def test_missing_image_and_fields(client, citizen):
    login(client, citizen.email)
    data = {"description": "short", "category": "nope", "latitude": "999", "longitude": "x", "observed_at": ""}
    r = client.post("/me/complaints/new", data=data, content_type="multipart/form-data")
    assert r.status_code == 400
    for msg in (b"photo of the issue is required", b"Description must be", b"Choose a category",
                b"Set the location", b"consent"):
        assert msg in r.data
    assert Complaint.query.count() == 0


def test_too_many_extra_images(client, citizen, app):
    login(client, citizen.email)
    extras = [(image_bytes(), f"e{i}.jpg") for i in range(app.config["MAX_EXTRA_IMAGES"] + 1)]
    r = submit(client, extra_images=extras)
    assert r.status_code == 400


def test_future_observation_rejected(client, citizen):
    login(client, citizen.email)
    r = submit(client, observed_at="2099-01-01T10:00")
    assert r.status_code == 400


def test_citizen_category_correction_before_review(client, citizen, reviewer):
    login(client, citizen.email)
    submit(client)
    c = Complaint.query.one()
    client.post(f"/me/complaints/{c.public_id}/category", data={"category": "garbage"})
    assert Complaint.query.one().submitted_category == "garbage"
    ev = StatusEvent.query.filter_by(event_type="category").one()
    assert ev.details == {"from": "pothole", "to": "garbage", "by": "citizen"}


def test_clarification(client, citizen):
    login(client, citizen.email)
    submit(client)
    c = Complaint.query.one()
    client.post(f"/me/complaints/{c.public_id}/clarify",
                data={"note": "It is next to the tea shop", "image": (image_bytes(), "more.jpg")},
                content_type="multipart/form-data")
    assert Attachment.query.filter_by(kind="clarification").count() == 1
    assert StatusEvent.query.filter_by(event_type="clarification").count() == 1


def test_nearby_api_hides_personal_data(client, citizen, citizen2):
    login(client, citizen.email)
    submit(client)
    client.post("/logout")
    login(client, citizen2.email)
    r = client.get("/api/nearby?lat=12.90812&lon=77.56652&category=pothole")
    data = r.get_json()
    assert len(data["results"]) == 1
    res = data["results"][0]
    assert set(res) == {"distance_m", "category", "status", "same_category"}
    far = client.get("/api/nearby?lat=12.9200&lon=77.5665").get_json()
    assert far["results"] == []


def test_suggest_api_labels_rule_based(client, citizen):
    login(client, citizen.email)
    r = client.post("/api/suggest-category", json={"text": "street light not working, dark street"})
    j = r.get_json()
    assert j["category"] == "streetlight" and j["method"] == "rule_based_keywords"
    assert "not a probability" in j["disclaimer"]
