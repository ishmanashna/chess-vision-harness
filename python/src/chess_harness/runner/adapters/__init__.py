"""Factory for runner move adapters."""

from __future__ import annotations

from typing import Optional

from ..config import SlotConfig
from .jeff_checklist import JeffChecklistAdapter
from .jeff_council import JeffCouncilAdapter
from .jeff_imagine import JeffImagineAdapter
from .jeff_phase import JeffPhaseAdapter
from .openai import OpenAIAdapter
from .stub import StubAdapter
from .typesafe import TypesafeAdapter

TransportFn = object


def _typesafe_kwargs(slot: SlotConfig, transport: TransportFn) -> dict:
    return dict(
        base_url=slot.base_url or "https://api.typesafe.ai/v1",
        model=slot.provider_model or "jev-latest",
        env_key=slot.env_key or "TYPESAFE_API_KEY",
        observation=slot.observation,
        transport=transport,
        jpeg_max_side=getattr(slot, "jpeg_max_side", None),
        spirit=getattr(slot, "spirit", None),
        duplicate_board=bool(getattr(slot, "duplicate_board", False)),
    )


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
    if provider in {"typesafe", "jev", "jeff"}:
        spirits = getattr(slot, "council_spirits", None)
        if spirits:
            voters = []
            for spirit in spirits:
                kwargs = _typesafe_kwargs(slot, transport)
                kwargs["spirit"] = spirit
                kwargs["duplicate_board"] = False
                voters.append(TypesafeAdapter(**kwargs))
            return JeffCouncilAdapter(voters)
        return TypesafeAdapter(**_typesafe_kwargs(slot, transport))
    raise ValueError(f"unsupported provider '{slot.provider}'")


def build_adapter_for_pack(slot: SlotConfig, transport: TransportFn, pack, *, stub_moves=None):
    """Build a Jeff/OpenAI adapter configured from a PromptPack."""
    from ...prompt_packs import PromptPack, load_pack

    if isinstance(pack, str):
        pack = load_pack(pack)
    if not isinstance(pack, PromptPack):
        return build_adapter(slot, transport, stub_moves=stub_moves)

    # Copy slot-like overrides via a simple namespace
    class _Slot:
        pass

    s = _Slot()
    for attr in (
        "provider",
        "base_url",
        "provider_model",
        "env_key",
        "observation",
        "jpeg_max_side",
    ):
        setattr(s, attr, getattr(slot, attr))
    s.spirit = (pack.body or '').replace('\ufeff', '').strip() or None
    s.duplicate_board = bool(pack.duplicate_board)
    s.council_spirits = None
    if pack.kind == "jeff_council":
        seat_ids = pack.seat_packs or ()
        s.council_spirits = [load_pack(pid).body.strip() for pid in seat_ids]
        s.duplicate_board = False
    if pack.observation:
        s.observation = pack.observation
    base = build_adapter(s, transport, stub_moves=stub_moves)
    if pack.kind == "jeff_phase":
        return JeffPhaseAdapter(base)
    if pack.kind == "jeff_checklist":
        return JeffChecklistAdapter(base)
    if pack.kind == "jeff_imagine":
        return JeffImagineAdapter(base)
    return base
