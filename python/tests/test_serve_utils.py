"""Tests for spectator port management."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.serve_utils import (
    ensure_port_available,
    is_port_in_use,
    read_spectator_meta,
    remove_spectator_meta,
    write_spectator_meta,
)


def test_port_check_localhost():
    assert is_port_in_use("127.0.0.1", 1) is False


def test_ensure_port_raises_with_hint(monkeypatch):
    monkeypatch.setattr(
        "chess_harness.serve_utils.is_port_in_use", lambda host, port: True
    )
    monkeypatch.setattr(
        "chess_harness.serve_utils.find_pids_on_port", lambda port: [12345]
    )
    with pytest.raises(RuntimeError, match="serve stop"):
        ensure_port_available("127.0.0.1", 8765, force=False)


def test_spectator_meta_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "chess_harness.serve_utils.resolve_base_dir", lambda: tmp_path / "harness"
    )
    write_spectator_meta("127.0.0.1", 8765)
    meta = read_spectator_meta()
    assert meta is not None
    assert meta["port"] == 8765
    assert meta["host"] == "127.0.0.1"
    remove_spectator_meta()
    assert read_spectator_meta() is None
