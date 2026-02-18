"""Tests for EvidenceRef model."""

import pytest
from pydantic import ValidationError

from investigator.models import EvidenceRef, EvidenceSource


class TestEvidenceRef:
    def test_valid_minimal(self) -> None:
        ref = EvidenceRef(
            source=EvidenceSource.local_file,
            pointer="logs/cdc_orders/run_123.log#L120-L150",
            hash="sha256:abc123",
        )
        assert ref.snippet is None

    def test_valid_with_snippet(self) -> None:
        ref = EvidenceRef(
            source=EvidenceSource.local_file,
            pointer="logs/x.log",
            hash="sha256:abc",
            snippet="Error: Column CUSTOMER_ID missing",
        )
        assert ref.snippet is not None

    def test_invalid_source(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRef(source="s3", pointer="x", hash="sha256:x")

    def test_snippet_max_length(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRef(
                source=EvidenceSource.local_file,
                pointer="x",
                hash="sha256:x",
                snippet="x" * 2001,
            )

    def test_pointer_max_length(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRef(source=EvidenceSource.db, pointer="x" * 2001, hash="sha256:x")

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRef(
                source=EvidenceSource.db,
                pointer="x",
                hash="sha256:x",
                unknown="bad",
            )
