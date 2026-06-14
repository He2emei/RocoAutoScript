# RocoAutoScript

洛克王国：世界的简易自动观战脚本。当前目标很窄：在 MuMu 模拟器里低频截图，识别好友列表中“正在进行[闪耀大赛]”一类绿色长状态，点击右侧“传送并观战”，结束后继续下一轮。

第一次使用请先看 [SETUP.md](SETUP.md)，里面按顺序说明了依赖安装、`config.yaml`、MuMu 实例、ADB serial、截图诊断和启动方式。

## 当前流程

1. 在大世界普通界面点击左上角菜单。
2. 在菜单里点击“好友”。
3. 在好友列表中扫描可观战好友，并跳过黑名单玩家。
4. 点击该好友右侧的观战按钮。
5. 在弹窗中确认“传送并观战”。
6. 观战中等待。
7. 对战结束奖励页点击任意位置退出，然后重复。

如果当前好友页没有可观战目标，脚本会留在好友页，等待 `runtime.interval_seconds` 后重新截图判断。
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

## 配置

`config.yaml` 里最常改的是：

- `adb.serial`：目标模拟器，比如 `127.0.0.1:16448`。
- `runtime.interval_seconds`：主循环截图间隔。
- `runtime.dry_run`：只识别不点击。
- `blacklist.enabled`：是否启用不可观战玩家过滤。
- `templates.blacklist`：黑名单玩家姓名模板。需要新增玩家时，裁一张姓名小图放到 `assets/templates`，再在这里追加配置。
- `vision.activity_min_width`：绿色状态文字最小宽度。真实手机 UI 如果识别不到可观战好友，可以适当调低。
- `templates`：页面模板配置。每个模板都有 `file`、`region`、`threshold`，坐标同样按 `2048x1152` 写。
- `regions` 和 `tap_points`：所有坐标都按截图基准 `2048x1152` 写，脚本会自动缩放到当前截图大小。

## 设计说明

这个项目参考 AzurLaneAutoScript 的基本路线，但做了极简化。当前识别方案是：

- ADB 负责截图、点击、滑动。
- Pillow/numpy 做局部模板匹配。菜单、好友页、确认弹窗、观战页、结算页都优先用 `assets/templates` 里的 UI 小图确认。
- 好友可观战目标只接受“正在进行[闪耀大赛]”状态模板命中；普通绿色状态默认不会触发观战。
- 黑名单使用姓名模板匹配：如果黑名单姓名和“正在进行[闪耀大赛]”处于同一行，该候选会被丢弃。
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
