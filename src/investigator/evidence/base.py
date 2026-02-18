"""EvidenceProvider interface.

V1 uses local files; V2 will swap in OpenSearch/Splunk/Datadog
by implementing this same interface.
"""

from abc import ABC, abstractmethod

from investigator.models import EvidenceRef


class EvidenceProvider(ABC):
    @abstractmethod
    def fetch(self, *, job_name: str, incident_id: str) -> list[EvidenceRef]:
        """Return evidence references for the given job and incident.

        Returns pointers + hashes only — never raw secrets or excessive data.
        """
