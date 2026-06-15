from __future__ import annotations

import logging
import time
from pathlib import Path

from .adb import AdbDevice
from .config import Config
from .geometry import random_near
from .stats import RewardStats
from .vision import (
    SCENE_CONFIRM,
    SCENE_BATTLE,
    SCENE_FRIENDS,
    SCENE_LOADING,
    SCENE_MENU,
    SCENE_NORMAL,
    SCENE_RESULT,
    SCENE_SLEEP,
    SCENE_SIDE_PANEL,
    Vision,
    image_from_png,
)


LOGGER = logging.getLogger("roco_auto")
SCENE_BATTLE_TRANSITION = "battle_transition"
SCENE_NO_WATCH_TARGET = "no_watch_target"


class SpectatorBot:
    def __init__(self, config: Config, device: AdbDevice, dry_run: bool = False) -> None:
        self.config = config
        self.device = device
        self.vision = Vision(config)
        self.dry_run = dry_run
        self.swipes_on_current_tab = 0
        self.tab_index = 0
        self.entered_friends = False
        self.needs_list_reset = False
        self.last_battle_seen_at = 0.0
        self.reward_stats = RewardStats(config)
        self.last_reward_amount: int | None = None
        self.last_reward_recorded_at = 0.0

    @property
    def tabs(self) -> list[str]:
        return ["friend_tab_game", "friend_tab_qq"]

    def _move_to_next_friend_tab(self) -> bool:
        if self.tab_index + 1 >= len(self.tabs):
            self.tab_index = 0
            self.entered_friends = False
            self.needs_list_reset = True
            self.swipes_on_current_tab = 0
            return False
        self.tab_index += 1
        self.entered_friends = False
        self.needs_list_reset = False
        self.swipes_on_current_tab = 0
        return True

    def _tap_point(self, name: str, radius: int = 4) -> None:
        image = getattr(self, "_last_image", None)
        if image is None:
            raise RuntimeError("No screenshot available for scaling tap point.")
        point = self.vision.scaler(image).point(self.config.point(name))
        point = random_near(point, radius=radius)
        LOGGER.info("tap %s @ %s", name, point)
        if not self.dry_run:
            self.device.tap(*point)

    def _tap_xy(self, x: int, y: int, name: str) -> None:
        x, y = random_near((x, y), radius=5)
        LOGGER.info("tap %s @ (%s, %s)", name, x, y)
        if not self.dry_run:
            self.device.tap(x, y)

    def _swipe_list(self) -> None:
        image = getattr(self, "_last_image", None)
        if image is None:
            raise RuntimeError("No screenshot available for scaling swipe.")
        scaler = self.vision.scaler(image)
        if self.config.get("swipe.use_row_distance", True):
            x = scaler.x(float(self.config.get("swipe.list_x", 1120)))
            start_y = scaler.y(float(self.config.get("swipe.start_y", 1000)))
            row_gap = scaler.y(float(self.config.get("friend_list.row_gap", 150)))
            rows = float(self.config.get("swipe.rows_per_page", self.config.get("friend_list.visible_rows", 6)))
            distance = round(row_gap * rows)
            min_end_y = scaler.y(float(self.config.get("swipe.min_end_y", 100)))
            end_y = max(min_end_y, start_y - distance)
            start = (x, start_y)
            end = (x, end_y)
        else:
            start = scaler.point(tuple(self.config.get("swipe.list_start", [1120, 900])))
            end = scaler.point(tuple(self.config.get("swipe.list_end", [1120, 310])))
        duration = int(self.config.get("swipe.duration_ms", 550))
        LOGGER.info("swipe friend list %s -> %s duration=%sms", start, end, duration)
        if not self.dry_run:
            self.device.swipe(start, end, duration)

    def _save_screenshot_if_needed(self, image) -> None:
        if not self.config.get("runtime.save_screenshots", False):
            return
        folder = Path(self.config.get("runtime.screenshot_dir", "debug/screenshots"))
        folder.mkdir(parents=True, exist_ok=True)
        image.save(folder / f"{int(time.time())}.png")

    def _record_reward_if_needed(self, image) -> None:
        if not self.reward_stats.enabled:
            return
        reward = self.vision.extract_reward_coins(image)
        duplicate_window = float(self.config.get("stats.duplicate_window_seconds", 20))
        now = time.time()
        if reward.amount is None:
            path = self.reward_stats.save_unresolved_crop(image, reward.box, reward.text)
            LOGGER.warning("reward OCR failed: text=%r confidence=%.3f crop=%s", reward.text, reward.confidence, path)
            return
        if self.last_reward_amount == reward.amount and now - self.last_reward_recorded_at < duplicate_window:
            LOGGER.info("skip duplicate reward: amount=%s", reward.amount)
            return
        event = self.reward_stats.record(reward.amount, reward.confidence, reward.text, image.size)
        self.last_reward_amount = reward.amount
        self.last_reward_recorded_at = now
        summary = self.reward_stats.summary()
        LOGGER.info(
            "reward recorded: amount=%s confidence=%.3f battles=%s coins=%s",
            event.amount,
            event.confidence,
            summary.get("battles"),
            summary.get("coins"),
        )

    def step(self) -> str:
        image = image_from_png(self.device.screenshot_png())
        self._last_image = image
        self._save_screenshot_if_needed(image)
        diagnosis = self.vision.diagnose(image)
        LOGGER.info("scene=%s targets=%s notes=%s", diagnosis.scene, len(diagnosis.targets), "; ".join(diagnosis.notes))

        if diagnosis.scene == SCENE_RESULT:
            self._record_reward_if_needed(image)
            self._tap_point("result_exit", radius=30)
            self.entered_friends = False
            self.swipes_on_current_tab = 0
            self.needs_list_reset = False
            self.last_battle_seen_at = 0.0
            return diagnosis.scene

        if diagnosis.scene == SCENE_SLEEP:
            self._tap_point("wake_screen", radius=50)
            self.entered_friends = False
            self.needs_list_reset = False
            return diagnosis.scene

        if diagnosis.scene == SCENE_SIDE_PANEL:
            self._tap_point("close_top_right", radius=8)
            self.entered_friends = False
            self.needs_list_reset = False
            return diagnosis.scene

        if diagnosis.scene == SCENE_CONFIRM:
            self._tap_point("confirm_watch", radius=8)
            self.entered_friends = False
            self.swipes_on_current_tab = 0
            self.needs_list_reset = False
            return diagnosis.scene

        if diagnosis.scene == SCENE_FRIENDS:
            if not self.entered_friends or self.needs_list_reset:
                self._tap_point(self.tabs[self.tab_index], radius=8)
                self.entered_friends = True
                self.swipes_on_current_tab = 0
                self.needs_list_reset = False
                return diagnosis.scene

            if diagnosis.targets:
                target = diagnosis.targets[0]
                LOGGER.info("watch target row=%s reason=%s", target.row_index + 1 if target.row_index >= 0 else "-", target.reason)
                self._tap_xy(target.x, target.y, "watch_button")
                return diagnosis.scene

            if diagnosis.offline_tail:
                if self._move_to_next_friend_tab():
                    LOGGER.info("offline tail reached; switch to %s", self.tabs[self.tab_index])
                    self._tap_point(self.tabs[self.tab_index], radius=8)
                    self.entered_friends = True
                    return diagnosis.scene
                LOGGER.info("offline tail reached on last friend tab; wait before rescan")
                return SCENE_NO_WATCH_TARGET

            max_swipes = int(self.config.get("runtime.max_swipes_per_tab", 4))
            if self.swipes_on_current_tab < max_swipes:
                self.swipes_on_current_tab += 1
                LOGGER.info("no watchable friend target on current rows; swipe page %s/%s", self.swipes_on_current_tab, max_swipes)
                self._swipe_list()
                return diagnosis.scene

            if self._move_to_next_friend_tab():
                LOGGER.info("no watchable friend target after %s swipes; switch to %s", max_swipes, self.tabs[self.tab_index])
                self._tap_point(self.tabs[self.tab_index], radius=8)
                self.entered_friends = True
                return diagnosis.scene

            LOGGER.info("no watchable friend target after %s swipes on all tabs; wait before rescan", max_swipes)
            return SCENE_NO_WATCH_TARGET

        if diagnosis.scene == SCENE_MENU:
            self._tap_point("menu_friend", radius=10)
            self.entered_friends = False
            self.needs_list_reset = False
            return diagnosis.scene

        if diagnosis.scene == SCENE_NORMAL:
            grace = float(self.config.get("runtime.post_battle_grace_seconds", 180))
            if self.last_battle_seen_at and time.time() - self.last_battle_seen_at < grace:
                LOGGER.info("recent battle scene; wait for result page")
                return SCENE_BATTLE_TRANSITION
            self._tap_point("open_menu", radius=8)
            self.entered_friends = False
            self.needs_list_reset = False
            return diagnosis.scene

        if diagnosis.scene == SCENE_BATTLE:
            self.last_battle_seen_at = time.time()
            LOGGER.info("battle/spectator scene; wait")
            return diagnosis.scene

        if diagnosis.scene == SCENE_LOADING:
            LOGGER.info("game is loading/downloading; wait")
            return diagnosis.scene

        LOGGER.info("unknown scene; wait")
        return diagnosis.scene

    def run_forever(self, interval_seconds: float) -> None:
        LOGGER.info("bot started: interval=%ss dry_run=%s", interval_seconds, self.dry_run)
        while True:
            try:
                scene = self.step()
            except KeyboardInterrupt:
                raise
            except Exception:
                LOGGER.exception("step failed")
                scene = "error"

            delay = float(self.config.get("runtime.post_action_delay_seconds", 2.0))
            if scene in {SCENE_LOADING, SCENE_BATTLE, SCENE_BATTLE_TRANSITION, SCENE_NO_WATCH_TARGET, "unknown", "error"}:
                delay = interval_seconds
            time.sleep(max(delay, 0.1))
