from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Config, ROOT


@dataclass(frozen=True)
class RewardEvent:
    timestamp: str
    amount: int
    confidence: float
    text: str
    image_size: tuple[int, int]


class RewardStats:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.events_file = self._path("stats.events_file", "stats/rewards.jsonl")
        self.summary_file = self._path("stats.summary_file", "stats/summary.json")
        self.unresolved_dir = self._path("stats.unresolved_dir", "debug/reward_unresolved")

    @staticmethod
    def _resolve(value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return ROOT / path

    def _path(self, key: str, default: str) -> Path:
        return self._resolve(str(self.config.get(key, default)))

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("stats.enabled", True))

    def record(self, amount: int, confidence: float, text: str, image_size: tuple[int, int]) -> RewardEvent:
        event = RewardEvent(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            amount=amount,
            confidence=round(confidence, 4),
            text=text,
            image_size=image_size,
        )
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.__dict__, ensure_ascii=False) + "\n")

        summary = self.summary()
        summary["battles"] = int(summary.get("battles", 0)) + 1
        summary["coins"] = int(summary.get("coins", 0)) + amount
        summary["last_amount"] = amount
        summary["last_timestamp"] = event.timestamp
        self.summary_file.parent.mkdir(parents=True, exist_ok=True)
        with self.summary_file.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return event

    def save_unresolved_crop(self, image, box: tuple[int, int, int, int], text: str) -> Path:
        self.unresolved_dir.mkdir(parents=True, exist_ok=True)
        safe_text = text.replace("?", "unknown") or "empty"
        path = self.unresolved_dir / f"reward_{int(time.time())}_{safe_text}.png"
        image.crop(box).save(path)
        return path

    def summary(self) -> dict[str, Any]:
        if not self.summary_file.exists():
            return {"battles": 0, "coins": 0}
        try:
            with self.summary_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                data.setdefault("battles", 0)
                data.setdefault("coins", 0)
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"battles": 0, "coins": 0}
