# Config Profiles

GUI 会在这个目录下保存多账号配置，例如：

```text
configs/account-main.yaml
configs/account-alt.yaml
```

这些 `*.yaml` 文件包含本机 MuMu serial、实例编号、统计路径等信息，默认不进入 Git。

命令行也可以直接使用某个配置：

```powershell
python -m roco_auto --config configs/account-main.yaml run --interval 30
python -m roco_auto --config configs/account-alt.yaml stats
```
