Now extend views.py with the three new list/create views:Now wire the new URLs:Now update `main.jsx` to route between Dashboard and ReviewApp, and update `index.html`:All checks pass. Here's the complete picture of what was built:

---

**Backend — 3 files updated**

`serializers.py` gained 6 new classes: `JobListSerializer`, `JobCreateSerializer`, `CandidateListSerializer`, `CandidateCreateSerializer` (with PDF validation + ResumeParser wiring), `ApplicationListSerializer` (denormalized table row with `final_score` + `is_evaluated_via_fallback`), and `ApplicationCreateSerializer` (idempotent `get_or_create`).

`views.py` gained `JobListCreateView`, `CandidateListCreateView`, `ApplicationListCreateView` — all supporting GET list + POST create with the right status codes (201 on create, 200 on idempotent re-associate).

`urls.py` wired `/api/jobs/`, `/api/candidates/`, `/api/applications/` above the existing per-application routes.

---

**Frontend — 13 files**

| File | Purpose |
|---|---|
| `api/client.js` | 9 typed exports covering all endpoints, uniform error shape |
| `hooks/useApplications.js` | List state + checkbox selection + concurrent `runSelected()` + 3s polling loop |
| `hooks/useJobs.js` / `useCandidates.js` | Lightweight list + append helpers |
| `components/Dashboard.jsx` | Root view — owns modal open state, wires all hooks |
| `components/ApplicationTable.jsx` | Checkbox table with indeterminate select-all, processing overlay |
| `components/StatusBadge.jsx` | Colour-coded pill for every `Application.Status` value |
| `components/BulkRunBar.jsx` | Sticky action bar, slides in when selection > 0 |
| `components/FallbackAlert.jsx` | ⚠ icon with tooltip on fallback-evaluated rows |
| `components/Modal.jsx` | Accessible base (ESC close, body scroll lock, focus on open) |
| `components/JobIngestionModal.jsx` | JSON POST form with client-side + server-side error display |
| `components/CandidateIngestionModal.jsx` | Multipart PDF upload with drag-zone + 10 MB guard |
| `components/AssociationModal.jsx` | Job + Candidate dropdowns with empty-state notice |
| `styles/dashboard.css` | Full design system — tokens, dark palette, all component styles |

**Async execution model:** `runSelected()` immediately flips all checked rows to `processing` status (optimistic), fires `POST /run/` for all IDs concurrently via `Promise.allSettled`, patches each row as its promise resolves, and runs a 3-second `setInterval` polling `GET /score/` as a safety net for future Celery migration.