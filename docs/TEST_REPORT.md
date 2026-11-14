# Test execution report (Phase 1)

Environment: Windows 11 Home, Python 3.11.9, packages as pinned in `requirements.txt` + `requirements-dev.txt` (pytest 9.2.0, Playwright 1.65.2), Microsoft Edge (installed system browser).

## Automated unit/integration tests

Command: `.\.venv\Scripts\python -m pytest -q`

Result: **73 passed**, 0 failed (about 30 s).

| File | Covers |
|---|---|
| `tests/test_auth.py` | registration, validation, duplicate email, login/logout, generic login error, deactivated account, open-redirect guard, CSRF enforcement, missing secret key |
| `tests/test_access.py` | anonymous access blocked, other citizen gets 404 for complaint/media/actions, owner access, citizen cannot change status, reviewer vs admin pages, reviewer object-level restriction, private notifications, Referrer-Policy for map tiles, public pages show disclaimers |
| `tests/test_complaints.py` | submission without AI weights (honest unavailable record, no fake detections), separate citizen choice vs suggestion, EXIF removal, random filenames, invalid/tiny/GIF uploads rejected with no leftover files, field validation, extra-image limit, future time, category correction, clarification, nearby API returns no personal data, suggestion API labelled rule-based |
| `tests/test_workflow.py` | full lifecycle with history, department required before Assigned, resolution note required, no direct reopen, reopening request → approval, decline needs reason, rejection reason, terminal states, internal notes hidden, reviewed category kept separate |
| `tests/test_priority.py` | weights, normalisation, unknown vs confirmed low, max score, age cap and freeze, corroboration dedup, exact formula, override clamp, override reason required, location rationale required |
| `tests/test_services.py` | haversine distances, keyword baseline, detector unavailable, path traversal, CSV formula injection, CSV export auth/safety/no identities, dashboards with empty data, reopened counted as unresolved, demo seed labels and no fake AI, purge keeps real data, `create-admin` |
| `tests/test_limits.py` | 108 MP phone photo accepted and downscaled, EXIF orientation applied, oversized PNG rejected, failed validation does not use the submission quota, attempt limit, login rate limit |
| `tests/test_regressions.py` | bugs found in the checkup (listed below) |

Mock inference: none needed in phase 1, because the real default backend is the "unavailable" detector.

## Real-browser checkup

Command (server running, demo reviewer credentials from `seed-demo` in env vars):

```powershell
$env:CIVICEYE_REVIEWER_EMAIL="demo.reviewer@demo.civiceye.invalid"; $env:CIVICEYE_REVIEWER_PASSWORD="<from seed-demo>"
.\.venv\Scripts\python scripts\browser_smoke.py        # add --headed to watch it
```

Result: **36/36 checks passed** in headless Microsoft Edge (Playwright, browser time zone deliberately set to Europe/London). Checks include: public pages; registration; map tiles requested with a Referer and none blocked (on the form, after a failed submission, staff map, review map); default observation time in IST; geolocation with granted permission; manual map click; image preview; keyword suggestion and "Use this"; nearby panel; failed submission keeps coordinates, pin, nearby panel and suggestion and asks to re-select photos; oversized photo blocked before upload; valid submission with a 4000×3000 extra photo; evidence images load; sign out; second citizen gets 404; reviewer dashboard charts; review page "AI unavailable"; status change; no JavaScript errors; no unexpected 4xx/5xx. Screenshots are written to `instance/browser_smoke/`.

## Bugs found and fixed in the checkup

| Bug | Effect | Fix |
|---|---|---|
| `Referrer-Policy: same-origin` | OpenStreetMap served "Access blocked" tiles | `strict-origin-when-cross-origin` |
| Blocked tiles cached by the browser | Map still blocked on ordinary loads (e.g. after a failed upload) until a hard refresh | Fixed by the header; clear cached images once (see README) |
| `nearbyTimer` used before declaration | JS error after a failed submission: pin, nearby check and suggestion not restored | Declare timers first; restore pin with its original location source and re-run the suggestion |
| Observation time defaulted to the browser's time zone | Wrong time (or "future time" error) on devices not set to IST | Compute the default in Asia/Kolkata; set `max` |
| 8 MB / 10,000 px limits | Typical phone photos (9–20 MB, up to 108 MP) rejected | 20 MB per photo, JPEG decoded at reduced scale, stored copy downscaled to 2560 px |
| Oversized uploads | Browser showed a connection error | Client-side size/count check with a clear message (server still validates) |
| Submission rate limit counted failed attempts | 10 validation errors locked a user out for an hour | Count only accepted complaints (10/h); separate 30/h attempt cap |
| `purge-demo` after a demo login | Crashed with `FOREIGN KEY constraint failed` | Demo users referenced in audit/history are deactivated, others deleted |
| `seed-demo` re-run | Did not print passwords for existing demo users | Regenerates and prints demo passwords on every run; refuses to touch non-demo accounts |
| Nearby lookup mixed demo and real data, and listed rejected reports to citizens | Misleading "existing reports" | Filter by the same data set; exclude rejected for citizens |
| Priority-band filter applied after the 500-row limit | Matching complaints silently missing; CSV ignored the band filter | Filter before limiting; CSV uses the same filters; page shows the true total |
| Clarification photo limit counted the original photos | Citizens who uploaded 4 photos could add only 1 more | Separate limit of 3 clarification photos |
| Closed complaints could be reassigned | Assignment events on resolved/rejected reports | Blocked with a message |
| Dashboard chart labels were raw keys | "under review", "pothole" | Human-readable labels |
| Median resolution time | Upper median for even sample sizes | `statistics.median` |
| 500 error page | Could fail on a broken DB session | Roll back before rendering |

## Not run

- Real phone testing (camera upload, mobile geolocation accuracy, small screens). The browser checkup uses desktop Edge with simulated geolocation.
- Keyboard-only and screen-reader walkthroughs.
- Performance measurements.
- AI model inference, training or evaluation (no weights installed).
