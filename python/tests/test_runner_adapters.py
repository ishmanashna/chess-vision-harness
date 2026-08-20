"""Unit tests for runner provider adapters."""

from __future__ import annotations

import io
import json
from typing import Dict, Optional, Tuple

import chess
import pytest
from PIL import Image

from chess_harness.board_text import format_board_text
from chess_harness.render_pillow import ChessBoardRenderer
from chess_harness.runner.adapters.images import compress_png_for_provider, png_to_jpeg_data_url
from chess_harness.runner.adapters.openai import OpenAIAdapter, parse_move_from_text
from chess_harness.runner.config import SlotConfig


def test_parse_move_from_text():
    assert parse_move_from_text("I'll play e2e4 today") == "e2e4"
    assert parse_move_from_text("garbage") == "garbage"


def test_jpeg_downscale_smaller_than_source():
    png = ChessBoardRenderer().render_board_bytes(chess.Board())
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    jpeg = compress_png_for_provider(png, max_side=128, quality=80)
    assert jpeg.startswith(b"\xff\xd8")
    assert len(jpeg) < len(png)
    with Image.open(io.BytesIO(jpeg)) as img:
        assert max(img.size) <= 128


def test_png_to_jpeg_data_url_prefix():
    png = ChessBoardRenderer().render_board_bytes(chess.Board())
    url = png_to_jpeg_data_url(png, max_side=96)
    assert url.startswith("data:image/jpeg;base64,")


def test_openai_adapter_against_fake_chat_endpoint(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    board_text = format_board_text(chess.Board())
    calls: Dict[str, int] = {"count": 0}

    def fake_transport(
        method: str,
        url: str,
        headers,
        body: Optional[bytes] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        calls["count"] += 1
        assert method.upper() == "POST"
        assert url.endswith("/chat/completions")
        assert headers.get("Authorization") == "Bearer test-key"
        payload = json.loads(body.decode("utf-8"))
        assert payload["model"] == "fake-model"
        messages = payload["messages"]
        user = messages[-1]["content"]
        assert "side_to_move" in user
        response = {
            "choices": [{"message": {"content": "Best move: e2e4"}}],
        }
        return 200, {}, json.dumps(response).encode("utf-8")

    slot = SlotConfig(
        inscribed_id="openai-test",
        provider="openai",
        observation="text",
        provider_model="fake-model",
        base_url="http://fake.local/v1",
        env_key="OPENAI_API_KEY",
        rpm=30,
        rpd=200,
    )
    adapter = OpenAIAdapter(
        base_url=slot.base_url,
        model=slot.provider_model,
        env_key=slot.env_key,
        observation=slot.observation,
        transport=fake_transport,
    )
    move = adapter.choose_move(board_text=board_text, board_png=None)
    assert move == "e2e4"
    adapter.probe(board_text=board_text, board_png=None)
    assert calls["count"] == 2


def test_openai_vision_sends_jpeg_data_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    board_text = format_board_text(chess.Board())
    png = ChessBoardRenderer().render_board_bytes(chess.Board())
    seen: Dict[str, bool] = {"jpeg": False}

    def fake_transport(method, url, headers, body=None):
        payload = json.loads(body.decode("utf-8"))
        user = payload["messages"][-1]["content"]
        assert isinstance(user, list)
        image_part = next(part for part in user if part.get("type") == "image_url")
        url_value = image_part["image_url"]["url"]
        seen["jpeg"] = url_value.startswith("data:image/jpeg;base64,")
        response = {"choices": [{"message": {"content": "g1f3"}}]}
        return 200, {}, json.dumps(response).encode("utf-8")

    adapter = OpenAIAdapter(
        base_url="http://fake.local/v1",
        model="vision-model",
        env_key="OPENAI_API_KEY",
        observation="vision",
        transport=fake_transport,
        jpeg_max_side=160,
    )
    move = adapter.choose_move(board_text=board_text, board_png=png)
    assert move == "g1f3"
    assert seen["jpeg"] is True
