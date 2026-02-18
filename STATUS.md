# Project Status — Autonomous Data Incident Investigator

## Current Week: 4

## Progress

- [x] Week 1 — Foundation & Architecture
- [x] Week 2 — Data Ingestion Pipeline
- [x] Week 3 — AI/LLM Integration
- [ ] Week 4 — Agent Orchestration
- [ ] Week 5 — Observability & Monitoring
- [ ] Week 6 — API & Integration Layer
- [ ] Week 7 — Testing, Quality & Security
- [ ] Week 8 — Deployment & Production Readiness

---

## Summaries

## Week 1 Summary

Delivered the full project foundation using TDD (75 tests, all green):

- **pyproject.toml** — project scaffold with Pydantic v2, FastAPI, SQLAlchemy, pytest, ruff, mypy
- **Pydantic models** (`src/investigator/models/`) — typed contracts for all 10 schemas in `docs/contracts.md`: IncidentEvent, ClassificationResult, EvidenceRef, DiagnosisResult, RemediationPlan, SimulationReport, RiskAssessment, ApprovalQueueItem, Feedback, ErrorResponse
- **State machine** (`src/investigator/state/machine.py`) — `IncidentStatus` enum + deterministic `transition()` guard; only allowlisted `(from, to)` pairs are permitted
- **Rules classifier** (`src/investigator/classification/rules.py`) — keyword-based `RulesClassifier` covering 5 incident categories with confidence scoring and unknown fallback
- Committed: `386d9d4`

## Week 3 Summary

Delivered the full AI/LLM integration layer using TDD (158 tests, all green):

- **LLM Provider abstraction** (`src/investigator/llm/`) — `LLMProvider` ABC with `complete(system, user, response_model)` → validated Pydantic model; `MockLLMProvider` for CI with scripted responses and call log
- **DiagnosisEngine** (`src/investigator/diagnosis/`) — builds structured prompts from incident event, classification, and evidence; calls LLM; returns validated `DiagnosisResult`
- **RemediationPlanner** (`src/investigator/remediation/planner.py`) — LLM-backed plan generation from diagnosis context; returns validated `RemediationPlan`
- **PlanSimulator** (`src/investigator/remediation/simulator.py`) — deterministic `sql_is_select_only` safety check; blocks any SQL step with forbidden DML/DDL
- **RiskEngine** (`src/investigator/risk/`) — deterministic 0–100 scoring from named factors (simulation, environment, confidence, time, classification); LOW→auto_approve, MEDIUM→human_review, HIGH+sim_fail→reject
- **ApprovalPolicy** (`src/investigator/approval/`) — deterministic routing: auto_approve→approved, human_review→pending with role (MEDIUM=on_call_engineer, HIGH=data_platform_lead), reject→rejected
- Committed in 5 incremental commits (ad60589→bd260fa)

## Week 2 Summary

Delivered the full data ingestion pipeline using TDD (108 tests, all green):

- **SQLAlchemy ORM** (`src/investigator/db/`) — `incidents`, `incident_events`, `transitions` tables; JSON columns for agent output blobs; session factory supports SQLite (tests) and Postgres (production)
- **Repository** (`src/investigator/repository/`) — `SqlIncidentRepository` with full CRUD; all state transitions validated through the Week 1 state machine before persisting
- **Evidence provider** (`src/investigator/evidence/`) — `EvidenceProvider` ABC + `LocalFileEvidenceProvider` reading `.log` files with SHA-256 hashing, 2000-char snippet cap
- **FastAPI app** (`src/investigator/api/`) — `POST /events/ingest` (201/409/422) + `GET /health`; tests use `StaticPool` for thread-safe in-memory SQLite
- Committed: `264a9de`
