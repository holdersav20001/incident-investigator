"""Local filesystem evidence provider.

Reads `.log` files under `<root>/<job_name>/` and returns EvidenceRef
objects with SHA-256 hashes. Snippets are capped at 2000 chars to stay
within the contract limit.
"""

import hashlib
from pathlib import Path

from investigator.models import EvidenceRef, EvidenceSource
from .base import EvidenceProvider

_MAX_REFS = 10
_SNIPPET_LIMIT = 2000


class LocalFileEvidenceProvider(EvidenceProvider):
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def fetch(self, *, job_name: str, incident_id: str) -> list[EvidenceRef]:
        # Resolve the candidate directory and verify it stays inside the root.
        # A job_name like "../../etc" would otherwise escape to the filesystem.
        job_dir = (self._root / job_name).resolve()
        try:
            job_dir.relative_to(self._root)
        except ValueError:
            # Path traversal attempt — silently return no evidence
            return []
        if not job_dir.is_dir():
            return []

        log_files = sorted(job_dir.glob("*.log"))[:_MAX_REFS]
        refs: list[EvidenceRef] = []

        for log_file in log_files:
            content = log_file.read_text(encoding="utf-8", errors="replace")
            digest = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
            snippet = content[:_SNIPPET_LIMIT] if content else None

            refs.append(
                EvidenceRef(
                    source=EvidenceSource.local_file,
                    pointer=f"{job_name}/{log_file.name}",
                    hash=digest,
                    snippet=snippet,
                )
            )

        return refs
