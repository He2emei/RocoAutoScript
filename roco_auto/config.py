from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data


@dataclass(frozen=True)
class Config:
    path: Path
    data: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        cfg_path = Path(path) if path else DEFAULT_CONFIG
        example = ROOT / "config.example.yaml"
        data = _load_yaml(example)
        if cfg_path.exists():
            data = _deep_merge(data, _load_yaml(cfg_path))
        return cls(path=cfg_path, data=data)

    def get(self, dotted: str, default: Any = None) -> Any:
        current: Any = self.data
        for part in dotted.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    @property
    def base_size(self) -> tuple[int, int]:
        return int(self.get("vision.base_width", 2048)), int(self.get("vision.base_height", 1152))

    def region(self, name: str) -> tuple[float, float, float, float]:
        value = self.get(f"regions.{name}")
        if not value or len(value) != 4:
            raise KeyError(f"Missing region: {name}")
        return tuple(float(v) for v in value)

    def point(self, name: str) -> tuple[float, float]:
        value = self.get(f"tap_points.{name}")
        if not value or len(value) != 2:
            raise KeyError(f"Missing tap point: {name}")
        return float(value[0]), float(value[1])
