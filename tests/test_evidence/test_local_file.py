"""Tests for LocalFileEvidenceProvider using temp directories."""

import hashlib
import pytest
from pathlib import Path

from investigator.evidence.local_file import LocalFileEvidenceProvider
from investigator.models import EvidenceSource


@pytest.fixture()
def log_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def provider(log_dir: Path) -> LocalFileEvidenceProvider:
    return LocalFileEvidenceProvider(root=log_dir)


class TestLocalFileEvidenceProvider:
    def test_returns_empty_for_no_files(
        self, provider: LocalFileEvidenceProvider, log_dir: Path
    ) -> None:
        refs = provider.fetch(job_name="missing_job", incident_id="abc")
        assert refs == []

    def test_finds_log_file_by_job_name(
        self, provider: LocalFileEvidenceProvider, log_dir: Path
    ) -> None:
        job_dir = log_dir / "cdc_orders"
        job_dir.mkdir()
        log_file = job_dir / "run_123.log"
        log_file.write_text("Error: Column X missing\nStack trace follows\n")

        refs = provider.fetch(job_name="cdc_orders", incident_id="inc-1")
        assert len(refs) == 1
        assert refs[0].source == EvidenceSource.local_file

    def test_ref_has_correct_pointer_format(
        self, provider: LocalFileEvidenceProvider, log_dir: Path
    ) -> None:
        job_dir = log_dir / "my_job"
        job_dir.mkdir()
        (job_dir / "run.log").write_text("some log content")

        refs = provider.fetch(job_name="my_job", incident_id="inc-2")
        assert len(refs) == 1
        assert "my_job" in refs[0].pointer

    def test_ref_has_valid_sha256_hash(
        self, provider: LocalFileEvidenceProvider, log_dir: Path
    ) -> None:
        content = "log content here"
        job_dir = log_dir / "job_a"
        job_dir.mkdir()
        (job_dir / "run.log").write_text(content)

        refs = provider.fetch(job_name="job_a", incident_id="inc-3")
        assert len(refs) == 1
        expected = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        assert refs[0].hash == expected

    def test_snippet_truncated_to_limit(
        self, provider: LocalFileEvidenceProvider, log_dir: Path
    ) -> None:
        long_content = "x" * 5000
        job_dir = log_dir / "big_job"
        job_dir.mkdir()
        (job_dir / "big.log").write_text(long_content)

        refs = provider.fetch(job_name="big_job", incident_id="inc-4")
        assert refs[0].snippet is not None
        assert len(refs[0].snippet) <= 2000

    def test_multiple_log_files_capped(
        self, provider: LocalFileEvidenceProvider, log_dir: Path
    ) -> None:
        job_dir = log_dir / "multi_job"
        job_dir.mkdir()
        for i in range(20):
            (job_dir / f"run_{i}.log").write_text(f"log {i}")

        # Should not exceed max_items=10 (EvidenceRef contract)
        refs = provider.fetch(job_name="multi_job", incident_id="inc-5")
        assert 0 < len(refs) <= 10

    def test_ignores_non_log_files(
        self, provider: LocalFileEvidenceProvider, log_dir: Path
    ) -> None:
        job_dir = log_dir / "job_b"
        job_dir.mkdir()
        (job_dir / "run.log").write_text("actual log")
        (job_dir / "readme.txt").write_text("not a log")
        (job_dir / "config.json").write_text('{"key": "val"}')

        refs = provider.fetch(job_name="job_b", incident_id="inc-6")
        assert len(refs) == 1
