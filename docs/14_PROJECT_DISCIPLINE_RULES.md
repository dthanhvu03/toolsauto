# Project Discipline & Engineering Rules

This file defines strict architectural discipline.
AI Agent must follow these rules.

---

# I. Separation of Concerns (MANDATORY)

1. FastAPI routers:
   - Only handle HTTP + validation
   - No business logic

2. Service layer:
   - Contains business logic
   - Controls state transitions
   - Controls DB updates

3. Worker:
   - Calls service layer
   - No direct DB manipulation

4. Adapter:
   - Only platform interaction
   - No DB writes directly

---

# II. No Hidden Side Effects

- Functions must not silently modify unrelated state.
- All DB writes must be explicit.
- No global mutable state.

---

# III. No Hardcoded Magic Numbers

- Cooldown
- Retry delays
- Limits
  All must be configurable.

---

# IV. Logging Discipline

- Every job state change logged.
- Every adapter error logged.
- No print() in production.
- Use structured logging.

---

# V. Selector Discipline (Critical for FB)

1. No XPath unless last resort.
2. No nth-child selectors.
3. Prefer:
   - get_by_role
   - get_by_label
   - get_by_text
   - aria-label
4. All selectors defined in one mapping file:
   adapters/facebook/selectors.py

Never scatter selectors across code.

---

# VI. Error Handling Rules

- Adapter must not crash worker.
- Worker must catch adapter errors.
- Retry logic centralized.

---

# VII. Deterministic Behavior

- Same input job should produce same internal workflow.
- No randomness except caption generation (controlled).

---

# VIII. No Circular Dependencies

Structure must remain:

routers → services → models
worker → services → adapters
adapters → browser_manager

Never reverse direction.

---

# IX. Refactor Discipline

When changing:

- State machine
- DB schema
- Adapter contract

Must update:

- Docs
- Migration
- Tests

---

# X. Code Quality Baseline

- Type hints required
- No 200+ line functions
- No business logic inside template
- Each adapter step separated into methods

---

# XI. Definition of Clean Build

System is considered stable when:

- Worker runs 24h without memory leak
- No orphan RUNNING jobs
- Logs readable
- UI responsive
- Restart safe

---

# XII. Import Scope Discipline

To prevent Python `UnboundLocalError`:

- NEVER place `import X` inside an `if` block or loop inside a function if `X` is used anywhere else in that same function.
- Python treats any `import` (or assignment) inside a function as making that variable **local** to the entire function scope.
- **Rule of thumb**: Place all function-level dynamic imports at the very **top** of the function, before any logic.

---

# Final Rule

If unsure:
Prefer simplicity over cleverness.
Prefer explicit over implicit.
Prefer maintainable over fast hack.
