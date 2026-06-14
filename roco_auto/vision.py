from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from time import time

import numpy as np
from PIL import Image, ImageDraw

from .config import Config, ROOT
from .geometry import Scaler


SCENE_NORMAL = "normal"
SCENE_MENU = "menu"
SCENE_FRIENDS = "friends"
SCENE_CONFIRM = "confirm_watch"
SCENE_RESULT = "battle_result"
SCENE_BATTLE = "battle"
SCENE_LOADING = "loading"
SCENE_SIDE_PANEL = "side_panel"
SCENE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class WatchTarget:
    y: int
    x: int
    green_pixels: int
    width: int
    box: tuple[int, int, int, int]


@dataclass(frozen=True)
class Diagnosis:
    scene: str
    targets: list[WatchTarget]
    image_size: tuple[int, int]
    notes: list[str]


@dataclass(frozen=True)
class TemplateHit:
    scene: str
    name: str
    score: float
    threshold: float
    box: tuple[int, int, int, int]
    template_size: tuple[int, int] = (0, 0)


def image_from_png(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data)).convert("RGB")


def image_from_file(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


class Vision:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._template_cache: dict[tuple[str, int, int], np.ndarray] = {}

    def scaler(self, image: Image.Image) -> Scaler:
        base_width, base_height = self.config.base_size
        return Scaler(base_width, base_height, image.width, image.height)

    @staticmethod
    def _crop_array(image: Image.Image, box: tuple[int, int, int, int]) -> np.ndarray:
        box = (
            max(0, box[0]),
            max(0, box[1]),
            min(image.width, box[2]),
            min(image.height, box[3]),
        )
        return np.asarray(image.crop(box), dtype=np.float32)

    @staticmethod
    def _gray_array(image: Image.Image) -> np.ndarray:
        return np.asarray(image.convert("L"), dtype=np.float32)

    @staticmethod
    def _box_from_config(scaler: Scaler, value: list[float] | tuple[float, float, float, float]) -> tuple[int, int, int, int]:
        return scaler.box(tuple(float(v) for v in value))

    @staticmethod
    def _brightness(arr: np.ndarray) -> float:
        if arr.size == 0:
            return 0.0
        return float(arr.mean())

    @staticmethod
    def _yellow_ratio(arr: np.ndarray) -> float:
        if arr.size == 0:
            return 0.0
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        mask = (r > 180) & (g > 135) & (b < 95) & ((r - b) > 80)
        return float(mask.mean())

    @staticmethod
    def _red_ratio(arr: np.ndarray) -> float:
        if arr.size == 0:
            return 0.0
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        mask = (r > 140) & (g < 115) & (b < 115) & ((r - g) > 35) & ((r - b) > 35)
        return float(mask.mean())

    @staticmethod
    def _loose_green_ratio(arr: np.ndarray) -> float:
        if arr.size == 0:
            return 0.0
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        mask = (g > 100) & (g > r * 1.15) & (g > b * 1.15)
        return float(mask.mean())

    @staticmethod
    def _battle_green_ratio(arr: np.ndarray) -> float:
        if arr.size == 0:
            return 0.0
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        mask = (g > 135) & (r < 125) & (b < 125) & ((g - r) > 45) & ((g - b) > 45)
        return float(mask.mean())

    @staticmethod
    def _white_ratio(arr: np.ndarray) -> float:
        if arr.size == 0:
            return 0.0
        mask = (arr[..., 0] > 220) & (arr[..., 1] > 220) & (arr[..., 2] > 210)
        return float(mask.mean())

    @staticmethod
    def _dark_ratio(arr: np.ndarray) -> float:
        if arr.size == 0:
            return 0.0
        mask = (arr[..., 0] < 55) & (arr[..., 1] < 55) & (arr[..., 2] < 55)
        return float(mask.mean())

    def _green_mask(self, arr: np.ndarray) -> np.ndarray:
        threshold = self.config.get("vision.green_threshold", {})
        min_g = float(threshold.get("min_g", 105))
        g_over_r = float(threshold.get("g_over_r", 1.25))
        g_over_b = float(threshold.get("g_over_b", 1.45))
        min_g_minus_r = float(threshold.get("min_g_minus_r", 28))
        min_g_minus_b = float(threshold.get("min_g_minus_b", 42))
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        return (
            (g >= min_g)
            & (g >= r * g_over_r)
            & (g >= b * g_over_b)
            & ((g - r) >= min_g_minus_r)
            & ((g - b) >= min_g_minus_b)
        )

    @staticmethod
    def _integral_sum(integral: np.ndarray, height: int, width: int) -> np.ndarray:
        return integral[height:, width:] - integral[:-height, width:] - integral[height:, :-width] + integral[:-height, :-width]

    @staticmethod
    def _fft_valid_correlation(search: np.ndarray, kernel: np.ndarray) -> np.ndarray:
        sh, sw = search.shape
        kh, kw = kernel.shape
        shape = (sh + kh - 1, sw + kw - 1)
        spectrum = np.fft.rfft2(search, shape) * np.fft.rfft2(np.flipud(np.fliplr(kernel)), shape)
        corr = np.fft.irfft2(spectrum, shape)
        return corr[kh - 1 : sh, kw - 1 : sw]

    def _template_array(self, file_name: str, width: int, height: int) -> np.ndarray:
        key = (file_name, width, height)
        cached = self._template_cache.get(key)
        if cached is not None:
            return cached

        path = Path(file_name)
        if not path.is_absolute():
            path = ROOT / path
        image = Image.open(path).convert("RGB")
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        arr = self._gray_array(image)
        self._template_cache[key] = arr
        return arr

    def _template_rgb(self, file_name: str, width: int, height: int) -> Image.Image:
        path = Path(file_name)
        if not path.is_absolute():
            path = ROOT / path
        image = Image.open(path).convert("RGB")
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        return image

    def _template_score_map(
        self, image: Image.Image, template: dict, scaler: Scaler
    ) -> tuple[np.ndarray | None, tuple[int, int, int, int], tuple[int, int]]:
        region = self._box_from_config(scaler, template["region"])
        search = self._gray_array(image.crop(region))
        sx, sy = scaler.sx, scaler.sy
        file_name = str(template["file"])
        base_template = Image.open((ROOT / file_name) if not Path(file_name).is_absolute() else file_name)
        width = max(8, round(base_template.width * sx))
        height = max(8, round(base_template.height * sy))
        if search.shape[0] < height or search.shape[1] < width:
            return None, region, (width, height)

        tpl = self._template_array(file_name, width, height)
        tpl = tpl - float(tpl.mean())
        tpl_norm_sq = float(np.square(tpl).sum())
        if tpl_norm_sq < 1e-6:
            return None, region, (width, height)

        numerator = self._fft_valid_correlation(search, tpl)
        padded = np.pad(search, ((1, 0), (1, 0)), mode="constant")
        integral = padded.cumsum(axis=0).cumsum(axis=1)
        padded_sq = np.pad(np.square(search), ((1, 0), (1, 0)), mode="constant")
        integral_sq = padded_sq.cumsum(axis=0).cumsum(axis=1)
        local_sum = self._integral_sum(integral, height, width)
        local_sum_sq = self._integral_sum(integral_sq, height, width)
        n = float(width * height)
        local_var = np.maximum(local_sum_sq - np.square(local_sum) / n, 1e-6)
        score_map = numerator / np.sqrt(local_var * tpl_norm_sq)
        return score_map, region, (width, height)

    def _template_score(self, image: Image.Image, template: dict, scaler: Scaler) -> tuple[float, tuple[int, int, int, int], tuple[int, int]]:
        score_map, region, template_size = self._template_score_map(image, template, scaler)
        if score_map is None:
            return -1.0, region, template_size
        score = float(np.nanmax(score_map))
        return score, region, template_size

    def _template_hits(self, image: Image.Image, scene: str) -> list[TemplateHit]:
        scaler = self.scaler(image)
        hits: list[TemplateHit] = []
        for index, template in enumerate(self.config.get(f"templates.{scene}", []) or []):
            score, box, template_size = self._template_score(image, template, scaler)
            name = Path(str(template["file"])).stem or f"{scene}_{index}"
            hits.append(
                TemplateHit(
                    scene=scene,
                    name=name,
                    score=score,
                    threshold=float(template.get("threshold", 0.7)),
                    box=box,
                    template_size=template_size,
                )
            )
        return hits

    def _template_best(self, image: Image.Image, scene: str) -> TemplateHit | None:
        hits = self._template_hits(image, scene)
        if not hits:
            return None
        return max(hits, key=lambda hit: hit.score)

    def _template_matches(self, image: Image.Image, scene: str, notes: list[str]) -> bool:
        best = self._template_best(image, scene)
        if best is None:
            return False
        if self.config.get("vision.template_debug", True):
            notes.append(f"tpl_{scene}={best.score:.3f}:{best.name}")
        return best.score >= best.threshold

    def _template_target_hits(self, image: Image.Image, scene: str) -> list[TemplateHit]:
        if scene == "watch_status":
            return self._watch_status_hits(image)

        scaler = self.scaler(image)
        hits: list[TemplateHit] = []
        for index, template in enumerate(self.config.get(f"templates.{scene}", []) or []):
            score_map, region, template_size = self._template_score_map(image, template, scaler)
            if score_map is None:
                continue
            threshold = float(template.get("threshold", 0.7))
            ys, xs = np.where(score_map >= threshold)
            if xs.size == 0:
                continue

            order = np.argsort(score_map[ys, xs])[::-1]
            name = Path(str(template["file"])).stem or f"{scene}_{index}"
            width, height = template_size
            for pos in order:
                x = int(xs[pos])
                y = int(ys[pos])
                score = float(score_map[y, x])
                box = (region[0] + x, region[1] + y, region[0] + x + width, region[1] + y + height)
                if any(abs(((old.box[1] + old.box[3]) / 2) - ((box[1] + box[3]) / 2)) < height * 0.7 for old in hits):
                    continue
                hits.append(
                    TemplateHit(
                        scene=scene,
                        name=name,
                        score=score,
                        threshold=threshold,
                        box=box,
                        template_size=template_size,
                    )
                )
                break
        return sorted(hits, key=lambda hit: hit.score, reverse=True)

    def _watch_status_hits(self, image: Image.Image) -> list[TemplateHit]:
        scaler = self.scaler(image)
        hits: list[TemplateHit] = []
        for index, template in enumerate(self.config.get("templates.watch_status", []) or []):
            region = self._box_from_config(scaler, template["region"])
            search_arr = self._crop_array(image, region)
            search_mask = self._green_mask(search_arr).astype(np.float32)
            sx, sy = scaler.sx, scaler.sy
            file_name = str(template["file"])
            base_template = Image.open((ROOT / file_name) if not Path(file_name).is_absolute() else file_name)
            width = max(8, round(base_template.width * sx))
            height = max(8, round(base_template.height * sy))
            if search_mask.shape[0] < height or search_mask.shape[1] < width:
                continue

            tpl_arr = np.asarray(self._template_rgb(file_name, width, height), dtype=np.float32)
            tpl_mask = self._green_mask(tpl_arr).astype(np.float32)
            template_green = float(tpl_mask.sum())
            if template_green < 10:
                continue

            score_map = self._fft_valid_correlation(search_mask, tpl_mask) / template_green
            threshold = float(template.get("threshold", 0.62))
            ys, xs = np.where(score_map >= threshold)
            if xs.size == 0:
                continue

            order = np.argsort(score_map[ys, xs])[::-1]
            name = Path(file_name).stem or f"watch_status_{index}"
            for pos in order:
                x = int(xs[pos])
                y = int(ys[pos])
                score = float(score_map[y, x])
                box = (region[0] + x, region[1] + y, region[0] + x + width, region[1] + y + height)
                if any(abs(((old.box[1] + old.box[3]) / 2) - ((box[1] + box[3]) / 2)) < height * 0.7 for old in hits):
                    continue
                hits.append(
                    TemplateHit(
                        scene="watch_status",
                        name=name,
                        score=score,
                        threshold=threshold,
                        box=box,
                        template_size=(width, height),
                    )
                )
                break
        return sorted(hits, key=lambda hit: hit.score, reverse=True)

    def detect_scene(self, image: Image.Image) -> tuple[str, list[str]]:
        scaler = self.scaler(image)
        notes: list[str] = []

        if self._template_matches(image, "result", notes):
            return SCENE_RESULT, notes

        result_arr = self._crop_array(image, scaler.box(self.config.region("result_reward_banner")))
        yellow = self._yellow_ratio(result_arr)
        notes.append(f"result_yellow={yellow:.3f}")
        if yellow > 0.18:
            return SCENE_RESULT, notes

        screen_dark = self._dark_ratio(np.asarray(image, dtype=np.float32))
        notes.append(f"screen_dark={screen_dark:.3f}")
        if screen_dark > 0.75:
            return SCENE_LOADING, notes

        header_arr = self._crop_array(image, scaler.box(self.config.region("confirm_dialog_header")))
        dialog_arr = self._crop_array(image, scaler.box(self.config.region("confirm_dialog_body")))
        confirm_arr = self._crop_array(image, scaler.box(self.config.region("confirm_button")))
        header_dark = self._dark_ratio(header_arr)
        dialog_brightness = self._brightness(dialog_arr)
        confirm_brightness = self._brightness(confirm_arr)
        notes.append(f"dialog_header_dark={header_dark:.3f}")
        notes.append(f"dialog_brightness={dialog_brightness:.1f}")
        notes.append(f"confirm_brightness={confirm_brightness:.1f}")
        if self._template_matches(image, "confirm", notes) or (
            header_dark > 0.35 and dialog_brightness > 120 and confirm_brightness > 90
        ):
            return SCENE_CONFIRM, notes

        logo_arr = self._crop_array(image, scaler.box(self.config.region("loading_logo")))
        logo_white = self._white_ratio(logo_arr)
        notes.append(f"loading_logo_white={logo_white:.3f}")
        if logo_white > 0.25:
            return SCENE_LOADING, notes

        side_panel_arr = self._crop_array(image, scaler.box(self.config.region("right_side_panel")))
        side_panel_dark = self._dark_ratio(side_panel_arr)
        side_panel_white = self._white_ratio(side_panel_arr)
        notes.append(f"side_panel_dark={side_panel_dark:.3f}")
        notes.append(f"side_panel_white={side_panel_white:.3f}")
        if side_panel_dark > 0.72 and side_panel_white > 0.02:
            return SCENE_SIDE_PANEL, notes

        progress_arr = self._crop_array(image, scaler.box(self.config.region("loading_progress")))
        progress_white = self._white_ratio(progress_arr)
        notes.append(f"loading_white={progress_white:.3f}")
        if progress_white > 0.12 and screen_dark < 0.15:
            return SCENE_LOADING, notes

        minimap_arr = self._crop_array(image, scaler.box(self.config.region("minimap")))
        minimap_green = self._loose_green_ratio(minimap_arr)
        minimap_yellow = self._yellow_ratio(minimap_arr)
        minimap_red = self._red_ratio(minimap_arr)
        minimap_mean = self._brightness(minimap_arr)
        minimap_like = (minimap_yellow > 0.08) or (minimap_green > 0.10 and minimap_red < 0.025 and minimap_mean > 105)
        notes.append(f"minimap_green={minimap_green:.3f}")
        notes.append(f"minimap_yellow={minimap_yellow:.3f}")
        notes.append(f"minimap_red={minimap_red:.3f}")
        notes.append(f"minimap_like={int(minimap_like)}")

        left_hp = self._crop_array(image, scaler.box(self.config.region("battle_left_hp")))
        right_hp = self._crop_array(image, scaler.box(self.config.region("battle_right_hp")))
        bottom_controls = self._crop_array(image, scaler.box(self.config.region("battle_bottom_controls")))
        left_green = self._battle_green_ratio(left_hp)
        right_green = self._battle_green_ratio(right_hp)
        bottom_dark = self._dark_ratio(bottom_controls)
        bottom_white = self._white_ratio(bottom_controls)
        notes.append(f"battle_left_green={left_green:.3f}")
        notes.append(f"battle_right_green={right_green:.3f}")
        notes.append(f"battle_bottom_dark={bottom_dark:.3f}")
        notes.append(f"battle_bottom_white={bottom_white:.3f}")
        if self._template_matches(image, "battle", notes) or (not minimap_like and (
            (left_green > 0.025 and right_green > 0.025)
            or (right_green > 0.04 and bottom_dark > 0.15 and bottom_white > 0.05)
        )):
            return SCENE_BATTLE, notes

        friend_panel_arr = self._crop_array(image, scaler.box(self.config.region("friend_list_panel")))
        panel_brightness = self._brightness(friend_panel_arr)
        notes.append(f"friend_panel_brightness={panel_brightness:.1f}")
        targets = self.find_watch_targets(image)
        friends_template = self._template_matches(image, "friends", notes)
        if friends_template and (targets or panel_brightness < 110):
            notes.append(f"green_targets={len(targets)}")
            return SCENE_FRIENDS, notes

        if panel_brightness < 82 and image.width > image.height and not minimap_like:
            return SCENE_FRIENDS, notes

        menu_arr = self._crop_array(image, scaler.box(self.config.region("menu_left_panel")))
        menu_brightness = self._brightness(menu_arr)
        notes.append(f"menu_brightness={menu_brightness:.1f}")
        if self._template_matches(image, "menu", notes) or (
            menu_brightness < 70 and screen_dark > 0.05 and not minimap_like
        ):
            return SCENE_MENU, notes

        # Normal game UI is hard to prove without templates; defaulting to normal is useful because
        # the next safe action is simply opening the menu.
        if image.width > image.height:
            return SCENE_NORMAL, notes
        return SCENE_UNKNOWN, notes

    def find_watch_targets(self, image: Image.Image) -> list[WatchTarget]:
        scaler = self.scaler(image)
        status_hits = self._template_target_hits(image, "watch_status")
        if status_hits:
            target_x = scaler.x(float(self.config.get("tap_points.watch_button_x", 1715)))
            targets = [
                WatchTarget(
                    y=round((hit.box[1] + hit.box[3]) / 2),
                    x=target_x,
                    green_pixels=round(hit.score * 1000),
                    width=hit.box[2] - hit.box[0],
                    box=hit.box,
                )
                for hit in status_hits
            ]
            center = image.height / 2
            return sorted(targets, key=lambda item: abs(item.y - center))

        if not self.config.get("vision.green_status_fallback", False):
            return []

        box = scaler.box(self.config.region("friend_status_search"))
        arr = self._crop_array(image, box)
        mask = self._green_mask(arr)
        if mask.size == 0:
            return []

        row_counts = mask.sum(axis=1)
        min_pixels = max(8, int(float(self.config.get("vision.activity_min_green_pixels", 80)) * scaler.sx))
        active_rows = row_counts > min_pixels
        segments: list[tuple[int, int]] = []
        start: int | None = None
        gap = 0
        for idx, active in enumerate(active_rows):
            if active:
                if start is None:
                    start = idx
                gap = 0
            elif start is not None:
                gap += 1
                if gap > max(3, int(8 * scaler.sy)):
                    end = idx - gap
                    if end - start >= max(3, int(5 * scaler.sy)):
                        segments.append((start, end))
                    start = None
                    gap = 0
        if start is not None:
            segments.append((start, len(active_rows) - 1))

        min_width = int(float(self.config.get("vision.activity_min_width", 170)) * scaler.sx)
        targets: list[WatchTarget] = []
        for y1, y2 in segments:
            seg_mask = mask[max(0, y1 - 2) : min(mask.shape[0], y2 + 3), :]
            ys, xs = np.where(seg_mask)
            if xs.size == 0:
                continue
            x1 = int(xs.min())
            x2 = int(xs.max())
            width = x2 - x1 + 1
            green_pixels = int(xs.size)
            if width < min_width:
                continue

            abs_y1 = box[1] + y1
            abs_y2 = box[1] + y2
            center_y = round((abs_y1 + abs_y2) / 2)
            target_x = scaler.x(float(self.config.get("tap_points.watch_button_x", 1715)))
            targets.append(
                WatchTarget(
                    y=center_y,
                    x=target_x,
                    green_pixels=green_pixels,
                    width=width,
                    box=(box[0] + x1, abs_y1, box[0] + x2, abs_y2),
                )
            )

        # Prefer visible rows closest to the center; this avoids tapping partially clipped rows first.
        center = image.height / 2
        return sorted(targets, key=lambda item: abs(item.y - center))

    def diagnose(self, image: Image.Image) -> Diagnosis:
        scene, notes = self.detect_scene(image)
        targets = self.find_watch_targets(image)
        return Diagnosis(scene=scene, targets=targets, image_size=(image.width, image.height), notes=notes)

    def save_debug(self, image: Image.Image, diagnosis: Diagnosis, folder: str | Path = "debug") -> Path:
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        out = image.copy()
        draw = ImageDraw.Draw(out)
        for target in diagnosis.targets:
            draw.rectangle(target.box, outline=(255, 0, 0), width=3)
            draw.ellipse((target.x - 8, target.y - 8, target.x + 8, target.y + 8), outline=(255, 0, 0), width=3)
        filename = folder / f"diagnose_{int(time())}_{diagnosis.scene}.png"
        out.save(filename)
        return filename
