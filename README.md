# Incident Investigator

An autonomous data incident investigation system that classifies, diagnoses, and proposes remediation for data pipeline failures — with deterministic safety gates, LLM-powered analysis, and human-in-the-loop approval.

Built with **Python 3.11+**, **FastAPI**, **SQLAlchemy**, **Pydantic v2**, and a **React** frontend.

---

## How It Works

When a data pipeline fails, Incident Investigator automatically runs a 6-step investigation pipeline:

```mermaid
flowchart LR
    A["1. Classify\n(rules)"] --> B["2. Diagnose\n(LLM)"]
    B --> C["3. Remediate\n(LLM)"]
    C --> D["4. Simulate\n(deterministic)"]
    D --> E["5. Risk Score\n(deterministic)"]
    E --> F["6. Approve\n(policy)"]

    style A fill:#4CAF50,color:#fff
    style B fill:#2196F3,color:#fff
    style C fill:#2196F3,color:#fff
    style D fill:#4CAF50,color:#fff
    style E fill:#4CAF50,color:#fff
    style F fill:#FF9800,color:#fff
```

> **Key principle:** LLMs propose, deterministic code validates and gates. No remediation is ever executed automatically — plans require human approval for production incidents.

---

## Architecture

```mermaid
flowchart TB
    subgraph Users
        UI["React UI\n(Vite SPA)"]
        Eng["On-call Engineer"]
    end

    subgraph Compose["Docker Compose Stack"]
        API["FastAPI\n:8000"]
        subgraph Pipeline["Investigation Pipeline"]
            CL["Classify"] --> DX["Diagnose"]
            DX --> REM["Remediate"]
            REM --> SIM["Simulate"]
            SIM --> RSK["Risk"]
            RSK --> APR["Approve"]
        end
        DB[("PostgreSQL\n:5432")]
        ALE["Alembic\nMigrations"]
    end

    LLM["LLM Provider\n(Anthropic / OpenRouter / Mock)"]

    UI -->|HTTP| API
    Eng -->|HTTP| API
    API --> Pipeline
    Pipeline --> DB
    ALE --> DB
    DX -->|structured JSON| LLM
    REM -->|structured JSON| LLM

    style LLM fill:#2196F3,color:#fff
    style DB fill:#FF9800,color:#fff
    style API fill:#4CAF50,color:#fff
```

---

## Sequence Diagram — Full Investigation Flow

```mermaid
sequenceDiagram
    autonumber
    participant Src as Incident Source
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Pipe as Pipeline
    participant LLM as LLM Provider

    Src->>API: POST /events/ingest
    API->>DB: Create incident (RECEIVED)
    API-->>Src: 201 Created

    Src->>API: POST /incidents/{id}/investigate
    API->>Pipe: run(incident_id)

    rect rgb(200, 230, 200)
        Note over Pipe: Step 1 — Classify (deterministic)
        Pipe->>Pipe: Keyword rules + confidence score
        Pipe->>DB: Persist classification → CLASSIFIED
    end

    rect rgb(200, 230, 200)
        Note over Pipe: Step 2 — Fetch Evidence
        Pipe->>Pipe: Local files + SHA-256 hash
    end

    rect rgb(200, 210, 240)
        Note over Pipe,LLM: Step 3 — Diagnose (LLM)
        Pipe->>LLM: Structured prompt (event + classification + evidence)
        LLM-->>Pipe: DiagnosisResult (JSON)
        Pipe->>DB: Persist diagnosis → DIAGNOSED
    end

    rect rgb(200, 210, 240)
        Note over Pipe,LLM: Step 4 — Remediate (LLM)
        Pipe->>LLM: Structured prompt (diagnosis context)
        LLM-->>Pipe: RemediationPlan (JSON)
    end

    rect rgb(200, 230, 200)
        Note over Pipe: Step 5 — Simulate (deterministic)
        Pipe->>Pipe: SQL safety checks (SELECT only, no DML/DDL)
        Pipe->>DB: Persist simulation → REMEDIATION_PROPOSED
    end

    rect rgb(255, 235, 200)
        Note over Pipe: Step 6 — Risk + Approve (deterministic)
        Pipe->>Pipe: Score 0-100, route decision
        Pipe->>DB: Persist risk + approval → RISK_ASSESSED
    end

    Pipe-->>API: PipelineResult
    API-->>Src: 200 OK (full result)

    opt If APPROVAL_REQUIRED
        Src->>API: POST /approvals/{id}/approve
        API->>DB: Transition → APPROVED
        API-->>Src: 200 OK
    end
```

---

## Approval Routing Logic

```mermaid
flowchart TD
    RISK["Risk Assessment\n(score 0–100)"]

    RISK -->|"score < 30"| LOW["LOW"]
    RISK -->|"30 ≤ score < 70"| MED["MEDIUM"]
    RISK -->|"score ≥ 70\nor simulation failed"| HIGH["HIGH"]

    LOW -->|auto_approve| APPROVED["APPROVED"]
    MED -->|human_review| PENDING["APPROVAL_REQUIRED\n(on_call_engineer\nor data_platform_lead)"]
    HIGH -->|reject| REJECTED["REJECTED"]

    PENDING -->|engineer approves| APPROVED
    PENDING -->|engineer rejects| REJECTED

    style LOW fill:#4CAF50,color:#fff
    style MED fill:#FF9800,color:#fff
    style HIGH fill:#f44336,color:#fff
    style APPROVED fill:#4CAF50,color:#fff
    style REJECTED fill:#f44336,color:#fff
    style PENDING fill:#FF9800,color:#fff
```

