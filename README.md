# RocoAutoScript

洛克王国：世界的简易自动观战脚本。当前目标很窄：在 MuMu 模拟器里低频截图，识别好友列表中“正在进行[闪耀大赛]”一类绿色长状态，点击右侧“传送并观战”，结束后继续下一轮。

第一次使用请先看 [SETUP.md](SETUP.md)，里面按顺序说明了依赖安装、`config.yaml`、MuMu 实例、ADB serial、截图诊断和启动方式。

## 当前流程

1. 在大世界普通界面点击左上角菜单。
2. 在菜单里点击“好友”。
3. 在好友列表中按可见行扫描可观战好友，并跳过黑名单玩家。
4. 点击该好友右侧的观战按钮。
5. 在弹窗中确认“传送并观战”。
6. 观战中等待。
7. 对战结束奖励页识别本局金币，写入统计后点击任意位置退出，然后重复。

如果当前 6 行没有可观战目标，脚本会向下滑动一屏继续扫描；一旦看到灰色离线时间行，就认为该列表后面都离线，切到 QQ 好友列表继续查找。QQ 好友列表也到离线区或达到 `runtime.max_swipes_per_tab` 后，才等待 `runtime.interval_seconds`，下一轮会回到游戏好友列表重新扫描。
如果游戏长时间未操作进入节能模式，脚本会点击屏幕中心返回游戏。

脚本默认使用 MuMu 第三个实例，ADB serial 为 `127.0.0.1:16448`。如果你的实例变化了，可以改 `config.yaml`。
`config.yaml` 是本机配置，不进入版本控制；新环境可以从 `config.example.yaml` 复制一份。

## 运行

```powershell
python -m roco_auto devices
python -m roco_auto screenshot --output debug/live.png
python -m roco_auto diagnose --image debug/live.png
python -m roco_auto run --interval 30
python -m roco_auto clicker
python -m roco_auto stats
python -m roco_auto gui
```

常用参数：

```powershell
python -m roco_auto run --dry-run
python -m roco_auto run --interval 60
python -m roco_auto diagnose
python -m roco_auto clicker --x 106 --y 618 --interval 2
```

`clicker` 是一个纯 ADB 连点器，不截图、不识别图像。默认每 2 秒点击一次 `config.yaml` 里的 `clicker.energy_point`，用于战斗中持续点击左下角“聚能”。

`diagnose` 不传 `--image` 时会从模拟器实时截图，并打印识别到的界面和候选好友行。

可选：如果希望好友状态用 OCR 辅助识别，可以额外安装一个 OCR 后端。脚本会自动尝试 RapidOCR 或 Tesseract；没装时会降级到严格状态模板，不影响启动。

```powershell
pip install rapidocr_onnxruntime
```

`stats` 会打印当前累计观战场次、累计金币和统计文件位置。统计默认写入 `stats/rewards.jsonl` 与 `stats/summary.json`。

`gui` 会打开一个低刷新率 Tkinter 管理界面，用于切换多账号配置、启动/停止观战、启动/停止聚能、查看日志和统计。GUI 不做实时画面预览，主要通过子进程运行现有命令，尽量减少额外性能消耗。

## 配置

`config.yaml` 里最常改的是：

- `adb.serial`：目标模拟器，比如 `127.0.0.1:16448`。
- `runtime.interval_seconds`：主循环截图间隔。
- `runtime.dry_run`：只识别不点击。
- `blacklist.enabled`：是否启用不可观战玩家过滤。
- `blacklist.names`：OCR 可用时用于过滤的黑名单玩家名。
- `templates.blacklist`：黑名单玩家姓名模板。需要新增玩家时，裁一张姓名小图放到 `assets/templates`，再在这里追加配置。
- `ocr.enabled`：是否启用好友状态 OCR。OCR 只跑每行状态文字的小区域，不做全屏识别。
- `friend_list`：好友列表可见行、行距、状态文字区域和姓名区域。不同分辨率下优先调这里。
- `vision.offline_*`：离线灰字检测阈值。看到灰色离线时间行后，会停止继续下滑当前列表。
- `swipe`：好友列表翻页参数。默认按 `friend_list.row_gap * swipe.rows_per_page` 计算拖动距离，并用较长 `duration_ms` 慢拖以减少惯性。
- `stats.enabled`：是否记录结算页金币统计。
- `reward_ocr.template_dir`：奖励金币数字模板目录。遇到缺模板数字时会保存未识别裁图到 `debug/reward_unresolved`。
- `vision.activity_min_width`：绿色状态文字最小宽度。真实手机 UI 如果识别不到可观战好友，可以适当调低。
- `templates`：页面模板配置。每个模板都有 `file`、`region`、`threshold`，坐标同样按 `2048x1152` 写。
- `regions` 和 `tap_points`：所有坐标都按截图基准 `2048x1152` 写，脚本会自动缩放到当前截图大小。

多账号配置可以放在 `configs/*.yaml`。命令行使用时，把 `--config` 放在子命令前：

```powershell
python -m roco_auto --config configs/account-main.yaml run --interval 30
python -m roco_auto --config configs/account-alt.yaml stats
```

## 设计说明

这个项目参考 AzurLaneAutoScript 的基本路线，但做了极简化。当前识别方案是：

- ADB 负责截图、点击、滑动。
- Pillow/numpy 做局部模板匹配。菜单、好友页、确认弹窗、观战页、结算页都优先用 `assets/templates` 里的 UI 小图确认。
- 好友列表按 6 个可见行分别判断。每行先尝试 OCR 识别状态文字，命中“正在进行”和“闪耀大赛”才算可观战；OCR 不可用时降级到状态文字模板。
- 黑名单按行过滤：如果黑名单姓名模板或 OCR 姓名和可观战状态处于同一行，该候选会被丢弃，并继续寻找下一位非黑名单玩家。
- 找不到目标时不会立刻等待，而是先按配置滑动到下一屏；看到离线灰字后切换到 QQ 好友列表，QQ 列表也结束后再等待并重置列表。
- 结算金币使用右下角金额区域的轻量数字模板识别，识别成功才写入累计统计。
- `vision.green_status_fallback` 可以恢复旧的泛绿色扫描，但默认关闭，避免误传到非 PVP 好友。
- 颜色/亮度统计只作为兜底，例如过场黑屏、小地图、动态血条布局，不再作为主判据。
- 节能模式用深色背景、底部返回提示和黄色电池图标组合判断，命中后点击屏幕中心唤醒。
- 坐标按 16:9 基准归一化，适配 MuMu 当前横屏截图。
- 不做隐藏窗口、反检测、注入或内存读写，只模拟普通点击。

如果游戏 UI 更新或手机版布局和截图差异较大，优先用下面命令存图：

```powershell
python -m roco_auto screenshot --output debug/problem.png
python -m roco_auto diagnose --image debug/problem.png --save-debug
```

然后根据 `debug/diagnose_*.png` 里的框位微调配置。
