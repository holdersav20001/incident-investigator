# System Invariants

These invariants MUST hold across the entire codebase at all times.
When adding or modifying any code path, verify that none of these are violated.
This file survives `/compact` — read it at the start of every session.

---

## 1. Per-Request Database Sessions

- Every HTTP request MUST get its own SQLAlchemy `Session` via FastAPI `Depends` with `yield`.
- NEVER share a single session instance across requests via `app.state`.
- Sessions must be committed/rolled-back and closed at the end of each request.
- Tests may use a single session per test function — that is fine.

## 2. All Writers of Shared State Must Be Consistent

When multiple code paths write to the same field, they must all leave the data in a consistent state:

- **`incident.status`** — only written via `record_transition()`, which validates through the state machine.
- **`incident.approval_status`** — must be updated by BOTH the pipeline approval step AND the human approval decision path. After human approve → `"approved"`. After human reject → `"rejected"`.
- **`approval_row.status`** — must be `"pending"` before a decision. After decision → `"approved"` or `"rejected"`.

When adding a new code path that modifies a shared field, grep for all other writers of that field and ensure they stay in sync.

## 3. Approval Decisions Require Pending State

- `record_approval_decision()` must verify the approval row is in `"pending"` status before accepting a decision.
- `record_approval_decision()` must read the incident's actual current status from the DB — never assume `from_status`.
- A second approve/reject on the same incident must return a clear 409 Conflict, not a 500.

## 4. API Boundary Validation

- Every query parameter or path parameter that maps to an enum MUST have explicit validation with a 422 response on invalid values.
- Every user-facing input must have at least one negative test (invalid value, missing value, boundary value).
- Unhandled exceptions at the API layer must never leak stack traces — the global error envelope catches `HTTPException` and `RequestValidationError`, but raw `ValueError`/`KeyError`/etc. need explicit handling in route functions.

## 5. Contract Consistency

- If `contracts.md` defines a field on a request model, the backend must either use it or not require it.
- If a request field is accepted but ignored (e.g. client-supplied timestamp overridden by server time), either:
  - Remove it from the request model, OR
  - Document clearly that it is advisory/ignored, OR
  - Actually use it

## 6. State Machine Is the Single Source of Truth

- `IncidentStatus` transitions are ONLY valid through the `transition()` function.
- No code may set `row.status` directly without calling `transition()` first.
- The `record_transition()` repository method enforces this — always use it.

## 7. Tests Must Cover Cross-Cutting Flows

- Any feature that spans multiple pipeline steps or multiple API endpoints needs an integration test that exercises the full flow.
- When two code paths can modify the same record (e.g. pipeline auto-approve vs. human approve), write a test for each path and verify the final state is identical where it should be.
