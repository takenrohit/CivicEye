# Test execution report (Phase 1)

Environment: Windows 11 Home, Python 3.11.9, packages as pinned in `requirements.txt` + pytest 9.2.0.

## Automated tests

Command: `.\.venv\Scripts\python -m pytest -q`

Result: **57 passed**, 0 failed (about 20 s).

| File | Covers |
|---|---|
| `tests/test_auth.py` | registration, validation, duplicate email, login/logout, generic login error, deactivated account, open-redirect guard, CSRF enforcement, missing secret key |
| `tests/test_access.py` | anonymous access blocked, other citizen gets 404 for complaint/media/actions, owner access, citizen cannot change status, reviewer vs admin pages, reviewer object-level restriction, private notifications, public pages show disclaimers |
| `tests/test_complaints.py` | submission without AI weights (honest unavailable record, no fake detections), separate citizen choice vs suggestion, EXIF removal, random filenames, invalid/tiny/GIF uploads rejected with no leftover files, field validation, extra-image limit, future time, category correction, clarification, nearby API returns no personal data, suggestion API labelled rule-based |
| `tests/test_workflow.py` | full lifecycle with history, department required before Assigned, resolution note required, no direct reopen, reopening request → approval, decline needs reason, rejection reason, terminal states, internal notes hidden, reviewed category kept separate |
| `tests/test_priority.py` | weights, normalisation, unknown vs confirmed low, max score, age cap and freeze, corroboration dedup, exact formula, override clamp, override reason required, location rationale required |
| `tests/test_services.py` | haversine distances, keyword baseline, detector unavailable, path traversal, CSV formula injection, CSV export auth/safety/no identities, dashboards with empty data, reopened counted as unresolved, demo seed labels and no fake AI, purge keeps real data, `create-admin` |

Mock inference: none needed in phase 1, because the real default backend is the "unavailable" detector.

## Manual smoke test against the running server

`flask --app wsgi run` with migrated DB and `seed-demo` data, driven by a Python HTTP client:

- `/`, `/guidance`, `/privacy`, `/login`, `/register` returned 200.
- Login POST without CSRF token returned 400. With token: 302 to the reviewer dashboard.
- `/staff/`, `/staff/complaints`, `/staff/map`, `/staff/reopen-requests`, `/staff/complaints/export.csv`, review page, and a `/media/...` image returned 200 for the demo reviewer; `/staff/admin/users` returned 403.
- CDN Subresource Integrity hashes for Bootstrap 5.3.3, Leaflet 1.9.4 and Chart.js 4.4.1 were verified by downloading the files.
- `node --check` passed for all four JS files.

## Not run

- No real browser or phone test (map clicks, geolocation permission, image preview, Chart.js rendering, keyboard navigation, screen readers). Do this manually before the presentation: `flask --app wsgi run`, then open http://127.0.0.1:5000.
- No performance measurement.
- No AI model inference, training or evaluation (no weights installed).
