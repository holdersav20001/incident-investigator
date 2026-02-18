# Contracts (JSON Schemas)

Generated: 2026-02-18

This document consolidates the **data contracts** for Project 2
(Autonomous Data Incident Investigator) in one place.

Design rules:

-   **All inbound/outbound payloads are validated** with Pydantic models
    (and/or JSON Schema derived from them).
-   **LLM outputs must be structured JSON** that passes schema
    validation.
-   **Confidence values** are always floats in the range **\[0.0,
    1.0\]**.
-   No raw secrets or raw PII are persisted; use redaction + hashes.

------------------------------------------------------------------------

## 1. Incident Event (Ingest)

**API:** `POST /events/ingest`

### JSON Example

``` json
{
  "incident_id": "7c6b0c92-53d6-4c95-9f14-3e0c5fb8a010",
  "source": "airflow",
  "environment": "prod",
  "job_name": "cdc_orders",
  "error_type": "schema_mismatch",
  "error_message": "Column CUSTOMER_ID missing in target",
  "timestamp": "2026-02-18T11:00:00Z",
  "metadata": {
    "dag_id": "cdc_orders",
    "task_id": "load_to_snowflake",
    "run_id": "manual__2026-02-18T11:00:00Z"
  }
}
```

### Contract

``` json
{
  "type": "object",
  "required": ["incident_id","source","environment","job_name","error_type","error_message","timestamp"],
  "properties": {
    "incident_id": {"type":"string","format":"uuid"},
    "source": {"type":"string","enum":["airflow","cloudwatch","manual","other"]},
    "environment": {"type":"string","enum":["prod","staging","dev"]},
    "job_name": {"type":"string","minLength":1,"maxLength":200},
    "error_type": {"type":"string","minLength":1,"maxLength":100},
    "error_message": {"type":"string","minLength":1,"maxLength":4000},
    "timestamp": {"type":"string","format":"date-time"},
    "metadata": {"type":"object","additionalProperties":true}
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 2. Incident Record (Read Model)

**API:** `GET /incidents/{incident_id}`

### Contract

``` json
{
  "type": "object",
  "required": ["incident_id","status","created_at","updated_at"],
  "properties": {
    "incident_id": {"type":"string","format":"uuid"},
    "status": {"type":"string"},
    "classification": {"type":"object"},
    "diagnosis": {"type":"object"},
    "remediation": {"type":"object"},
    "simulation": {"type":"object"},
    "risk": {"type":"object"},
    "approval_status": {"type":"string"},
    "created_at": {"type":"string","format":"date-time"},
    "updated_at": {"type":"string","format":"date-time"}
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 3. ClassificationResult (Deterministic, Rules)

### JSON Example

``` json
{
  "type": "schema_mismatch",
  "confidence": 0.87,
  "reason": "Detected keywords: column missing, schema drift"
}
```

### Contract

``` json
{
  "type":"object",
  "required":["type","confidence","reason"],
  "properties": {
    "type": {"type":"string","enum":["schema_mismatch","timeout","data_quality","auth","connectivity","unknown"]},
    "confidence": {"type":"number","minimum":0.0,"maximum":1.0},
    "reason": {"type":"string","minLength":1,"maxLength":1000}
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 4. EvidenceRef (Pointers, not raw logs)

### JSON Example

``` json
{
  "source": "local_file",
  "pointer": "logs/cdc_orders/2026-02-18/run_123.log#L120-L150",
  "snippet": "Error: Column CUSTOMER_ID missing...",
  "hash": "sha256:..."
}
```

### Contract

``` json
{
  "type":"object",
  "required":["source","pointer","hash"],
  "properties": {
    "source": {"type":"string","enum":["local_file","db","http","opensearch","other"]},
    "pointer": {"type":"string","minLength":1,"maxLength":2000},
    "snippet": {"type":"string","maxLength":2000},
    "hash": {"type":"string","minLength":1,"maxLength":200}
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 5. DiagnosisResult (LLM Structured Output)

### JSON Example

``` json
{
  "root_cause": "schema drift in upstream extractor",
  "evidence": [{"source":"local_file","pointer":"...","hash":"sha256:..."}],
  "confidence": 0.78,
  "next_checks": ["Compare source schema vs target", "Check last successful run"]
}
```

### Contract

``` json
{
  "type":"object",
  "required":["root_cause","evidence","confidence"],
  "properties": {
    "root_cause": {"type":"string","minLength":1,"maxLength":2000},
    "evidence": {"type":"array","items": {"$ref":"#/definitions/EvidenceRef"}, "maxItems": 10},
    "confidence": {"type":"number","minimum":0.0,"maximum":1.0},
    "next_checks": {"type":"array","items": {"type":"string","maxLength":500}, "maxItems": 10}
  },
  "definitions": {
    "EvidenceRef": {
      "type":"object",
      "required":["source","pointer","hash"],
      "properties": {
        "source": {"type":"string"},
        "pointer": {"type":"string"},
        "snippet": {"type":"string"},
        "hash": {"type":"string"}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 6. RemediationPlan (LLM Structured Output, No Execution)

### JSON Example

``` json
{
  "plan": [
    {"step":"Re-run extractor with updated schema mapping","tool":"rerun_job","command":"dag=cdc_orders task=extract"},
    {"step":"Backfill last 1 day","tool":"sql","command":"SELECT ..."} 
  ],
  "rollback": [{"step":"Revert mapping to previous version"}],
  "expected_time_minutes": 15
}
```

### Contract

``` json
{
  "type":"object",
  "required":["plan","rollback","expected_time_minutes"],
  "properties": {
    "plan": {
      "type":"array",
      "minItems": 1,
      "maxItems": 12,
      "items": {"$ref":"#/definitions/PlanStep"}
    },
    "rollback": {
      "type":"array",
      "maxItems": 8,
      "items": {"$ref":"#/definitions/RollbackStep"}
    },
    "expected_time_minutes": {"type":"integer","minimum":1,"maximum":1440}
  },
  "definitions": {
    "PlanStep": {
      "type":"object",
      "required":["step","tool","command"],
      "properties": {
        "step": {"type":"string","minLength":1,"maxLength":1000},
        "tool": {"type":"string","enum":["sql","vector","rest","rerun_job","notify","noop"]},
        "command": {"type":"string","minLength":1,"maxLength":4000}
      },
      "additionalProperties": false
    },
    "RollbackStep": {
      "type":"object",
      "required":["step"],
      "properties": {
        "step": {"type":"string","minLength":1,"maxLength":1000}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 7. SimulationReport (Deterministic)

### JSON Example

``` json
{
  "ok": true,
  "checks": [
    {"name":"sql_is_select_only","ok":true},
    {"name":"tables_allowlisted","ok":true},
    {"name":"estimated_rows","ok":true,"value": 1200}
  ],
  "notes": ["No writes detected. Safe to review."]
}
```

### Contract

``` json
{
  "type":"object",
  "required":["ok","checks"],
  "properties": {
    "ok": {"type":"boolean"},
    "checks": {"type":"array","items": {"$ref":"#/definitions/Check"}, "maxItems": 50},
    "notes": {"type":"array","items": {"type":"string","maxLength":500}, "maxItems": 20}
  },
  "definitions": {
    "Check": {
      "type":"object",
      "required":["name","ok"],
      "properties": {
        "name": {"type":"string","maxLength":200},
        "ok": {"type":"boolean"},
        "value": {"type":["string","number","integer","boolean","null"]}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 8. RiskAssessment (Deterministic)

### Contract

``` json
{
  "type":"object",
  "required":["risk_score","risk_level","recommendation"],
  "properties": {
    "risk_score": {"type":"integer","minimum":0,"maximum":100},
    "risk_level": {"type":"string","enum":["LOW","MEDIUM","HIGH"]},
    "recommendation": {"type":"string","enum":["auto_approve","human_review","reject"]},
    "rationale": {"type":"string","maxLength":2000},
    "blast_radius": {"type":"array","items": {"type":"string","maxLength":300}, "maxItems": 200}
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 9. Approval Queue Item

**API:** `GET /approvals/pending`,
`POST /approvals/{incident_id}/approve|reject`

### Contract

``` json
{
  "type":"object",
  "required":["incident_id","status","required_role","created_at"],
  "properties": {
    "incident_id": {"type":"string","format":"uuid"},
    "status": {"type":"string","enum":["pending","approved","rejected"]},
    "required_role": {"type":"string","maxLength":200},
    "reviewer": {"type":"string","maxLength":200},
    "reviewer_note": {"type":"string","maxLength":2000},
    "created_at": {"type":"string","format":"date-time"},
    "reviewed_at": {"type":"string","format":"date-time"}
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 10. Feedback (Learning Loop)

### Contract

``` json
{
  "type":"object",
  "required":["incident_id","outcome","timestamp"],
  "properties": {
    "incident_id": {"type":"string","format":"uuid"},
    "outcome": {"type":"string","enum":["fixed","not_fixed","unknown"]},
    "overrides": {"type":"object","additionalProperties":true},
    "reviewer_notes": {"type":"string","maxLength":4000},
    "timestamp": {"type":"string","format":"date-time"}
  },
  "additionalProperties": false
}
```

------------------------------------------------------------------------

## 11. Error Response Envelope (API)

All API errors return the same envelope.

``` json
{
  "type":"object",
  "required":["error","message","trace_id"],
  "properties": {
    "error": {"type":"string"},
    "message": {"type":"string"},
    "trace_id": {"type":"string","minLength":8,"maxLength":128},
    "details": {"type":"object","additionalProperties":true}
  },
  "additionalProperties": false
}
```
