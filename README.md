# CivicEye
An AI-Based Traffic, Pothole and Civic Complaint Analysis System

DSCE Information Science and Engineering community project, academic year 2026–27.
Proposed pilot: a permission-approved locality around DSCE, Kumaraswamy Layout, Bengaluru (permissions not yet obtained).
Primary SDG alignment: SDG 11, Sustainable Cities and Communities.

> **Academic decision-support prototype.** Not an official government complaint portal, emergency
> service, or traffic-control system, and it does not guarantee civic repairs. Reviewer/"officer"
> accounts are simulated project roles.

## Current state: Phase 1 (base application)

Phase 1 is a working web application for the complaint workflow. See
[docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) for the full checklist.

| Feature | Kind | State |
|---|---|---|
| Accounts, roles, complaint submission, tracking, review workflow, notifications, reopening, feedback | Operational | Working |
| Category suggestion from the description | **Rule-based keyword baseline** (not AI, not evaluated) | Working |
| Priority score `P = 0.45R + 0.25L + 0.20A + 0.10C` | Rule-based, human-reviewed inputs | Working |
| Nearby-report lookup (haversine, 30 m / 30 days) | Rule-based | Working (linking not yet) |
| Image detection of potholes / litter | Trained AI | **Not installed.** The app shows "AI unavailable" |
| Duplicate linking, incident groups | — | Phase 2 |
| Traffic-video analysis | Trained AI (pretrained detector) | Phase 3 |
| Demo data | Synthetic, labelled DEMO everywhere | `seed-demo` command |

## Setup (Windows PowerShell, tested)

Requires Python 3.11 (tested with 3.11.9). Python 3.14 is not used because PyTorch support is needed in later phases.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# put a random value in .env:
.\.venv\Scripts\python -c "import secrets; print(secrets.token_hex(32))"
#   CIVICEYE_SECRET_KEY=<paste>

.\.venv\Scripts\flask --app wsgi db upgrade          # create / migrate the SQLite database
.\.venv\Scripts\flask --app wsgi init-departments    # simulated departments + category mapping
.\.venv\Scripts\flask --app wsgi create-admin        # prompts for email and hidden password
.\.venv\Scripts\flask --app wsgi seed-demo           # optional: synthetic DEMO data, prints generated demo passwords
.\.venv\Scripts\flask --app wsgi run                 # http://127.0.0.1:5000
```

On Linux/macOS use `python3.11 -m venv .venv`, `source .venv/bin/activate`, then the same `flask --app wsgi ...` commands.

Other commands:

```powershell
.\.venv\Scripts\flask --app wsgi create-reviewer     # simulated reviewer account
.\.venv\Scripts\flask --app wsgi purge-demo          # deletes ONLY records flagged as demo
.\.venv\Scripts\python -m pytest -q                  # run tests
.\.venv\Scripts\python scripts\browser_smoke.py      # real-browser checkup (server must be running; uses installed Edge)
```

Phase 1 has no background worker. The traffic-video worker arrives in phase 3.

The app loads Bootstrap, Leaflet and Chart.js from public CDNs (with Subresource Integrity hashes), and map tiles from OpenStreetMap. The presentation machine therefore needs internet access. Review the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/) before any public deployment; the tile URL and attribution are configurable in `.env`.

## Presentation demo script (about 5 minutes)

1. Open `/`: point out the disclaimers, the aggregate-only public statistics, and the separate DEMO counts.
2. Register a new citizen account. Open **Report an issue**.
3. Choose a photo. The panel shows **"AI unavailable"** for images. Type a description such as "big pothole near the bus stop": a **keyword-rule** suggestion appears, labelled as not AI. Choose the category yourself.
4. Click **Use my location** (or click the map). Note the accuracy message, the editable coordinates, and the "possible existing reports nearby" panel.
5. Tick consent and submit. Show the opaque complaint ID and the confirmation page.
6. Sign out and sign in as the admin (or the demo reviewer). Show the dashboard charts, unreviewed queue and the map.
7. Open the new complaint: original automated outputs are shown separately, nearby reports are listed, the priority is **Provisional**.
8. Confirm the category, set risk and location context (rationale required), and watch the priority breakdown change.
9. Move it Under Review → assign a department → Assigned → In Progress → Resolved (resolution note is mandatory; without a photo, the citizen sees "Resolution not independently verified").
10. Sign in as the citizen: notifications, history (internal notes hidden), and **Request reopening**. Back as reviewer, approve it in **Reopen requests**.
11. Sign in as a second citizen and paste the first complaint's URL: it returns 404.

## Project layout

```
civiceye/            Flask application package (app factory in __init__.py)
  blueprints/        public, auth, citizen, staff (reviewer/admin), media, api
  services/          workflow (status rules), priority, geo, nearby, storage, exports
  ai/                image.py (replaceable detector interface), text.py (keyword baseline)
  templates/, static/
migrations/          Alembic migrations (Flask-Migrate)
tests/               pytest suite
docs/                status checklist, architecture/ER diagram, routes, privacy notes, test report
MANUAL_WORK.md       tasks the team must do outside the software
```

## Documentation

- [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md): checklist (COMPLETE / PARTIAL / NOT STARTED)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): architecture, ER diagram, routes, priority definition, status rules
- [docs/PRIVACY_SECURITY.md](docs/PRIVACY_SECURITY.md): privacy controls, threat notes, retention, backup/restore
- [docs/TEST_REPORT.md](docs/TEST_REPORT.md): what was actually run, and the results
- [MANUAL_WORK.md](MANUAL_WORK.md): approvals, community work, data, models and academic tasks for the team

## Troubleshooting

- `RuntimeError: CIVICEYE_SECRET_KEY is not set`: create `.env` from `.env.example` and set the key.
- `Python was not found`: use `py -3.11` (Windows launcher) or install Python 3.11.
- Map is grey: no internet access, or the tile provider is blocked. Coordinates can still be typed.
- Map tiles say "Access blocked": OpenStreetMap rejects tile requests that carry no `Referer`. The app sends `Referrer-Policy: strict-origin-when-cross-origin` for this reason; do not change it to `no-referrer` or `same-origin`. Browser extensions that strip referrers cause the same problem. Hard-refresh (Ctrl+F5) after fixing.
- "Use my location" does nothing: browsers allow geolocation only on `localhost`/HTTPS and after permission. Click the map instead.
- `400 Bad request` after leaving a form open for hours: the CSRF token expired (4 h). Reload the page.
- Map still blocked after a fix or after uploading: the browser cached the blocked tiles. Clear cached images (Edge/Chrome: Ctrl+Shift+Delete, "Cached images and files") or open a private window.
- Lost the demo passwords: run `seed-demo --count 1` again; it prints new passwords for all demo accounts.
- A phone photo is rejected: the limit is 20 MB per photo (`CIVICEYE_MAX_IMAGE_MB`). Stored copies are downscaled to 2560 px.
- `429 Too many requests`: login (10/min), registration (5/min) and submission (10 accepted complaints and 30 attempts per hour) are rate-limited.