---

## State Machine

Every incident transitions through a strict, deterministic state machine. Only allowlisted `(from, to)` transitions are permitted — invalid transitions raise errors.

```mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> CLASSIFIED
    CLASSIFIED --> DIAGNOSED
    DIAGNOSED --> REMEDIATION_PROPOSED
    REMEDIATION_PROPOSED --> RISK_ASSESSED

    RISK_ASSESSED --> APPROVED
    RISK_ASSESSED --> APPROVAL_REQUIRED
    RISK_ASSESSED --> REJECTED

    APPROVAL_REQUIRED --> APPROVED
    APPROVAL_REQUIRED --> REJECTED
```

---

## Project Structure

```
├── main.py                     # Production entrypoint — wires all dependencies
├── src/investigator/
│   ├── api/                    # FastAPI routes (ingest, investigate, approvals, feedback)
│   ├── approval/               # Deterministic approval policy routing
│   ├── classification/         # Rules-based incident classifier
│   ├── config.py               # Pydantic Settings (env vars)
│   ├── db/                     # SQLAlchemy ORM models + session factory
│   ├── diagnosis/              # LLM-powered root-cause analysis engine
│   ├── evidence/               # Evidence provider (local files, SHA-256 hashing)
│   ├── llm/                    # LLM provider abstraction (Anthropic, OpenRouter, Mock)
│   ├── models/                 # Pydantic v2 data contracts (10 schemas)
│   ├── observability/          # Structured logging, metrics, SLO checker
│   ├── remediation/            # LLM planner + deterministic plan simulator
│   ├── reporting/              # Blameless postmortem generator
│   ├── repository/             # Incident repository (CRUD + state transitions)
│   ├── risk/                   # Deterministic 0-100 risk scoring engine
│   ├── state/                  # Incident status enum + state machine
│   └── workflow/               # Investigation pipeline orchestrator
├── ui/                         # React + Vite frontend (incident submission & tracking)
├── tests/                      # 526 unit tests + 23 integration tests
├── evidence/                   # Sample log files with real stack traces
├── alembic/                    # Database migrations
├── Dockerfile                  # Multi-stage build (non-root, slim)
├── docker-compose.yml          # Postgres + API stack
└── docs/                       # Architecture (C4), contracts, sequence diagrams
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/events/ingest` | Submit a pipeline failure event |
| `POST` | `/incidents/{id}/investigate` | Trigger the 6-step investigation pipeline |
| `GET` | `/incidents/{id}` | Get full incident record with all artefacts |
| `GET` | `/incidents` | List incidents (paginated, filterable by status) |
| `GET` | `/approvals/pending` | List incidents awaiting human approval |
| `POST` | `/approvals/{id}/approve` | Approve a remediation plan |
| `POST` | `/approvals/{id}/reject` | Reject a remediation plan |
| `POST` | `/incidents/{id}/feedback` | Submit outcome feedback (learning loop) |
| `GET` | `/metrics` | Prometheus-style metrics snapshot |
| `GET` | `/health` | Health check (DB ping + SLO evaluation) |

---

## Quick Start

### Development (no external dependencies)

```bash
# Clone and install
git clone https://github.com/holdersav20001/incident-investigator.git
cd incident-investigator
pip install -e ".[dev]"

# Run with SQLite + mock LLM (no API key needed)
python main.py
```

The API starts at `http://localhost:8000`. The mock LLM returns plausible stub responses so the full pipeline completes end-to-end.

### With Docker Compose (Postgres)

```bash
cp .env.example .env
# Edit .env with your LLM API key (optional)

docker compose up
```

### With a real LLM

```bash
# Anthropic
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python main.py

# OpenRouter
export LLM_PROVIDER=openrouter
export OPENROUTER_API_KEY=sk-or-...
python main.py
```

### React UI

```bash
cd ui
npm install
npm run dev
```

Opens at `http://localhost:5173` with a Vite proxy to the API.

---

## Running Tests

```bash
# Unit tests (526 tests, no Docker required)
pytest

# Integration tests (requires Docker)
pytest -m integration

# Full verification (compose + alembic + all tests)
pwsh scripts/verify.ps1
```

---

## Deterministic vs LLM Boundary

A core design principle — LLMs only handle unstructured reasoning. Everything else is deterministic:

| Component | Deterministic | LLM |
|-----------|:---:|:---:|
| State transitions | Yes | - |
| Schema/SQL validation | Yes | - |
| Approval policy | Yes | - |
| Classification | Yes (rules) | - |
| Risk scoring | Yes | - |
| **Diagnosis** | - | **Yes** |
| **Remediation planning** | - | **Yes** |

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic
- **Frontend:** React, Vite
- **Database:** PostgreSQL 16 (SQLite for development)
- **LLM:** Anthropic Claude / OpenRouter (pluggable provider abstraction)
- **Testing:** pytest (526 unit + 23 integration), testcontainers
- **CI:** GitHub Actions (test matrix + ruff lint)
- **Deployment:** Docker multi-stage build, docker-compose

---

## License

MIT
