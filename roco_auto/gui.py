from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk

import yaml

from .config import Config, ROOT


PROFILE_DIR = ROOT / "configs"
DEFAULT_PROFILE = ROOT / "config.yaml"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _set_dotted(data: dict, dotted: str, value) -> None:
    current = data
    parts = dotted.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _get_dotted(data: dict, dotted: str, default=""):
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _profile_name(path: Path) -> str | None:
    if path.parent.resolve() != PROFILE_DIR.resolve():
        return None
    return path.stem


class RocoGui:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("RocoAutoScript")
        self.root.geometry("960x620")
        self.root.minsize(860, 540)

        self.profile_var = StringVar()
        self.profile_paths: dict[str, Path] = {}
        self.config_data: dict = {}
        self.processes: dict[str, subprocess.Popen] = {}
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.serial_var = StringVar()
        self.mumu_index_var = StringVar()
        self.mumu_cli_var = StringVar()
        self.adb_exe_var = StringVar()
        self.interval_var = StringVar()
        self.dry_run_var = BooleanVar()
        self.click_x_var = StringVar()
        self.click_y_var = StringVar()
        self.click_interval_var = StringVar()
        self.summary_var = StringVar(value="battles: 0    coins: 0")

        self._build()
        self.refresh_profiles()
        self.root.after(300, self._drain_logs)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(2, weight=1)

        profile_frame = ttk.LabelFrame(outer, text="配置档案", padding=8)
        profile_frame.grid(row=0, column=0, rowspan=3, sticky="nsw", padx=(0, 10))
        profile_frame.columnconfigure(0, weight=1)

        self.profile_list = ttk.Treeview(profile_frame, columns=("path",), show="tree", height=12)
        self.profile_list.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.profile_list.bind("<<TreeviewSelect>>", self._on_profile_select)

        ttk.Button(profile_frame, text="刷新", command=self.refresh_profiles).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(profile_frame, text="新建", command=self.new_profile).grid(row=1, column=1, sticky="ew", pady=(8, 0), padx=(6, 0))
        ttk.Button(profile_frame, text="复制为", command=self.duplicate_profile).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(profile_frame, text="打开目录", command=self.open_profiles_dir).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        config_frame = ttk.LabelFrame(outer, text="关键配置", padding=8)
        config_frame.grid(row=0, column=1, sticky="new")
        for col in (1, 3):
            config_frame.columnconfigure(col, weight=1)

        self._entry(config_frame, 0, 0, "ADB serial", self.serial_var)
        self._entry(config_frame, 0, 2, "MuMu index", self.mumu_index_var, width=10)
        self._entry(config_frame, 1, 0, "mumu-cli", self.mumu_cli_var)
        ttk.Button(config_frame, text="选择", command=self.choose_mumu_cli).grid(row=1, column=4, padx=(6, 0))
        self._entry(config_frame, 2, 0, "adb.exe", self.adb_exe_var)
        ttk.Button(config_frame, text="选择", command=self.choose_adb).grid(row=2, column=4, padx=(6, 0))
        self._entry(config_frame, 3, 0, "观战间隔", self.interval_var, width=10)
        ttk.Checkbutton(config_frame, text="dry-run", variable=self.dry_run_var).grid(row=3, column=2, sticky="w", padx=(8, 0))
        self._entry(config_frame, 4, 0, "聚能 X", self.click_x_var, width=10)
        self._entry(config_frame, 4, 2, "聚能 Y", self.click_y_var, width=10)
        self._entry(config_frame, 5, 0, "连点间隔", self.click_interval_var, width=10)

        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=6, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        for col in range(6):
            button_frame.columnconfigure(col, weight=1)
        ttk.Button(button_frame, text="保存配置", command=self.save_profile).grid(row=0, column=0, sticky="ew")
        ttk.Button(button_frame, text="设备列表", command=self.run_devices).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Button(button_frame, text="截图", command=self.run_screenshot).grid(row=0, column=2, sticky="ew", padx=(6, 0))
        ttk.Button(button_frame, text="诊断", command=self.run_diagnose).grid(row=0, column=3, sticky="ew", padx=(6, 0))
        ttk.Button(button_frame, text="统计", command=self.run_stats).grid(row=0, column=4, sticky="ew", padx=(6, 0))
        ttk.Button(button_frame, text="停止全部", command=self.stop_all).grid(row=0, column=5, sticky="ew", padx=(6, 0))

        run_frame = ttk.LabelFrame(outer, text="运行", padding=8)
        run_frame.grid(row=1, column=1, sticky="ew", pady=(10, 10))
        run_frame.columnconfigure(5, weight=1)
        ttk.Button(run_frame, text="启动观战", command=self.start_watch).grid(row=0, column=0, sticky="ew")
        ttk.Button(run_frame, text="dry-run观战", command=lambda: self.start_watch(force_dry=True)).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(run_frame, text="停止观战", command=lambda: self.stop_process("watch")).grid(row=0, column=2, sticky="ew", padx=(8, 0))
        ttk.Button(run_frame, text="启动聚能", command=self.start_clicker).grid(row=0, column=3, sticky="ew", padx=(8, 0))
        ttk.Button(run_frame, text="停止聚能", command=lambda: self.stop_process("clicker")).grid(row=0, column=4, sticky="ew", padx=(8, 0))
        ttk.Label(run_frame, textvariable=self.summary_var).grid(row=0, column=5, sticky="e", padx=(8, 0))

        log_frame = ttk.LabelFrame(outer, text="日志", padding=8)
        log_frame.grid(row=2, column=1, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = ScrolledText(log_frame, height=14, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

    @staticmethod
    def _entry(parent, row: int, col: int, label: str, var: StringVar, width: int | None = None) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", pady=3)
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=row, column=col + 1, sticky="ew", padx=(6, 8), pady=3)

    def refresh_profiles(self) -> None:
        PROFILE_DIR.mkdir(exist_ok=True)
        if not DEFAULT_PROFILE.exists() and not any(PROFILE_DIR.glob("*.yaml")):
            shutil.copyfile(ROOT / "config.example.yaml", DEFAULT_PROFILE)
        self.profile_paths = {}
        self.profile_list.delete(*self.profile_list.get_children())

        if DEFAULT_PROFILE.exists():
            self.profile_paths["default"] = DEFAULT_PROFILE
            self.profile_list.insert("", "end", iid="default", text="default")
        for path in sorted(PROFILE_DIR.glob("*.yaml")):
            name = path.stem
            self.profile_paths[name] = path
            self.profile_list.insert("", "end", iid=name, text=name)

        first = next(iter(self.profile_paths), None)
        if first:
            self.profile_list.selection_set(first)
            self.load_profile(first)

    def _on_profile_select(self, _event=None) -> None:
        selected = self.profile_list.selection()
        if selected:
            self.load_profile(selected[0])

    def current_profile_path(self) -> Path:
        selected = self.profile_list.selection()
        if not selected:
            raise RuntimeError("请选择一个配置档案。")
        return self.profile_paths[selected[0]]

    def load_profile(self, name: str) -> None:
        path = self.profile_paths[name]
        self.profile_var.set(name)
        self.config_data = Config.load(path).data
        self.serial_var.set(str(_get_dotted(self.config_data, "adb.serial", "")))
        self.mumu_index_var.set(str(_get_dotted(self.config_data, "adb.mumu.index", "")))
        self.mumu_cli_var.set(str(_get_dotted(self.config_data, "adb.mumu.cli", "")))
        self.adb_exe_var.set(str(_get_dotted(self.config_data, "adb.executable", "auto")))
        self.interval_var.set(str(_get_dotted(self.config_data, "runtime.interval_seconds", 30)))
        self.dry_run_var.set(bool(_get_dotted(self.config_data, "runtime.dry_run", False)))
        energy = _get_dotted(self.config_data, "clicker.energy_point", [106, 618])
        if not isinstance(energy, list) or len(energy) != 2:
            energy = [106, 618]
        self.click_x_var.set(str(energy[0]))
        self.click_y_var.set(str(energy[1]))
        self.click_interval_var.set(str(_get_dotted(self.config_data, "clicker.interval_seconds", 2.0)))
        self.update_stats_label()
        self.log(f"loaded profile: {name} ({path})")

    def save_profile(self) -> bool:
        try:
            path = self.current_profile_path()
            data = dict(self.config_data)
            _set_dotted(data, "adb.serial", self.serial_var.get().strip())
            _set_dotted(data, "adb.mumu.index", int(self.mumu_index_var.get().strip()))
            _set_dotted(data, "adb.mumu.cli", self.mumu_cli_var.get().strip())
            _set_dotted(data, "adb.executable", self.adb_exe_var.get().strip() or "auto")
            _set_dotted(data, "runtime.interval_seconds", float(self.interval_var.get().strip()))
            _set_dotted(data, "runtime.dry_run", bool(self.dry_run_var.get()))
            _set_dotted(data, "clicker.energy_point", [int(self.click_x_var.get().strip()), int(self.click_y_var.get().strip())])
            _set_dotted(data, "clicker.interval_seconds", float(self.click_interval_var.get().strip()))
            profile_name = _profile_name(path)
            if profile_name:
                _set_dotted(data, "stats.events_file", f"stats/{profile_name}/rewards.jsonl")
                _set_dotted(data, "stats.summary_file", f"stats/{profile_name}/summary.json")
                _set_dotted(data, "stats.unresolved_dir", f"debug/{profile_name}/reward_unresolved")
                _set_dotted(data, "runtime.screenshot_dir", f"debug/{profile_name}/screenshots")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)
            self.config_data = data
            self.log(f"saved profile: {path}")
            return True
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return False

    def new_profile(self) -> None:
        name = simpledialog.askstring("新建配置", "配置名称，例如 account4：", parent=self.root)
        if not name:
            return
        safe_name = "".join(ch for ch in name.strip() if ch.isalnum() or ch in ("-", "_"))
        if not safe_name:
            messagebox.showerror("名称无效", "配置名称只能包含字母、数字、下划线或短横线。")
            return
        path = PROFILE_DIR / f"{safe_name}.yaml"
        if path.exists():
            messagebox.showerror("已存在", f"{path} 已存在。")
            return
        source = DEFAULT_PROFILE if DEFAULT_PROFILE.exists() else ROOT / "config.example.yaml"
        shutil.copyfile(source, path)
        self.refresh_profiles()
        self.profile_list.selection_set(safe_name)
        self.load_profile(safe_name)

    def duplicate_profile(self) -> None:
        try:
            source = self.current_profile_path()
        except RuntimeError as exc:
            messagebox.showerror("未选择配置", str(exc))
            return
        name = simpledialog.askstring("复制配置", "新配置名称：", parent=self.root)
        if not name:
            return
        safe_name = "".join(ch for ch in name.strip() if ch.isalnum() or ch in ("-", "_"))
        target = PROFILE_DIR / f"{safe_name}.yaml"
        if target.exists():
            messagebox.showerror("已存在", f"{target} 已存在。")
            return
        shutil.copyfile(source, target)
        self.refresh_profiles()
        self.profile_list.selection_set(safe_name)
        self.load_profile(safe_name)

    def choose_mumu_cli(self) -> None:
        path = filedialog.askopenfilename(title="选择 mumu-cli.exe", filetypes=[("mumu-cli", "mumu-cli.exe"), ("exe", "*.exe")])
        if path:
            self.mumu_cli_var.set(path)

    def choose_adb(self) -> None:
        path = filedialog.askopenfilename(title="选择 adb.exe", filetypes=[("adb", "adb.exe"), ("exe", "*.exe")])
        if path:
            self.adb_exe_var.set(path)

    def open_profiles_dir(self) -> None:
        PROFILE_DIR.mkdir(exist_ok=True)
        subprocess.Popen(["explorer", str(PROFILE_DIR)])

    def _base_cmd(self) -> list[str]:
        return [sys.executable, "-u", "-m", "roco_auto", "--config", str(self.current_profile_path())]

    def _start_process(self, name: str, args: list[str]) -> None:
        if name in self.processes and self.processes[name].poll() is None:
            messagebox.showinfo("正在运行", f"{name} 已经在运行。")
            return
        if not self.save_profile():
            return
        cmd = self._base_cmd() + args
        self.log("> " + " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.processes[name] = proc
        threading.Thread(target=self._read_process_output, args=(name, proc), daemon=True).start()

    def _run_once(self, args: list[str]) -> None:
        if not self.save_profile():
            return
        cmd = self._base_cmd() + args
        self.log("> " + " ".join(cmd))
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=self._read_process_output, args=("once", proc), daemon=True).start()

    def _read_process_output(self, name: str, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            self.log_queue.put(line.rstrip())
        code = proc.wait()
        self.log_queue.put(f"[{name}] exited with code {code}")

    def start_watch(self, force_dry: bool = False) -> None:
        args = ["run", "--interval", self.interval_var.get().strip() or "30"]
        if force_dry or self.dry_run_var.get():
            args.append("--dry-run")
        self._start_process("watch", args)

    def start_clicker(self) -> None:
        self._start_process("clicker", ["clicker"])

    def stop_process(self, name: str) -> None:
        proc = self.processes.get(name)
        if not proc or proc.poll() is not None:
            self.log(f"{name} is not running")
            return
        proc.terminate()
        self.log(f"stopping {name}")

    def stop_all(self) -> None:
        for name in list(self.processes):
            self.stop_process(name)

    def run_devices(self) -> None:
        self._run_once(["devices"])

    def run_screenshot(self) -> None:
        self._run_once(["screenshot", "--output", "debug/gui_live.png"])

    def run_diagnose(self) -> None:
        self._run_once(["diagnose", "--save-debug"])

    def run_stats(self) -> None:
        self._run_once(["stats"])
        self.root.after(800, self.update_stats_label)

    def update_stats_label(self) -> None:
        try:
            from .stats import RewardStats

            stats = RewardStats(Config.load(self.current_profile_path()))
            summary = stats.summary()
            self.summary_var.set(f"battles: {summary.get('battles', 0)}    coins: {summary.get('coins', 0)}")
        except Exception:
            self.summary_var.set("battles: ?    coins: ?")

    def log(self, text: str) -> None:
        self.log_queue.put(text)

    def _drain_logs(self) -> None:
        changed = False
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", line + "\n")
            changed = True
        if changed:
            line_count = int(self.log_text.index("end-1c").split(".")[0])
            if line_count > 800:
                self.log_text.delete("1.0", f"{line_count - 600}.0")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(500, self._drain_logs)

    def close(self) -> None:
        running = [name for name, proc in self.processes.items() if proc.poll() is None]
        if running and not messagebox.askyesno("退出", "仍有进程在运行，是否停止并退出？"):
            return
        self.stop_all()
        self.root.destroy()

    def run(self) -> int:
        self.root.mainloop()
        return 0


def main() -> int:
    return RocoGui().run()
