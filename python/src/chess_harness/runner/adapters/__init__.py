"""Factory for runner move adapters."""

from __future__ import annotations

from typing import Optional

from ..config import SlotConfig
from .openai import OpenAIAdapter
from .stub import StubAdapter

TransportFn = object


def build_adapter(slot: SlotConfig, transport: TransportFn, *, stub_moves=None):
    provider = slot.provider.strip().lower()
    if provider in {"stub", "fake"}:
        return StubAdapter(moves=stub_moves)
    if provider == "openai":
        return OpenAIAdapter(
            base_url=slot.base_url or "https://api.openai.com/v1",
            model=slot.provider_model,
            env_key=slot.env_key,
            observation=slot.observation,
            transport=transport,
            jpeg_max_side=slot.jpeg_max_side,
        )
    raise ValueError(f"unsupported provider '{slot.provider}'")
