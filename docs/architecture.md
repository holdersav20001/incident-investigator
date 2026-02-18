# Architecture (C4 + Sequence Diagrams)

Generated: 2026-02-18

This document describes the V1 architecture for Project 2 using a
simplified local stack (Docker Compose, Postgres, Redis optional,
Airflow, FastAPI).

Principles: - Deterministic boundaries govern execution. - LLMs propose;
the system validates and gates. - All decisions are auditable and
observable. - Interfaces remain pluggable for V2 cloud adoption.

------------------------------------------------------------------------

## C4 --- Level 1: System Context (Mermaid)

``` mermaid
C4Context
title Autonomous Data Incident Investigator — System Context

Person(oncall, "On-call Engineer", "Receives incidents, reviews approval queue, provides feedback")
Person(dataeng, "Data Engineer", "Owns pipelines, uses incident reports and remediation plans")
System(system, "Incident Investigator", "Classifies, diagnoses, proposes remediation, risk-scores, routes for approval")
System_Ext(airflow, "Orchestrator (Airflow)", "Runs scheduled/triggered workflows")
System_Ext(llm, "LLM Provider", "Structured diagnosis/remediation planning")
System_Ext(pipelines, "Data Pipelines", "Emit failure signals and logs")

Rel(oncall, system, "Reviews, approves/rejects, adds feedback")
Rel(dataeng, system, "Consumes incident reports and fix plans")
Rel(pipelines, system, "Sends events/log pointers")
Rel(system, airflow, "Triggers workflow runs")
Rel(system, llm, "Requests structured JSON outputs (guardrailed)")
```

> Note: Some Mermaid renderers require the C4 extension. If your preview
> does not support `C4Context`, keep the diagram in docs for GitHub
> rendering (or use the alternative below).

### Alternative (Plain Mermaid)

``` mermaid
flowchart LR
  oncall[On-call Engineer] -->|approve/reject, feedback| svc[Incident Investigator API]
  dataeng[Data Engineer] -->|review incident report| svc
  pipelines[Data Pipelines] -->|failure event + log pointers| svc
  svc -->|orchestrate| airflow[Airflow]
  svc -->|structured JSON| llm[LLM Provider]
  svc --> pg[(Postgres)]
  svc --> redis[(Redis optional)]
  svc --> fs[(Filesystem artifacts)]
```

------------------------------------------------------------------------

## C4 --- Level 2: Containers

``` mermaid
flowchart TB
  subgraph Compose["Docker Compose (V1)"]
    api[FastAPI: incident-investigator]
    airflow[Airflow: workflow runner]
    pg[(Postgres: incidents, audit, lineage)]
    redis[(Redis: optional queue/cache)]
    fs[(Filesystem volume: runbooks/log samples)]
  end

  llm[External LLM Provider]
  user[On-call Engineer]

  user -->|API calls| api
  api --> pg
  api --> redis
  airflow --> pg
  airflow --> api
  api -->|diagnosis/remediation JSON| llm
  api --> fs
```

Key notes: - Postgres is the **source of truth** for state. - Airflow
orchestrates state transitions; transitions are **idempotent**. - LLM
calls are done via a provider abstraction; CI uses a mock provider.

------------------------------------------------------------------------

## Core Runtime Flow

### Sequence: Ingest → Classify → Diagnose → Remediate → Risk → Approval

``` mermaid
sequenceDiagram
  autonumber
  participant Src as Incident Source
  participant API as FastAPI
  participant DB as Postgres
  participant WF as Workflow Runner (Airflow)
  participant CL as Classifier (rules)
  participant EV as Evidence Provider
  participant LLM as LLM Provider
  participant VAL as Deterministic Validators
  participant RISK as Risk Engine
  participant APPR as Approval/Policy

  Src->>API: POST /events/ingest (IncidentEvent)
  API->>DB: create/update incident + append event
  API->>DB: transition RECEIVED

  WF->>DB: fetch incidents in RECEIVED
  WF->>CL: classify(event summary)
  CL-->>WF: ClassificationResult
  WF->>DB: persist classification + transition CLASSIFIED

  WF->>EV: fetch evidence refs (pointers/snippets)
  EV-->>WF: EvidenceRef[]
  WF->>LLM: diagnose (structured JSON only)
  LLM-->>WF: DiagnosisResult (JSON)
  WF->>VAL: validate schema + confidence
  VAL-->>WF: ok / fail (deterministic)
  WF->>DB: persist diagnosis + transition DIAGNOSED

  WF->>LLM: propose remediation plan (structured JSON only)
  LLM-->>WF: RemediationPlan (JSON)
  WF->>VAL: validate plan + simulate (no execution)
  VAL-->>WF: SimulationReport
  WF->>DB: persist remediation + simulation + transition REMEDIATION_PROPOSED

  WF->>RISK: score risk using simulation + lineage
  RISK-->>WF: RiskAssessment
  WF->>DB: persist risk + transition RISK_ASSESSED

  WF->>APPR: policy decision (deterministic)
  APPR-->>WF: auto_approve / queue / reject
  WF->>DB: persist approval decision + transition APPROVAL_REQUIRED/APPROVED/REJECTED
```

------------------------------------------------------------------------

## Deterministic vs LLM Boundary

  Component                           Deterministic              LLM
  --------------------------------- --------------- ----------------
  State transitions                              ✅               ❌
  Validation (schema, SQL safety)                ✅               ❌
  Policy / approval decisions                    ✅               ❌
  Classification                      ✅ (V1 rules)   optional later
  Diagnosis                                      ❌               ✅
  Remediation proposal                           ❌               ✅
  Risk scoring                                   ✅               ❌

------------------------------------------------------------------------

## Data Stores (V1)

-   **Postgres**
    -   incidents (JSONB fields for agent outputs)
    -   incident_events
    -   transitions (append-only)
    -   approvals_queue
    -   feedback
    -   lineage_edges + resource_metadata
-   **Filesystem volume**
    -   sample logs / runbooks for evidence provider
-   **Redis (optional)**
    -   lightweight queue/caching for workflow coordination

------------------------------------------------------------------------

## V2 Seam (Cloud Adoption Without Rewrite)

To keep V2 easy, V1 should code against interfaces: - EvidenceProvider
(local files → OpenSearch/Splunk/Datadog later) - LineageStore (Postgres
→ graph DB later) - EventSource (API ingest → event bus later) -
ArtifactStore (filesystem → S3 later)

------------------------------------------------------------------------
