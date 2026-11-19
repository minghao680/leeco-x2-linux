# x2 启动日志错误分诊

基线：`6.19.5-msm8996+ #54`，latest boot 850 行。只列最近一次启动里实际出现的内容。

## 本次已处理

### 1. arm-smmu 的 TLB sync timeout

日志：

```text
arm-smmu d00000.iommu: smmu-reset: 9 tlb sync
arm-smmu d00000.iommu: TLB sync timed out -- SMMU may be deadlocked
```

这条是诊断补丁 `0002-arm-smmu-trace-reset.patch` 造成的：它在
`arm_smmu_device_reset()` 的 TLBI 和 TLB sync 之间插入了多条 `dev_info()`，
printk 延迟足以让 TLB sync 超时。该补丁已移到
`kernel/patches/debug/`，不再进入生产构建。

### 2. WLED OVP IRQ unbalanced enable

日志：

```text
Unbalanced enable for IRQ 61
WARNING: kernel/irq/manage.c:753 at __enable_irq
Workqueue: events wled_ovp_work
```

原因是 bootloader 可能已经把 WLED module 打开，`wled_configure_ovp_irq()`
看到 module enabled 就没有 `disable_irq()`；随后 `wled_module_enable(1)` 又
schedule `wled_ovp_work`，work 里再 `enable_irq()`，于是重复 enable。

`0008-wled-ovp-irq-state.patch` 增加 `ovp_irq_enabled` 状态：

- probe 时按 module 当前状态同步状态；
- work 只在 IRQ 未 enable 时才 enable；
- module disable 时只在已 enable 时才 disable；
- remove 时同样按状态处理。

## 仍然存在，但不是这次要修

| 日志 | 性质 |
|---|---|
| `[Firmware Bug]: Kernel image misaligned at boot` | bootloader 加载地址问题，内核侧无法修 |
| `psci: failed to set PC mode: -1` | 该 bootloader 的 PSCI 固件行为，非致命 |
| `ufshcd dme-get attr-id 0xa00b failed` / `hw clk gating enabled failed` | UFS 控制器能力探测失败，UFS 读写正常 |
| `qcom-pcie: Invalid eDMA IRQs found` | PCIe eDMA 不可用；WiFi 走别的路径，正常 |
| `ath10k: failed to fetch board data ... board-2.bin` | 已知回退到 board.bin，WiFi 正常 |
| `temp-alarm deferred` / `qcrypto Failed to get TX DMA channel` | 可选设备 deferred probe，不影响使用 |
| `bam-dma-engine 644000.dma-controller: probe failed -22` | BAM DMA 初始化失败；当前没有依赖它的功能 |
| `fd_ahb_clk status stuck at 'on'` | 未使用时钟无法关闭，时钟框架 WARN，非功能问题 |
| `mdp5_irq_error_handler *ERROR* errors: 14000000` | MDP5 启动路径错误位；屏幕仍能显示，需单独查 |
| `drm vblank wait timed out` | 关闭/刷新路径的 vblank 超时，发生在关机阶段 |
| `WLED fault=0x8` | WLED OVP 状态；去掉 debug patch 后不再打印 |
| `Bluetooth Frame reassembly failed (-84)` | QCA 蓝牙固件加载期噪声，之后可用 |

## 验证镜像

- `out/boot-x2-debian-clean.img`
- 内含：watchdog restart 修复、WLED IRQ 状态修复、UFS restart shutdown 规避
- 不包含：arm-smmu trace、wled debug 两个诊断补丁
