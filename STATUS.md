# Project Status — Autonomous Data Incident Investigator

## Current Week: 8

## Progress

- [x] Week 1 — Foundation & Architecture
- [x] Week 2 — Data Ingestion Pipeline
- [x] Week 3 — AI/LLM Integration
- [x] Week 4 — Agent Orchestration
- [x] Week 5 — Observability & Monitoring
- [x] Week 6 — API & Integration Layer
- [x] Week 7 — Testing, Quality & Security
- [ ] Week 8 — Deployment & Production Readiness

---

## Summaries

## Week 7 Summary

Delivered Testing, Quality & Security using TDD (430 tests, all green):

- **Pipeline approval queue fix** (`src/investigator/workflow/pipeline.py`) — `_step_approve` now calls `create_approval_queue_item` for human-review decisions, wiring the pipeline's `ApprovalDecision` into the DB-backed approvals table; fixes E2E approve/reject flows
- **E2E HTTP lifecycle tests** (`tests/test_e2e/`) — 16 tests covering four full scenarios via HTTP: dev auto-approve (ingest→investigate→APPROVED→feedback), prod human-review (APPROVAL_REQUIRED→approve→APPROVED), prod rejection, and unsafe-plan auto-rejection
- **Contract compliance tests** (`tests/test_contracts/`) — 23 tests that validate every API response field-by-field against `contracts.md`: ingest response, incident record, approval queue item, and error envelope (no extra fields, correct types, ISO datetime strings, no stack traces)
- **Security hardening** (`src/investigator/evidence/local_file.py`) — `LocalFileEvidenceProvider` now resolves the job_dir and asserts it stays inside root, blocking path traversal attacks (`job_name='../../etc'`); 26 security tests covering input length limits, enum enforcement, special characters, and error response safety
- **Postmortem generator** (`src/investigator/reporting/postmortem.py`) — `PostmortemGenerator.generate(IncidentRow)` produces a `Postmortem` dataclass with a `.markdown` property rendering an 8-section blameless postmortem; 39 tests validate all sections, data sourcing, graceful missing-blob handling, and disposition-specific action items
- Committed in 4 incremental commits (727838d→f79a3df)

## Week 6 Summary

Delivered the full API & Integration Layer using TDD (326 tests, all green):

- **ApprovalRow + FeedbackRow ORM** (`src/investigator/db/models.py`) — `approvals` and `feedback` tables with reviewer/outcome fields; 5 new repository methods: `create_approval_queue_item`, `list_pending_approvals`, `get_approval`, `record_approval_decision` (transitions incident state), `create_feedback`, `list_feedback`, `list_incidents` (paginated with status filter)
- **Approval queue API** (`src/investigator/api/routes/approvals.py`) — `GET /approvals/pending`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`; reviewer decision transitions incident through the state machine
- **Feedback API** (`src/investigator/api/routes/feedback.py`) — `POST /incidents/{id}/feedback` with OutcomeType validation, 201 on success, 404 for unknown incidents
- **List incidents** (`GET /incidents`) — paginated with `?status=`, `?limit=`, `?offset=` query params; returns IncidentListItem list sorted by created_at desc
- **Global error envelope** (`app.py`) — all HTTP and validation errors now return `{error, message, trace_id, details?}` matching `contracts.md` Contract 11
- **OpenAPI spec tests** — 15 tests assert every contracted route is present in `/openapi.json`; acts as a route regression guard
- Committed in 5 incremental commits (fa6ef3e→ce5110e)

## Week 5 Summary

Delivered the full observability & monitoring layer using TDD (263 tests, all green):

- **Structured logger** (`src/investigator/observability/logger.py`) — `PipelineLogger` emitting structured log records per step (step_start, step_success, step_error, pipeline_complete) with incident_id, step, duration_ms, outcome extras; pipeline integration hooks emit these automatically
- **MetricsRegistry** (`src/investigator/observability/metrics.py`) — in-memory `Counter` (labeled/unlabeled), `Histogram` (count/mean/p50/p95/p99), and `MetricsRegistry.snapshot()`; pipeline `run()` records `pipeline_runs_total`, `pipeline_errors_total`, `simulation_failures_total`, `pipeline_step_duration_ms`
- **SLO checker** (`src/investigator/observability/slo.py`) — `SLODefinition` + `SLOChecker` evaluating `pipeline_success_rate ≥ 0.95` and `simulation_safe_rate ≥ 0.90`; `STANDARD_SLOS` constant for reuse
- **Observability API** — `GET /metrics` (counter + histogram snapshot), `GET /health` enhanced with DB ping and SLO evaluation (status/db/slos response model)
- Committed in 4 incremental commits (3ff97e0→d7242b1)

## Week 1 Summary

Delivered the full project foundation using TDD (75 tests, all green):

- **pyproject.toml** — project scaffold with Pydantic v2, FastAPI, SQLAlchemy, pytest, ruff, mypy
- **Pydantic models** (`src/investigator/models/`) — typed contracts for all 10 schemas in `docs/contracts.md`: IncidentEvent, ClassificationResult, EvidenceRef, DiagnosisResult, RemediationPlan, SimulationReport, RiskAssessment, ApprovalQueueItem, Feedback, ErrorResponse
- **State machine** (`src/investigator/state/machine.py`) — `IncidentStatus` enum + deterministic `transition()` guard; only allowlisted `(from, to)` pairs are permitted
- **Rules classifier** (`src/investigator/classification/rules.py`) — keyword-based `RulesClassifier` covering 5 incident categories with confidence scoring and unknown fallback
- Committed: `386d9d4`

## Week 4 Summary

Delivered the agent orchestration layer using TDD (202 tests, all green):

- **InvestigationPipeline** (`src/investigator/workflow/pipeline.py`) — sequences Classify→Diagnose→Remediate→Simulate→Risk→Approve; guards on current status so re-runs skip completed steps (resumable from any intermediate state)
- **PipelineResult** (`src/investigator/workflow/result.py`) — typed output capturing every step's artefact and final status; `error` field populated on partial failure
- **Fault-tolerant execution** — LLM failures are caught; incident stays at last good status; artefacts already persisted are preserved; resume with a working pipeline to continue
- **Approval routing** — auto_approve→APPROVED, human_review→APPROVAL_REQUIRED (with role), reject→APPROVAL_REQUIRED→REJECTED
- **Risk engine calibration** — prod weight +20→+30 so production incidents always reach MEDIUM threshold and require human review
- **5 evaluation scenarios** — schema_mismatch/dev→auto_approve, schema_mismatch/prod→on_call_engineer, timeout/prod→review, unknown/prod→review, unsafe_sql→reject
- **API endpoints** — `POST /incidents/{id}/investigate` + `GET /incidents/{id}` with pipeline injected via app state
- Committed in 4 incremental commits (bf7e881→5257d0d)

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
