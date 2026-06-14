from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


COMMON_ADB_PATHS = (
    r"D:\APP\MuMuPlayer\nx_main\adb.exe",
    r"D:\APP\MuMuPlayer\nx_device\12.0\shell\adb.exe",
    r"C:\Program Files\Netease\MuMu Player 12\shell\adb.exe",
    r"C:\Program Files\Netease\MuMuPlayer-12\shell\adb.exe",
)


class AdbError(RuntimeError):
    pass


class AdbDevice:
    def __init__(
        self,
        executable: str = "auto",
        serial: str | None = None,
        mumu_cli: str | None = None,
        mumu_index: int | None = None,
        mumu_auto_connect: bool = True,
    ) -> None:
        self.executable = self._resolve_adb(executable)
        self.serial = serial
        self.mumu_cli = mumu_cli
        self.mumu_index = mumu_index
        self.mumu_auto_connect = mumu_auto_connect

    @staticmethod
    def _resolve_adb(executable: str) -> str:
        if executable and executable != "auto":
            if Path(executable).exists():
                return executable
            raise FileNotFoundError(f"ADB executable not found: {executable}")

        path = shutil.which("adb")
        if path:
            return path

        for candidate in COMMON_ADB_PATHS:
            if Path(candidate).exists():
                return candidate

        raise FileNotFoundError("ADB executable not found. Set adb.executable in config.yaml.")

    def _base_cmd(self) -> list[str]:
        cmd = [self.executable]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def run(self, args: list[str], *, check: bool = True, binary: bool = False, timeout: int = 30) -> bytes | str:
        proc = subprocess.run(
            self._base_cmd() + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if check and proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            stdout = proc.stdout.decode("utf-8", errors="replace").strip()
            raise AdbError(stderr or stdout or f"adb exited with {proc.returncode}")
        if binary:
            return proc.stdout
        return proc.stdout.decode("utf-8", errors="replace")

    def connect_mumu(self) -> None:
        if not self.mumu_auto_connect or not self.mumu_cli or self.mumu_index is None:
            return
        cli = Path(self.mumu_cli)
        if not cli.exists():
            return
        subprocess.run(
            [str(cli), "adb", "-v", str(self.mumu_index), "-c", "connect"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )

    def devices(self) -> str:
        proc = subprocess.run(
            [self.executable, "devices", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        return proc.stdout.decode("utf-8", errors="replace")

    def ensure_connected(self) -> None:
        self.connect_mumu()
        if not self.serial:
            return
        output = self.devices()
        if self.serial not in output:
            host, _, port = self.serial.partition(":")
            if host and port:
                subprocess.run(
                    [self.executable, "connect", self.serial],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=15,
                    check=False,
                )
        state = self.run(["get-state"], check=False).strip()
        if state != "device":
            raise AdbError(f"ADB device is not ready: serial={self.serial!r}, state={state!r}")

    def screenshot_png(self) -> bytes:
        self.ensure_connected()
        data = self.run(["exec-out", "screencap", "-p"], binary=True, timeout=30)
        if not isinstance(data, bytes) or not data.startswith(b"\x89PNG"):
            raise AdbError("ADB screencap did not return a PNG image.")
        return data

    def tap(self, x: int, y: int) -> None:
        self.ensure_connected()
        self.run(["shell", "input", "tap", str(x), str(y)], timeout=10)

    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration_ms: int = 500) -> None:
        self.ensure_connected()
        self.run(
            [
                "shell",
                "input",
                "swipe",
                str(start[0]),
                str(start[1]),
                str(end[0]),
                str(end[1]),
                str(duration_ms),
            ],
            timeout=15,
        )

    def shell(self, command: str) -> str:
        self.ensure_connected()
        return self.run(["shell", command], timeout=20)
