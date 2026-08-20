"""Inscribed model registry for standardized agent identities."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import project_root, resolve_base_dir, resolve_models_file

_MODEL_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

AGENT_START_ELO = 500

OBSERVATION_VISION = "vision"
OBSERVATION_TEXT = "text"
_VALID_OBSERVATIONS = frozenset({OBSERVATION_VISION, OBSERVATION_TEXT})


def normalize_observation(value: Any) -> str:
    """Default missing/legacy values to vision."""
    if value == OBSERVATION_TEXT:
        return OBSERVATION_TEXT
    return OBSERVATION_VISION


def validate_observation(value: Optional[str]) -> str:
    """Parse inscription/API observation; raise ValueError when invalid."""
    if value is None or not str(value).strip():
        return OBSERVATION_VISION
    obs = str(value).strip().lower()
    if obs not in _VALID_OBSERVATIONS:
        raise ValueError(
            f"observation must be '{OBSERVATION_VISION}' or '{OBSERVATION_TEXT}'"
        )
    return obs

# Legacy free-text names -> canonical inscribed id
MODEL_ALIASES: Dict[str, str] = {
    "Composer 2.5": "composer-2.5",
    "composer 2.5": "composer-2.5",
    "mimo-v2.5": "mimo-v2.5",
}


class ModelRegistry:
    """Manages inscribed models and their ELO ratings (stored together in models.json)."""

    def __init__(self, models_file: Optional[Path] = None):
        self.models_file = models_file or resolve_models_file()
        self._data = self._load()
        self._migrate_legacy_elo_file()

    def _load(self) -> Dict[str, Any]:
        if not self.models_file.exists():
            return {"models": []}
        try:
            return json.loads(self.models_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"models": []}

    def _reload(self) -> None:
        """Re-read models.json so long-lived registries see web/CLI inscriptions."""
        self._data = self._load()

    def _save(self) -> None:
        self.models_file.parent.mkdir(parents=True, exist_ok=True)
        self.models_file.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")

    def _migrate_legacy_elo_file(self) -> None:
        """One-time import from deprecated .chess_harness/elo.json into model entries."""
        if self.models_file != resolve_models_file():
            return

        legacy_ratings: Dict[str, float] = {}
        legacy_path = resolve_base_dir() / "elo.json"
        if legacy_path.exists():
            try:
                legacy_ratings = json.loads(legacy_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                legacy_ratings = {}

        changed = False
        for model in self._data.get("models", []):
            model_id = model.get("id")
            if model_id and "elo" not in model:
                model["elo"] = round(
                    float(legacy_ratings.get(model_id, AGENT_START_ELO)), 1
                )
                changed = True
            elif model_id and "elo" in model:
                model["elo"] = round(float(model["elo"]), 1)

        if changed:
            self._save()

    def list_models(self) -> List[Dict[str, Any]]:
        self._reload()
        return list(self._data.get("models", []))

    def list_ids(self) -> List[str]:
        return [m["id"] for m in self.list_models()]

    def get(self, model_id: str) -> Optional[Dict[str, Any]]:
        for model in self.list_models():
            if model["id"] == model_id:
                return model
        return None

    def display_name(self, model_id: str) -> str:
        model = self.get(model_id)
        return model["name"] if model else model_id

    def get_elo(self, model_id: str) -> float:
        model = self.get(model_id)
        if not model:
            return float(AGENT_START_ELO)
        return float(model.get("elo", AGENT_START_ELO))

    def set_elo(self, model_id: str, elo: float) -> None:
        self._reload()
        for model in self._data.get("models", []):
            if model["id"] == model_id:
                model["elo"] = round(elo, 1)
                self._save()
                return

    def reset_all_elo(self, elo: float = AGENT_START_ELO) -> None:
        self._reload()
        for model in self._data.get("models", []):
            model["elo"] = round(elo, 1)
        self._save()

    def validate_id_format(self, model_id: str) -> bool:
        return bool(_MODEL_ID_PATTERN.match(model_id))

    def is_inscribed(self, model_id: str) -> bool:
        return self.get(model_id) is not None

    def is_enabled(self, model_id: str) -> bool:
        model = self.get(model_id)
        return bool(model.get("enabled", True)) if model else False

    def set_enabled(self, model_id: str, enabled: bool) -> Dict[str, Any]:
        self._reload()
        for entry in self._data.get("models", []):
            if entry["id"] != model_id:
                continue
            if enabled:
                entry.pop("enabled", None)
            else:
                entry["enabled"] = False
            self._save()
            return dict(entry)
        raise ValueError(f"Model '{model_id}' is not inscribed")

    def observation_for(self, model_id: str) -> str:
        model = self.get(model_id)
        if not model:
            return OBSERVATION_VISION
        return normalize_observation(model.get("observation"))

    def inscribe(
        self,
        model_id: str,
        name: Optional[str] = None,
        *,
        observation: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.validate_id_format(model_id):
            raise ValueError(
                f"Invalid model id '{model_id}'. Use letters, numbers, dots, dashes, underscores."
            )
        self._reload()
        if self.is_inscribed(model_id):
            raise ValueError(f"Model '{model_id}' is already inscribed")

        entry: Dict[str, Any] = {
            "id": model_id,
            "name": name or model_id,
            "inscribed": date.today().isoformat(),
            "elo": AGENT_START_ELO,
            "observation": validate_observation(observation),
        }
        self._data.setdefault("models", []).append(entry)
        self._save()
        return entry

    def uninscribe(self, model_id: str) -> Dict[str, Any]:
        self._reload()
        if not self.is_inscribed(model_id):
            raise ValueError(f"Model '{model_id}' is not inscribed")

        entry = self.get(model_id)
        assert entry is not None
        self._data["models"] = [m for m in self._data.get("models", []) if m["id"] != model_id]
        self._save()
        return entry

    def clear_all(self) -> None:
        self._data = {"models": []}
        self._save()

    def resolve(self, model_ref: Optional[str]) -> str:
        """Resolve id or legacy alias/name to canonical inscribed model id."""
        if not model_ref or not str(model_ref).strip():
            raise ValueError(self._missing_model_message())

        ref = str(model_ref).strip()

        if ref in MODEL_ALIASES:
            ref = MODEL_ALIASES[ref]

        if self.is_inscribed(ref):
            if not self.is_enabled(ref):
                raise ValueError(
                    f"Model '{ref}' is disabled. "
                    "Enable with: chess-harness models enable <id>"
                )
            return ref

        for model in self.list_models():
            if model.get("name", "").lower() == ref.lower():
                if not model.get("enabled", True):
                    raise ValueError(
                        f"Model '{ref}' is disabled. "
                        "Enable with: chess-harness models enable <id>"
                    )
                return model["id"]

        raise ValueError(self._unknown_model_message(ref))

    def normalize_result_model(self, model_name: Optional[str]) -> Optional[str]:
        """Map stored/legacy model_name to canonical id, or None if not inscribed."""
        if not model_name:
            return None
        try:
            return self.resolve(model_name)
        except ValueError:
            return None

    def _missing_model_message(self) -> str:
        ids = ", ".join(self.list_ids()) or "(none — run: chess-harness models inscribe <id>)"
        return (
            "A inscribed model is required. Use --model <id>.\n"
            f"Inscribed models: {ids}\n"
            "List models: chess-harness models list"
        )

    def _unknown_model_message(self, ref: str) -> str:
        ids = ", ".join(self.list_ids()) or "(none)"
        return (
            f"Unknown model '{ref}'. Must be an inscribed model id.\n"
            f"Inscribed models: {ids}\n"
            "Inscribe new: chess-harness models inscribe <id> --name \"Display Name\""
        )


def format_model_list(registry: ModelRegistry) -> str:
    models = registry.list_models()
    if not models:
        return "No inscribed models. Run: chess-harness models inscribe <id> --name \"Name\""
    lines = ["Inscribed models:"]
    for model in models:
        elo = model.get("elo", AGENT_START_ELO)
        disabled = "" if model.get("enabled", True) else " [disabled]"
        obs = normalize_observation(model.get("observation"))
        obs_mark = " [text]" if obs == OBSERVATION_TEXT else ""
        lines.append(
            f"  {model['id']}: {model.get('name', model['id'])} ({round(elo)} ELO){obs_mark}{disabled}"
        )
    return "\n".join(lines)
