from datetime import datetime, timedelta

import pytest

from civiceye.config import Config
from civiceye.models import Complaint, StatusEvent
from civiceye.services import priority as P

from .conftest import login, logout, submit

CFG = {"PRIORITY_WEIGHTS": Config.PRIORITY_WEIGHTS, "PRIORITY_AGE_CAP_DAYS": 30,
       "PRIORITY_CORROBORATION_CAP": 4, "PRIORITY_BANDS": Config.PRIORITY_BANDS}
NOW = datetime(2026, 8, 1, 12, 0)


def calc(**kw):
    base = dict(risk_level=None, location_level=None, created_at=NOW, now=NOW, config=CFG, reporter_id=1)
    base.update(kw)
    return P.compute(**base)


def test_weights_sum_to_one():
    assert sum(Config.PRIORITY_WEIGHTS.values()) == pytest.approx(1.0)


def test_normalization_ranges():
    assert [P.normalize_risk(i) for i in range(1, 6)] == [0, 0.25, 0.5, 0.75, 1]
    assert [P.normalize_location(i) for i in range(3)] == [0, 0.5, 1]
    with pytest.raises(ValueError):
        P.normalize_risk(6)
    with pytest.raises(ValueError):
        P.normalize_location(3)


def test_missing_values_are_unknown_and_provisional():
    r = calc()
    assert r.components["R"] is None and r.components["L"] is None
    assert r.provisional and set(r.missing) == {"R", "L"}
    assert r.total == 0


def test_confirmed_low_is_not_provisional():
    r = calc(risk_level=1, location_level=0)
    assert r.components["R"] == 0 and not r.provisional
    assert r.total == 0


def test_maximum_score():
    r = calc(risk_level=5, location_level=2, created_at=NOW - timedelta(days=90),
             corroborating_reporter_ids=[2, 3, 4, 5, 6, 7])
    assert r.total == pytest.approx(1.0) and r.band == "High"


def test_age_capped_and_frozen_on_resolution():
    assert calc(created_at=NOW - timedelta(days=15)).components["A"] == pytest.approx(0.5)
    assert calc(created_at=NOW - timedelta(days=300)).components["A"] == 1.0
    frozen = calc(created_at=NOW - timedelta(days=20), resolved_at=NOW - timedelta(days=17))
    assert frozen.components["A"] == pytest.approx(0.1)


def test_corroboration_dedup_and_excludes_original_reporter():
    r = calc(corroborating_reporter_ids=[1, 1, 2, 2, 2, None])
    assert r.components["C"] == pytest.approx(1 / 4)  # only user 2 counts
    r = calc(corroborating_reporter_ids=list(range(2, 50)))
    assert r.components["C"] == 1.0


def test_exact_formula():
    r = calc(risk_level=4, location_level=1, created_at=NOW - timedelta(days=6), corroborating_reporter_ids=[2])
    expected = 0.45 * 0.75 + 0.25 * 0.5 + 0.20 * 0.2 + 0.10 * 0.25
    assert r.computed == pytest.approx(expected, abs=1e-4)
    assert r.band == "Medium"


def test_override_clamped_and_flagged():
    r = calc(risk_level=1, override=0.9)
    assert r.overridden and r.total == 0.9 and r.computed == 0 and r.band == "High"
    assert calc(override=7).total == 1.0
    assert not calc(override=0.5).provisional


def test_override_route_requires_reason(client, citizen, reviewer):
    login(client, citizen.email)
    submit(client)
    logout(client)
    c = Complaint.query.one()
    login(client, reviewer.email)
    client.post(f"/staff/complaints/{c.public_id}/override", data={"value": "0.8", "reason": ""})
    assert Complaint.query.one().priority_override is None
    client.post(f"/staff/complaints/{c.public_id}/override", data={"value": "0.8", "reason": "Near school gate"})
    assert Complaint.query.one().priority_override == 0.8
    assert StatusEvent.query.filter_by(event_type="priority_override").count() == 1
    client.post(f"/staff/complaints/{c.public_id}/override", data={"clear": "1", "reason": "Reassessed"})
    assert Complaint.query.one().priority_override is None


def test_location_sensitivity_requires_rationale(client, citizen, reviewer):
    login(client, citizen.email)
    submit(client)
    logout(client)
    c = Complaint.query.one()
    login(client, reviewer.email)
    client.post(f"/staff/complaints/{c.public_id}/risk", data={"reviewed_risk": "4", "location_sensitivity": "2"})
    assert Complaint.query.one().location_sensitivity is None
    client.post(f"/staff/complaints/{c.public_id}/risk",
                data={"reviewed_risk": "4", "location_sensitivity": "2", "location_rationale": "School gate"})
    c = Complaint.query.one()
    assert c.reviewed_risk == 4 and c.location_sensitivity == 2
