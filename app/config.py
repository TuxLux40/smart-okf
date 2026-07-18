"""Application configuration: YAML file + environment variable loading.

Load order (lowest to highest precedence): field defaults -> smart-okf.yaml -> env vars
(`SMART_OKF_` prefix).
"""

import ipaddress
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from app.constants import (
    DEFAULT_LLM_HOST,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
)

DEFAULT_CONFIG_FILENAME = "smart-okf.yaml"
DEFAULT_LLM_HOST_ALLOWLIST = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
ALWAYS_ALLOWED_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})


def parse_llm_host(value: str) -> str:
    """Extract a bare hostname from a URL or `host:port` string.

    `http://localhost:11434` -> `localhost`; `localhost:11434` -> `localhost`.
    """
    if "://" in value:
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError(f"Invalid llm_host URL: {value}")
        return parsed.hostname
    return value.split(":")[0]


def _is_rfc1918(hostname: str) -> bool:
    try:
        return ipaddress.ip_address(hostname).is_private
    except ValueError:
        return False


def host_is_allowlisted(hostname: str, extra: list[str]) -> bool:
    """True if `hostname` is always-allowed, RFC1918 private, or in `extra`."""
    if hostname in ALWAYS_ALLOWED_HOSTNAMES:
        return True
    if _is_rfc1918(hostname):
        return True
    return hostname in extra


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """Load `smart-okf.yaml` (or `~/.config/smart-okf/smart-okf.yaml`) via pyyaml."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = Path(os.getenv("SMART_OKF_CONFIG", DEFAULT_CONFIG_FILENAME))
        if not path.exists():
            path = Path.home() / ".config/smart-okf" / DEFAULT_CONFIG_FILENAME
        if path.exists():
            return yaml.safe_load(path.read_text()) or {}
        return {}


class SmartOkfConfig(BaseSettings):
    """Root application configuration.

    Trimmed to fields the actual pipeline (`app/services/ingest.py`) reads. Fields from
    the pre-rewrite design (colocation_mode, watcher_*, sqlite_path, bind_host/port, ...)
    were removed as dead config — see the 2026-07-17/18 amendments in docs/DESIGN.md for
    why those subsystems were cut. Re-add fields here only when the code that reads them
    actually exists.
    """

    model_config = SettingsConfigDict(env_prefix="SMART_OKF_", env_nested_delimiter="__")

    document_roots: list[Path] = Field(..., min_length=1)

    llm_model: str = DEFAULT_LLM_MODEL
    llm_temperature: float = DEFAULT_LLM_TEMPERATURE
    llm_max_tokens: int = DEFAULT_MAX_TOKENS
    allow_remote_llm: bool = False
    llm_host_allowlist: list[str] = Field(default_factory=lambda: list(DEFAULT_LLM_HOST_ALLOWLIST))
    llm_host: str = DEFAULT_LLM_HOST

    use_marker: bool = True
    """Route PDF extraction through the marker CLI backend (layout-aware: tables, forms).
    Requires a separately-installed `marker_single` binary on PATH — never a pip
    dependency of this project (marker's code is GPL-3.0); onboarding installs it as a
    prerequisite alongside tesseract/ghostscript. Set false (CLI: `--no-marker`) to opt
    out and use plain pdfplumber/OCRmyPDF instead. See README.md."""

    vision_model: str | None = None
    """Vision-capable model name for standalone image ingest (handwriting transcription +
    scene description), served by the same `llm_host`. None (default) falls back to
    tesseract-only OCR — no vision capability, no dependency added. See README.md."""

    @field_validator("document_roots", mode="before")
    @classmethod
    def validate_document_roots(cls, v: list[Path | str]) -> list[Path]:
        """Require at least one root; normalize to resolved absolute paths."""
        roots = [Path(p).expanduser().resolve() for p in (v or [])]
        if len(roots) < 1:
            raise ValueError("document_roots must contain at least one path")
        return roots

    @field_validator("llm_host")
    @classmethod
    def validate_llm_host(cls, v: str, info: ValidationInfo) -> str:
        """Reject non-allowlisted remote hosts unless `allow_remote_llm` is set."""
        hostname = parse_llm_host(v)
        if host_is_allowlisted(hostname, info.data.get("llm_host_allowlist", [])):
            return v
        if info.data.get("allow_remote_llm"):
            return v
        raise ValueError(f"llm_host hostname {hostname!r} not in allowlist; set allow_remote_llm=true")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, YamlConfigSettingsSource(settings_cls))
