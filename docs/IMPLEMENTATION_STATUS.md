# Implementation status

Legend: **COMPLETE** · **PARTIAL** · **BLOCKED** · **NOT STARTED**. Last updated at the end of Phase 1.

## Phase plan

| Phase | Scope | State |
|---|---|---|
| 1. Base | App factory, auth/roles, complaint workflow, review, priority, nearby lookup, map, dashboard, CSV, demo seed, tests, docs | COMPLETE |
| 2. Image AI + duplicates | PyTorch/YOLO inference backend, RDD2022/TACO preparation, training/evaluation scripts, model card; duplicate candidates, linking/unlinking, incident groups, corroboration (C) | NOT STARTED |
| 3. Traffic video | Upload, ROI + counting line, detection + tracking, directional counts, persistent job queue + worker, charts/CSV, manual-reference evaluation | NOT STARTED |
| 4. Hardening + academic docs | Text TF-IDF model (only if real labelled data exists), heatmap, CSP, browser tests, academic documentation drafts, performance measurements | NOT STARTED |

## Detailed checklist

| Requirement | State | Notes |
|---|---|---|
| Flask app factory, config from env, SQLite, Flask-Migrate | COMPLETE | `civiceye/__init__.py`, `migrations/` |
| Register / login / logout, hashed passwords, rate limits | COMPLETE | |
| Roles: citizen, reviewer, admin; secure `create-admin` command | COMPLETE | Reviewers labelled simulated |
| Public pages: home, guidance/limitations, privacy/consent, aggregate stats | COMPLETE | No public map in phase 1 |
| Complaint form: required image, extras (limit 3), description length, observation time, geolocation after permission, manual map pin, editable coordinates, landmark, category, consent | COMPLETE | Browser behaviour not tested on a real phone |
| "AI unavailable" display, no blocking on AI failure | COMPLETE | |
| Original automated output stored separately from human categories | COMPLETE | `inference_records` vs `submitted_category` / `reviewed_category` |
| Nearby existing reports before submission (no personal data) | COMPLETE | |
| Opaque complaint ID, transactional save, confirmation page, history event, staff visibility | COMPLETE | Files are removed if the DB transaction fails |
| Complaint detail with history, priority breakdown, resolution verification notice | COMPLETE | |
| Citizen category correction, clarification/evidence, reopening request | COMPLETE | |
| In-app notifications | COMPLETE | Email/SMS: NOT STARTED (disabled) |
| Feedback | COMPLETE | |
| Status transitions enforced in backend, mandatory reject reason and resolution note | COMPLETE | |
| Public vs internal notes | COMPLETE | |
| Assignment to (simulated) departments and reviewers | COMPLETE | |
| Category/risk/assignment/override changes recorded | COMPLETE | |
| Priority engine with provisional state, caps, override | COMPLETE | C is 0 until phase 2 linking |
| Reviewer dashboard: totals, category/status charts, unreviewed and high-priority queues, resolution summary | COMPLETE | |
| Filters: date, category, status, department, priority band, landmark, demo/real | COMPLETE | Location filter is landmark text only |
| Staff map with markers (shape + letter, not colour only) | COMPLETE | Heatmap NOT STARTED |
| Safe, authorised CSV export | COMPLETE | |
| Admin: reviewers, departments + category mapping, feedback, audit log | COMPLETE | |
| Demo seed / purge commands, DEMO labels in UI and CSV | COMPLETE | |
| Upload validation, EXIF removal, random names, authorised media route, path-traversal guard | COMPLETE | |
| Image AI module interface | PARTIAL | Interface + honest unavailable backend only |
| Pothole/litter trained model, dataset prep, training, evaluation, model card | NOT STARTED | Phase 2 |
| Text TF-IDF + logistic regression | NOT STARTED | Needs a genuine labelled dataset; keyword baseline used |
| Duplicate candidates with image/text similarity, linking, unlinking, incident groups, test pairs | PARTIAL | Haversine nearby lookup only |
| Traffic-video module and worker | NOT STARTED | Phase 3 |
| Automated tests | PARTIAL | 57 tests for phase 1 scope; no browser tests |
| README, architecture + ER diagram, routes, privacy notes, test report | COMPLETE | For phase 1 |
| Model card, dataset notes | NOT STARTED | Phase 2 |
| Academic documentation drafts | NOT STARTED | Phase 4 |
| MANUAL_WORK.md | COMPLETE | |
