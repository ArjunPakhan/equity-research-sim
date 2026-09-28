"""
Shared NVIDIA NIM configuration for the Research and Debate agents.

NVIDIA NIM exposes an OpenAI-compatible /v1/chat/completions endpoint.
Configuration comes from the process environment only:

    NVIDIA_API_KEY    required for real LLM calls (never committed, never logged)
    NVIDIA_MODEL      optional override (default: nvidia/nemotron-3.5-lightning-30b-a3b)
    NVIDIA_BASE_URL   optional override (default: https://integrate.api.nvidia.com/v1)
"""

from __future__ import annotations

import os
from typing import Optional

NVIDIA_BASE_URL_DEFAULT = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL_DEFAULT = "nvidia/nemotron-3.5-lightning-30b-a3b"


def nvidia_api_key() -> Optional[str]:
    """Return the NVIDIA API key from the environment, or None. Never logged."""
    return os.environ.get("NVIDIA_API_KEY") or None


def nvidia_base_url() -> str:
    """Return the NVIDIA NIM OpenAI-compatible base URL."""
    return os.environ.get("NVIDIA_BASE_URL") or NVIDIA_BASE_URL_DEFAULT


def nvidia_model() -> str:
    """Return the NVIDIA NIM model identifier."""
    return os.environ.get("NVIDIA_MODEL") or NVIDIA_MODEL_DEFAULT


def llm_enabled() -> bool:
    """
    True only when a real NVIDIA NIM call is allowed:
    a key exists AND we are not inside pytest (tests stay deterministic).
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return nvidia_api_key() is not None
