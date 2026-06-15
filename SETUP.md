# Setup Guide

这份文档面向第一次使用本项目的人。目标是从拉取仓库开始，配置到可以截图、诊断、运行自动观战。

## 准备条件

- Windows。
- Python 3.10 或更新版本。
- MuMu 模拟器，已安装手机版《洛克王国：世界》。
- 游戏账号已经登录，并且能进入正常游戏界面。
- 模拟器分辨率建议使用 `1280x720` 横屏。

## 1. 拉取代码

```powershell
git clone git@github.com:He2emei/RocoAutoScript.git
cd RocoAutoScript
```

如果不能使用 SSH，也可以用 HTTPS：

```powershell
git clone https://github.com/He2emei/RocoAutoScript.git
cd RocoAutoScript
```

## 2. 安装 Python 依赖

推荐使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
```

可选：好友状态识别支持 OCR 辅助。脚本只会 OCR 每行状态文字的小区域，不会全屏识别；没安装 OCR 后端时会自动降级到状态模板。

```powershell
python -m pip install rapidocr_onnxruntime
```

以后每次重新打开终端，先进入项目目录并激活虚拟环境：

```powershell
cd RocoAutoScript
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 不允许运行激活脚本，可以临时放开当前用户策略：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 3. 创建本机配置

项目不会提交你的个人配置。第一次使用时复制一份：

```powershell
Copy-Item config.example.yaml config.yaml
```

之后只改 `config.yaml`。常用字段如下：

```yaml
adb:
  executable: auto
  serial: 127.0.0.1:16448
  mumu:
    cli: D:\APP\MuMuPlayer\nx_main\mumu-cli.exe
    index: 2
    auto_connect: true

runtime:
  interval_seconds: 30
  dry_run: false
```

说明：

- `adb.executable`：设为 `auto` 时会自动查找系统 `adb` 或常见 MuMu 路径。找不到时，改成你电脑上的 `adb.exe` 完整路径。
- `adb.serial`：目标模拟器的 ADB 地址，必须和 `python -m roco_auto devices` 看到的一致。
- `adb.mumu.cli`：MuMu 的 `mumu-cli.exe` 路径。安装位置不同就改成自己的路径。
- `adb.mumu.index`：MuMu 实例编号，通常从 0 开始。第三个实例一般是 `2`。
- `runtime.interval_seconds`：等待、观战、无目标时的主循环间隔。默认 30 秒。
- `runtime.max_swipes_per_tab`：好友列表每轮最多向下滑几屏。每屏按 6 条可见好友重新扫描。
- `runtime.dry_run`：设为 `true` 时只识别不点击，适合第一次测试。

## 4. 找到模拟器 serial

先打开 MuMu 和游戏，然后运行：

```powershell
python -m roco_auto devices
```

你会看到类似输出：

```text
List of devices attached
127.0.0.1:16448 device product:...
```

把 `127.0.0.1:16448` 这一段填到 `config.yaml` 的 `adb.serial`。

如果没有设备：

- 确认 MuMu 实例已经启动。
- 确认 `adb.mumu.cli` 路径正确。
- 确认 `adb.mumu.index` 是当前游戏所在实例。
- 把 `adb.executable` 改成 MuMu 自带 `adb.exe` 的完整路径。

## 5. 截图测试

先确认 ADB 能正常截图：

```powershell
python -m roco_auto screenshot --output debug/live.png
```

成功后打开 `debug/live.png`，确认它是当前游戏画面。

## 6. 识别测试

让游戏停在普通大世界界面或好友列表界面，然后运行：

```powershell
python -m roco_auto diagnose --save-debug
```

终端会打印：

- `scene`：当前识别出的页面。
- `watch targets`：好友列表里识别到的可观战候选数量。
- `notes`：模板、逐行识别、OCR 后端和黑名单过滤信息，排查问题时使用。

如果加了 `--save-debug`，会在 `debug/` 里生成带红框的诊断图。

## 7. 先 dry-run

第一次建议先只识别、不点击：

```powershell
python -m roco_auto run --dry-run --interval 30
```

观察日志里 `scene=` 是否符合当前画面。确认没问题后按 `Ctrl+C` 停止。

## 8. 启动自动观战

确认配置正确后运行：

```powershell
python -m roco_auto run --interval 30
```

也可以双击项目里的：

```text
start_auto_watch.bat
```

运行时建议让模拟器保持在游戏内，不要遮挡或最小化到无法截图的状态。

好友列表会按当前可见的 6 条逐行扫描。当前屏没有目标时，脚本会执行一次列表滑动，让下一组好友尽量完整进入同一套行区域；如果看到灰色离线时间行，就认为当前列表后面已经没有在线好友，会切换到 QQ 好友列表继续查找。QQ 好友列表也到离线区，或滑动次数达到 `runtime.max_swipes_per_tab` 后仍没有可观战好友，才等待 `runtime.interval_seconds`，下一轮回到游戏好友列表重新扫描。

