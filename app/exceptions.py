"""Application-specific exceptions."""


class SmartOkfError(Exception):
    """Base error for smart-okf operations."""


class LLMClientError(SmartOkfError):
    """Raised when a local LLM request fails."""


class DocumentIngestError(SmartOkfError):
    """Raised when document ingestion or OKF serialization fails."""


class EncryptedDocumentError(DocumentIngestError):
    """Raised when a file is password-protected / encrypted and cannot be read.

    A subtype of `DocumentIngestError` so existing catch-alls still skip the file, but
    distinct so ingest can log a specific, human-clear reason ("password-protected")
    rather than an opaque parser traceback — the run continues, the file is just skipped.
    """
