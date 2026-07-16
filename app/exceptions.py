"""Application-specific exceptions."""


class SmartOkfError(Exception):
    """Base error for smart-okf operations."""


class LLMClientError(SmartOkfError):
    """Raised when a local LLM request fails."""


class DocumentIngestError(SmartOkfError):
    """Raised when document ingestion or OKF serialization fails."""