## 9. 使用 GUI 和多配置

启动 GUI：

```powershell
python -m roco_auto gui
```

也可以双击：

```text
start_gui.bat
```

GUI 使用标准库 Tkinter，不做实时截图预览，只负责配置档案、启动/停止脚本、查看日志和统计。多账号配置默认放在：

```text
configs/*.yaml
```

在 GUI 里新建 `account-main`、`account-alt` 这类配置后，每个配置可以填不同的 `adb.serial` 和 `adb.mumu.index`。GUI 保存 `configs/account-main.yaml` 时，会把统计文件自动分到：

```text
stats/account-main
```

命令行也可以指定配置。注意 `--config` 要放在子命令前：

```powershell
python -m roco_auto --config configs/account-main.yaml run --interval 30
python -m roco_auto --config configs/account-alt.yaml stats
```

## 10. 启动聚能连点器

聚能连点器不做截图识别，只按固定坐标点击：

```powershell
python -m roco_auto clicker
```

默认坐标来自：

```yaml
clicker:
  energy_point: [106, 618]
  interval_seconds: 2.0
```

也可以双击：

```text
start_juneng_clicker.bat
```

如果你的分辨率或 UI 位置不同，先用截图确认坐标，再改 `config.yaml` 的 `clicker.energy_point`。

## 11. 查看金币统计

自动观战遇到结算页时，会尝试识别右下角本局金币，并写入：

```text
stats/rewards.jsonl
stats/summary.json
```

查看累计值：

```powershell
python -m roco_auto stats
```

如果奖励数字没识别出来，脚本会把右下角金额裁图保存到：

```text
debug/reward_unresolved
```

当前奖励识别是轻量模板方案，不依赖 OCR 软件。遇到从未出现过的数字时，需要从未识别裁图里补一张数字模板到 `assets/templates/reward_digits`。

## 12. 黑名单配置

如果某个好友不允许观战，可以加入黑名单。当前默认已经包含 `全剧终`。

黑名单优先依赖姓名小图模板；如果安装了 OCR 后端，也会参考 `blacklist.names` 里的玩家名。新增玩家的大致流程：

1. 截一张好友列表图。
2. 裁出该玩家姓名区域，保存到 `assets/templates/`。
3. 在 `config.yaml` 的 `templates.blacklist` 追加一项。

示例：

```yaml
templates:
  blacklist:
    - name: 全剧终
      file: assets/templates/blacklist_quanjuzhong.png
      region: [390, 250, 760, 1010]
      threshold: 0.72

blacklist:
  names:
    - 全剧终
```

## 13. 好友列表识别和滚动调参

好友行坐标在 `friend_list` 下配置，所有坐标仍以 `2048x1152` 为基准，会自动缩放到当前截图大小：

```yaml
friend_list:
  visible_rows: 6
  first_row_y: 250
  row_gap: 150
  row_height: 130
  row_match_margin: 55
  status_box: [430, -22, 790, 24]
  name_box: [430, -68, 790, -20]
```

如果滑动后下一组 6 条没有完整对齐，优先调 `swipe.list_start`、`swipe.list_end` 和 `swipe.duration_ms`。默认 `list_end.y` 是按“每次滚约 6 条”校准的；如果实际跳过 7 条，把 `swipe.list_end` 的 y 值调大一些，如果不足 6 条则调小一些。如果某一行状态文字框住不准，优先调 `friend_list.status_box` 和 `friend_list.row_gap`。

离线列表终止检测在 `vision.offline_*` 下配置。默认逻辑是：同一行状态区域内绿色像素很少、灰色文字像素足够多时，认为这一行是“2天前 / 4小时前 / 10小时前”这类离线行。

`region` 是搜索范围，按 `2048x1152` 基准坐标填写；脚本会自动缩放到当前截图大小。

## 常见问题

`ADB executable not found`

把 `config.yaml` 里的 `adb.executable` 改成实际 `adb.exe` 路径，例如：

```yaml
adb:
  executable: D:\APP\MuMuPlayer\nx_main\adb.exe
```

`ADB device is not ready`

检查 `adb.serial` 是否和 `python -m roco_auto devices` 输出一致。也可以重启 MuMu 后再运行 `devices`。

截图不是游戏画面

确认 `adb.serial` 指向的是游戏所在实例。多开时最容易连错实例。

识别不到好友列表

先运行：

```powershell
python -m roco_auto screenshot --output debug/problem.png
python -m roco_auto diagnose --image debug/problem.png --save-debug
```

然后查看 `scene` 和 `debug/diagnose_*.png`。如果游戏 UI 版本变化较大，需要更新 `assets/templates` 或调整 `config.yaml` 里的模板区域与阈值。

误点了不能观战的人

把该玩家加入黑名单模板。脚本会在识别到“正在进行[闪耀大赛]”后，再过滤黑名单同一行。
