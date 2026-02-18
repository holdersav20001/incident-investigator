"""IncidentEvent (ingest) and IncidentRecord (read model)."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class IncidentSource(StrEnum):
    airflow = "airflow"
    cloudwatch = "cloudwatch"
    manual = "manual"
    other = "other"


class IncidentEnvironment(StrEnum):
    prod = "prod"
    staging = "staging"
    dev = "dev"


class IncidentEvent(BaseModel):
    """Inbound payload for POST /events/ingest."""

    model_config = {"extra": "forbid"}

    incident_id: UUID
    source: IncidentSource
    environment: IncidentEnvironment
    job_name: str = Field(min_length=1, max_length=200)
    error_type: str = Field(min_length=1, max_length=100)
    error_message: str = Field(min_length=1, max_length=4000)
    timestamp: datetime
    metadata: Optional[dict[str, Any]] = None


class IncidentRecord(BaseModel):
    """Read model for GET /incidents/{incident_id}."""

    model_config = {"extra": "forbid"}

    incident_id: UUID
    status: str
    classification: Optional[dict[str, Any]] = None
    diagnosis: Optional[dict[str, Any]] = None
    remediation: Optional[dict[str, Any]] = None
    simulation: Optional[dict[str, Any]] = None
    risk: Optional[dict[str, Any]] = None
    approval_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime
