"""Unit tests for ApiKeyStore."""

import hashlib
import json

import pytest

from chess_harness.api_keys import ApiKeyStore


def test_create_and_verify_roundtrip(tmp_path):
    path = tmp_path / "api_keys.json"
    store = ApiKeyStore(path)
    raw = store.create("agent-a")
    assert store.verify(raw) == "agent-a"
    assert store.verify("wrong-key") is None

    data = json.loads(path.read_text(encoding="utf-8"))
    entry = data["keys"][0]
    assert entry["model_id"] == "agent-a"
    assert entry["key_prefix"] == raw[:8]
    assert entry["key_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in path.read_text(encoding="utf-8")


def test_verify_empty_key(tmp_path):
    store = ApiKeyStore(tmp_path / "api_keys.json")
    assert store.verify("") is None


def test_corrupt_store_fails_closed_without_overwrite(tmp_path):
    path = tmp_path / "api_keys.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError):
        ApiKeyStore(path)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_independent_stores_do_not_lose_keys(tmp_path):
    path = tmp_path / "api_keys.json"
    first = ApiKeyStore(path)
    second = ApiKeyStore(path)
    key_a = first.create("agent-a")
    key_b = second.create("agent-b")
    combined = ApiKeyStore(path)
    assert combined.verify(key_a) == "agent-a"
    assert combined.verify(key_b) == "agent-b"
