"""EvidenceRef — pointer to a piece of evidence, never raw log content."""

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class EvidenceSource(StrEnum):
    local_file = "local_file"
    db = "db"
    http = "http"
    opensearch = "opensearch"
    other = "other"


class EvidenceRef(BaseModel):
    model_config = {"extra": "forbid"}

    source: EvidenceSource
    pointer: str = Field(min_length=1, max_length=2000)
    snippet: Optional[str] = Field(default=None, max_length=2000)
    hash: str = Field(min_length=1, max_length=200)
