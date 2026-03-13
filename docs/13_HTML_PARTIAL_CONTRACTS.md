# HTMX Partial Contract Rules

## Purpose
Define strict UI fragment response structure to avoid DOM chaos.

---

## DOM ID Conventions

Each job row must have:

<tr id="job-{{ job.id }}">

This allows row-level update:

hx-target="#job-{{job.id}}"
hx-swap="outerHTML"

---

## Endpoint Contracts

### GET /jobs/table
Return full table fragment:
- Includes header + all rows
- Wrapped in <tbody id="jobs-table-body">

Used for:
hx-get every 10s polling

---

### GET /jobs/{id}/row
Return single row fragment:
<tr id="job-{{job.id}}">...</tr>

Used for:
- After retry
- After reschedule
- After edit caption

---

### POST /jobs/{id}/retry
Returns updated row fragment only.

---

### POST /jobs/{id}/reschedule
Returns updated row fragment only.

---

## DO NOT:

- Return JSON to HTMX endpoints expecting HTML
- Mix API JSON and HTML in same route
- Modify DOM structure from frontend JS randomly

---

## HTMX Polling Rule

Polling must refresh only necessary section:

<div hx-get="/jobs/table"
     hx-trigger="every 10s"
     hx-target="#jobs-table-body"
     hx-swap="outerHTML">
</div>

---

## Acceptance Criteria

- No full page reload for job operations
- Row updates do not break table layout
- DOM IDs predictable and stable