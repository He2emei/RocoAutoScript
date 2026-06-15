from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from .adb import AdbDevice
from .bot import SpectatorBot
from .config import Config
from .stats import RewardStats
from .vision import SCENE_RESULT, Vision, image_from_file, image_from_png


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def build_device(config: Config) -> AdbDevice:
    return AdbDevice(
        executable=str(config.get("adb.executable", "auto")),
        serial=str(config.get("adb.serial")) if config.get("adb.serial") else None,
        mumu_cli=str(config.get("adb.mumu.cli")) if config.get("adb.mumu.cli") else None,
        mumu_index=int(config.get("adb.mumu.index")) if config.get("adb.mumu.index") is not None else None,
        mumu_auto_connect=bool(config.get("adb.mumu.auto_connect", True)),
    )


def cmd_devices(config: Config) -> int:
    device = build_device(config)
    device.connect_mumu()
    print(device.devices())
    return 0


def cmd_screenshot(config: Config, output: str) -> int:
    device = build_device(config)
    image = image_from_png(device.screenshot_png())
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    print(f"saved {out.resolve()} ({image.width}x{image.height})")
    return 0


def cmd_diagnose(config: Config, image_path: str | None, save_debug: bool) -> int:
    device = None
    if image_path:
        image = image_from_file(image_path)
    else:
        device = build_device(config)
        image = image_from_png(device.screenshot_png())

    vision = Vision(config)
    diagnosis = vision.diagnose(image)
    print(f"image: {diagnosis.image_size[0]}x{diagnosis.image_size[1]}")
    print(f"scene: {diagnosis.scene}")
    print(f"offline tail: {diagnosis.offline_tail}")
    print("notes:")
    for note in diagnosis.notes:
        print(f"  - {note}")
    print(f"watch targets: {len(diagnosis.targets)}")
    for idx, target in enumerate(diagnosis.targets, 1):
        print(
            f"  {idx}. tap=({target.x}, {target.y}) "
            f"row={target.row_index + 1 if target.row_index >= 0 else '-'} "
            f"score={target.green_pixels} width={target.width} reason={target.reason or '-'} box={target.box}"
        )
    if diagnosis.scene == SCENE_RESULT:
        reward = vision.extract_reward_coins(image)
        print(f"reward coins: {reward.amount if reward.amount is not None else 'unknown'}")
        print(f"reward text: {reward.text!r} confidence={reward.confidence:.3f} box={reward.box}")
    if save_debug:
        path = vision.save_debug(image, diagnosis)
        print(f"debug image: {path.resolve()}")
    return 0


def cmd_run(config: Config, interval: float | None, dry_run: bool | None) -> int:
    interval_seconds = float(interval if interval is not None else config.get("runtime.interval_seconds", 30))
    effective_dry_run = bool(config.get("runtime.dry_run", False) if dry_run is None else dry_run)
    device = build_device(config)
    bot = SpectatorBot(config, device, dry_run=effective_dry_run)
    bot.run_forever(interval_seconds)
    return 0


def cmd_clicker(config: Config, x: int | None, y: int | None, interval: float | None, once: bool) -> int:
    point = config.get("clicker.energy_point", [106, 618])
    tap_x = int(x if x is not None else point[0])
    tap_y = int(y if y is not None else point[1])
    delay = float(interval if interval is not None else config.get("clicker.interval_seconds", 2.0))
    device = build_device(config)
    logging.getLogger("roco_auto").info("clicker started: point=(%s, %s) interval=%ss", tap_x, tap_y, delay)

    while True:
        device.tap(tap_x, tap_y)
        if once:
            break
        time.sleep(delay)
    return 0


def cmd_stats(config: Config) -> int:
    stats = RewardStats(config)
    summary = stats.summary()
    print(f"battles: {summary.get('battles', 0)}")
    print(f"coins: {summary.get('coins', 0)}")
    if summary.get("last_amount") is not None:
        print(f"last amount: {summary.get('last_amount')}")
    if summary.get("last_timestamp"):
        print(f"last timestamp: {summary.get('last_timestamp')}")
    print(f"events file: {stats.events_file}")
    return 0


def cmd_gui() -> int:
    from .gui import main as gui_main

    return gui_main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roco_auto")
    parser.add_argument("--config", default=None, help="Path to config YAML.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="Show adb devices.")

    screenshot = sub.add_parser("screenshot", help="Capture a screenshot from the configured device.")
    screenshot.add_argument("--output", default="debug/live.png")

    diagnose = sub.add_parser("diagnose", help="Diagnose scene and watchable rows.")
    diagnose.add_argument("--image", default=None, help="Use a local image instead of live screenshot.")
    diagnose.add_argument("--save-debug", action="store_true", help="Save an annotated debug image.")

    run = sub.add_parser("run", help="Run the spectator bot.")
    run.add_argument("--interval", type=float, default=None, help="Loop interval for wait/unknown states.")
    dry = run.add_mutually_exclusive_group()
    dry.add_argument("--dry-run", action="store_true", dest="dry_run")
    dry.add_argument("--no-dry-run", action="store_false", dest="dry_run")
    run.set_defaults(dry_run=None)

    clicker = sub.add_parser("clicker", help="Tap the configured energy button repeatedly.")
    clicker.add_argument("--x", type=int, default=None, help="Raw screen x coordinate.")
    clicker.add_argument("--y", type=int, default=None, help="Raw screen y coordinate.")
    clicker.add_argument("--interval", type=float, default=None, help="Seconds between taps.")
    clicker.add_argument("--once", action="store_true", help="Tap once and exit.")

    sub.add_parser("stats", help="Show recorded reward totals.")
    sub.add_parser("gui", help="Open the lightweight Tkinter GUI.")

    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    config = Config.load(args.config)

    if args.command == "devices":
        return cmd_devices(config)
    if args.command == "screenshot":
        return cmd_screenshot(config, args.output)
    if args.command == "diagnose":
        return cmd_diagnose(config, args.image, args.save_debug)
    if args.command == "run":
        return cmd_run(config, args.interval, args.dry_run)
    if args.command == "clicker":
        return cmd_clicker(config, args.x, args.y, args.interval, args.once)
    if args.command == "stats":
        return cmd_stats(config)
    if args.command == "gui":
        return cmd_gui()
    raise AssertionError(args.command)
