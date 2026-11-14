# Privacy and security notes (Phase 1)

## Controls implemented

| Area | Implementation |
|---|---|
| Passwords | Werkzeug `generate_password_hash` (scrypt); min 10 chars; never logged |
| Sessions | Flask-Login, `session_protection="strong"`, HttpOnly + SameSite=Lax cookies; `CIVICEYE_SECURE_COOKIES=1` for HTTPS |
| CSRF | Flask-WTF `CSRFProtect` on every POST, including logout and JSON API (header `X-CSRFToken`) |
| Rate limits | Flask-Limiter: login 10/min, register 5/min, complaint submit 10/hour, API 60/min (in-memory store; use Redis for multi-process) |
| Secrets | `CIVICEYE_SECRET_KEY` from environment; app refuses to start without it; `.env` is git-ignored |
| Access control | Role decorator on every protected route; citizens get 404 for others' complaints; reviewer object-level check |
| IDs | Complaint IDs `CE-` + 12 random chars; attachment IDs 128-bit random |
| Uploads | Decoded with Pillow; only JPEG/PNG/WebP; size, pixel-count and dimension limits; re-encoded (drops EXIF incl. GPS and trailing payloads); random filenames; stored outside `static/`; served only via an authorised route with `Cache-Control: no-store`; path-traversal guard |
| Output | Jinja autoescaping; JS builds DOM with `textContent`; JSON passed through `tojson` |
| CSV | Cells starting with `= + - @ TAB CR` are prefixed with `'`; reporter identities excluded; coordinates rounded to 4 dp; each export audited |
| Headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` (other sites see only the origin, never paths containing complaint IDs; OSM tile servers reject requests without a Referer), `Permissions-Policy` |
| Redirects | `next` parameter restricted to local paths |
| Third-party scripts | CDN assets pinned with SRI hashes (verified) |

## Data minimisation

- Collected: email, display name, complaint photos, description, observation time, location, optional landmark.
- Not collected: Aadhaar, government ID, phone number, home address.
- EXIF GPS is never read. Browser geolocation is requested only after the user presses the button.
- Public pages show only aggregate counts. No public map in phase 1, and no photos are ever public (there is no redaction, so images are not released).
- The nearby-report API returns distance, category and status only.
- No face recognition or number-plate recognition.

## Retention (draft pilot policy, needs guide approval)

Keep pilot data for the project period (2026–27), then delete or anonymise. Delete an account and its complaints on request. `flask purge-demo` removes only demo-flagged records.

## Backup and restore (SQLite)

```powershell
# backup (stop the app first, or use sqlite3 .backup for a live copy)
Copy-Item instance\civiceye.db backups\civiceye-$(Get-Date -Format yyyyMMdd-HHmm).db
Compress-Archive instance\uploads backups\uploads-$(Get-Date -Format yyyyMMdd-HHmm).zip
# restore
Copy-Item backups\civiceye-<stamp>.db instance\civiceye.db
Expand-Archive backups\uploads-<stamp>.zip instance\ -Force
.\.venv\Scripts\flask --app wsgi db upgrade
```

Back up before every migration. Backups contain personal data, so store them with the same access restrictions.

## Threat notes and known gaps

- Account enumeration through the registration "email already exists" message is possible. Accepted for the pilot; revisit before public deployment.
- The in-memory rate-limit store resets on restart and is per-process.
- The development server (`flask run`) must not be used for public deployment. Use a WSGI server behind HTTPS.
- Content-Security-Policy is not yet set (CDN scripts are SRI-pinned). Planned.
- Password reset by email is not implemented (email is disabled). An admin can deactivate accounts; reset is manual.
