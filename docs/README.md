# 文档索引

## 当前主线

| 文档 | 内容 |
|---|---|
| [plan-debian-bringup.md](plan-debian-bringup.md) | 双系统路线、阶段 A–G 状态与验收标准 |
| [wireless-bringup.md](wireless-bringup.md) | QCA6174 WiFi 根因、board data、复现流程、吞吐/稳定性结果 |
| [ufs-static-analysis.md](ufs-static-analysis.md) | UFS 冷启动、持续写、热重启矩阵 |
| [display-bringup-notes.md](display-bringup-notes.md) | 双 DSI 面板点亮记录 |
| [mdp5-dual-intf-plan.md](mdp5-dual-intf-plan.md) | MDP5 双接口全屏方案（已实现） |
| [x2-hardware.md](x2-hardware.md) | 整机硬件型号与总线 |
| [x2-sensors.md](x2-sensors.md) | 45 个传感器逐条记录 |
| [x2-firmware.md](x2-firmware.md) | 固件/本机持久资料缺口、两层打包与部署 |

## 后续阶段

| 文档 | 内容 |
|---|---|
| [plan-debian-only-migration.md](plan-debian-only-migration.md) | 放弃 Android 后的最终分区布局、原生启动链、迁移门槛与回滚 |
| [fingerprint-qbt1000-analysis.md](fingerprint-qbt1000-analysis.md) | QBT1000 指纹方案与 TrustZone/SSC 限制 |
| [debian-peripherals-gap.md](debian-peripherals-gap.md) | 早期外设缺口快照；PCIe/BT 部分已过时，以 wireless/plan 为准 |

## 历史记录

| 文档 | 内容 |
|---|---|
| [debian-mainline-milestone.md](debian-mainline-milestone.md) | Debian 首次进入用户空间 |
| [peripherals-dts-notes.md](peripherals-dts-notes.md) | vendor DTS/pinctrl 证据摘录 |

## 约定

- 当前结论写进 `plan-debian-bringup.md` 或对应 bring-up 文档，过时的“缺口”文档
  只保留为历史参考，不再作为实现依据。
- 每个硬件 bring-up 文档至少包含：硬件 ID/总线、驱动/固件、复现命令、验收结果、
  已知限制。
- 不把 WiFi PSK、设备序列号等敏感信息写进文档或仓库。
