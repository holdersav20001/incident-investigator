# Project Instructions for Claude

## Autonomy Level: HIGH

- Proceed with implementation without asking for approval
- Make standard engineering decisions autonomously
- Use common patterns and conventions
- Only ask if there's a critical security/data risk

## Default Preferences

- **Language**: Python 3.11+
- **Style**: Follow PEP 8, use type hints
- **Testing**: Write tests for all new functions, including negative tests for every user-facing input (invalid enums, missing fields, boundary values)
- **Comments**: Explain "why" not "what"
- **Error handling**: Every API route must catch exceptions that can arise from user input (ValueError, KeyError, enum coercion) and return a 4xx response. Never let unhandled exceptions reach the client as 500s.
- **Database sessions**: Always use per-request sessions via FastAPI `Depends` with `yield`. Never share a session across requests.
- **Shared state**: When modifying a field that is written by more than one code path (e.g. `approval_status`), grep for ALL other writers and ensure consistency. Write a cross-cutting test.

## When to Ask

ONLY ask if:
1. Deleting production data
2. Changing authentication/security
3. Major architecture change
4. Contradictory requirements

Otherwise: **JUST DO IT** ✅

## Session Continuity

**At the start of every session (do this before anything else):**

1. Read `STATUS.md` to find the current week and what has been completed
2. Read `INVARIANTS.md` — these are system-wide rules that must hold across all code. Verify new work does not violate them.
3. Read `WEEK0X_PROMPT.md` and `WEEK0X_PLAN.md` for the current week (replace `0X` with the current week number)
4. Continue from where the previous session left off — do not restart completed work

**When a week is complete (all tests passing, CI green, commits done):**

1. Update `STATUS.md` — mark the week as `[x]` complete and advance `Current Week` to the next
2. Write a brief `## Week N Summary` entry in `STATUS.md` describing what was delivered
3. Notify the user: "Week N complete. Ready to begin Week N+1 — type /compact before continuing to keep context clean."

> Note: `/compact` must be run by the user, not by Claude. The reminder above is the handoff signal.

## Skills (Project-Wide)

These skills from `.claude/skills/` apply to **every week** and are always active:

- `/architecture` — system design and structural decisions
- `/api-design-principles` — consistent, contract-first API design
- `/tdd-workflow` — enforce test-first development throughout
- `/python-pro` — Python best practices, idioms, and performance
- `/python-patterns` — reusable Python patterns and conventions
- `/incident-responder` — incident investigation mindset and response patterns
