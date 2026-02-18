"""Evidence providers — pluggable interface for fetching log evidence."""

from .base import EvidenceProvider
from .local_file import LocalFileEvidenceProvider

__all__ = ["EvidenceProvider", "LocalFileEvidenceProvider"]
