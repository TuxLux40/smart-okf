"""Nested configuration models for `SmartOkfConfig`."""

from pydantic import BaseModel


class FeaturesConfig(BaseModel):
    """Feature toggles for the ingest and reasoning pipeline."""

    derive_on_ingest: bool = True
    derive_sync: bool = False
    dream_enabled: bool = True
    enrichment_gate: bool = True
    store_transcripts: bool = True
    git_auto_commit: bool = False
