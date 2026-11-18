# x2 / MSM8996 UFS 静态对照与最小实验序列

日期：2026-11-18  
目标：不继续无目标刷机；用厂商 3.18 与主线 6.19.5 的源码证据，分别定位冷启动 PA 初始化和持续写/writeback 卡死的最小代码差异。

## 0. 最终实测结论（本节优先于后续历史候选）

**决定性修复：`0019-msm8996-leeco-x2-ufs-regulator-load.patch`。**

x2 DTS 的 L20/L25/S4 原先缺少 `regulator-allow-set-load`，regulator core 因 `REGULATOR_CHANGE_DRMS` 未开放而跳过 RPM 负载写入；DTS 已声明的 UFS `vcc=600 mA`、`vccq=450 mA`、`vccq2=450 mA` 实际没有生效。0019 只补这三个属性，regulator summary 随后确认三组负载均已下发。

这同时解释了故障特征：NOP 和 READ_DEVICE_DESC 等轻载操作可成功，而 `fDeviceInit` 的内部初始化和持续 NAND 写入进入高负载后掉链。trace 显示失败前 DME_LINKSTARTUP 与 NOP 均成功，SET_FLAG(fDeviceInit) 无响应；READ_DEVICE_DESC 能收到 `QUERY_RESP=0xF6 (NOT_READABLE)`，证明 QUERY 传输路径本身可用。

**最终最小验收镜像：`out/boot-va39-debian-screen52-regload-only.img`。**

- 启用：`0006` DMA32 retry、`0019` regulator load。
- 已删除：`0015` PHY 顺序补丁、`0016` dynamic gear 补丁。二者在源码上互相依赖：只应用 0015 会因残留 `goto out_disable_phy` 而编译失败；两者组合只是上游 v8 候选，不是本机必需。
- 仍禁用：0010 全关 PM、0012 完整校准、0013 E1、0014 common reset、0017 二次 startup、0018 QUERY 诊断。
- screen47 证明没有 0019 时 0015/0016 也不能修复冷启动；screen52 进一步证明去掉 0015/0016 后，0019 单独即可稳定冷启动和高负载写。

| 前态 | 镜像 | 枚举 / 挂载 | 真实写验收 |
|---|---|---|---|
| 完全断电冷启动，第 1 次 | screen50，no-PM | 全分区；userdata `rw` | cache 累计 1.25 GiB，约 130–135 MiB/s |
| 完全断电冷启动，第 1 次 | screen51，正常 PM | 全分区；journal recovery + `rw` | cache 1 GiB + idle 20 s 后再写 256 MiB；rootfs 另写 256 MiB |
| 完全断电冷启动，第 2 次 | screen51，正常 PM | 全分区；userdata `rw` | cache 256 MiB |
| 完全断电冷启动，第 1 次 | screen52，0019 only | 全分区；userdata `rw` | 256 MiB，119.2 MB/s |
| 完全断电冷启动，第 2 次 | screen52，0019 only | 全分区；userdata `rw` | 256 MiB，139.3 MB/s；另 1 GiB 持续写 137.0 MB/s，Dirty/Writeback=0 |
| Debian 热重启 | screen51，正常 PM | journal recovery + `rw` | cache 256 MiB |
| Android 热重启 | screen51，正常 PM | userdata `rw` | cache 256 MiB |
| TWRP 热重启 | screen51，正常 PM | userdata `rw` | cache 256 MiB |

以上写测均先满足 `test -b /dev/sda3` 或 `test -b /dev/sda9`，执行 `fsync/sync` 后无 `saved_uic_err`、DL replay、OCS invalid、EXT4 错误或块层卡死。RAM 中不存在块设备时禁止直接 `dd of=/dev/sdaN`，以免创建普通文件造成假通过。

后续历史章节保留用于说明排查路径；其中“待验证/未验收”的旧状态以本节为准。

## 1. 已验证事实（不是假设）

- 设备：Samsung `KLUCG4J1CB-B0B1`，UFS 2.0，单 lane，目标 HS-G3；HCI 版本为 2.0。
- 持续写先出现 `DL_TCx_REPLAY_ERROR`，随后 `OCS invalid from controller`，最后块层 tag 耗尽，shell/整机卡死。
- 顺序读正常；DMA 地址已在 4 GiB 内，故障不是简单的 >32-bit DMA。
- `0010-ufs-msm8996-no-pm-write-fix.patch` 同时关闭 clock gating、hibern8-with-clk-gating、clock scaling、WB-with-clock-scaling、aggressive power collapse、RPM autosuspend 后，128/256 MiB 写入 + `sync` 成功，`Dirty=0`、`Writeback=0`。
- screen38（只关 gating/hibern8）和 screen39（只关 scaling/aggressive/RPM 等）都仍失败。
- screen40 起 initramfs 已改为 `mount -o rw`，但冷启动 UFS probe 失败，journal replay 尚未验收。
- screen41 的 deferred-probe 已撤回：第二次 probe 使用旧 reset controller，触发悬垂指针 oops。
- screen42 的 `fDeviceInit` 前 100 ms 延迟无效；失败前已有 `PA_GENERIC_ERROR` / PA init 错误。
- screen43 已包含完整厂商 2.0.0 PHY 校准表、PCS 表及 SVS 后处理，尚未启动验证。

## 2. 对照源码

主线：`/home/claude/linux-msm8996`

- `drivers/ufs/host/ufs-qcom.c`
- `drivers/ufs/core/ufshcd.c`
- `drivers/phy/qualcomm/phy-qcom-qmp-ufs.c`
- `arch/arm64/boot/dts/qcom/msm8996.dtsi`

厂商：`/home/claude/x2_kernel/android_kernel_leeco_msm8996`

- `drivers/scsi/ufs/ufs-qcom.c`
- `drivers/scsi/ufs/ufshcd.c`
- `drivers/phy/phy-qcom-ufs.c`
- `drivers/phy/phy-qcom-ufs-qmp-14nm.[ch]`
- `arch/arm64/boot/dts/qcom/msm8996.dtsi`

## 3. 角度 A：PHY 上电、校准与冷启动 PA 错误

### A1. 首次 HCE 前存在一次厂商没有的 PHY 电源循环（高优先级）

主线调用链：

1. `ufs_qcom_init()` 末尾经 `ufs_qcom_setup_clocks(true, POST_CHANGE)` 执行 `phy_power_on()`。
2. 随后 `ufs_qcom_power_up_sequence()`（`ufs-qcom.c:487`）在 `phy->power_count` 非零时先 `phy_power_off()`。
3. 再执行 `phy_init()`、`phy_set_mode_ext()`、`phy_power_on()`、`phy_calibrate()`。

厂商在 variant init 上电后，HCE 路径只做 reset、calibrate、deassert reset、start serdes、等待 PCS ready，不做这次额外断电/重上电。

**假设**：x2 的 14 nm PHY 在这次额外 power collapse 后没有按厂商时序恢复，导致后续 DME/PA init 失败。  
**状态**：源码差异明确，尚未实机归因。100 ms `fDeviceInit` 延迟无效，说明不是单纯“设备晚就绪”。

### A2. 模拟断电前后缺 `QSERDES_COM_SW_RESET` 配对（高优先级）

厂商 `ufs_qcom_phy_qmp_14nm_power_control()`（`phy-qcom-ufs-qmp-14nm.c:116`）对 host 2.0.0 启用 `HIBERN8_EXIT_AFTER_PHY_PWR_COLLAPSE`：

- 断电前：`QSERDES_COM_SW_RESET = 1`，内存屏障，再清 `UFS_PHY_POWER_DOWN_CONTROL`。
- 上电后：先置 `UFS_PHY_POWER_DOWN_CONTROL`，再 `QSERDES_COM_SW_RESET = 0`。

主线 `qmp_ufs_power_off()`（`phy-qcom-qmp-ufs.c:1924`）只清 power-down、关 clocks/regulators；`qmp_ufs_power_on()`（`:1855`）只开 regulators/clocks、置 power-down，没有这对 common reset。

**覆盖范围**：既影响 A1 的首次多余断电，也影响后续每次 PM 模拟断电恢复。  
**状态**：源码差异明确，尚未移植验证。

### A3. 厂商校准表、PCS 和 SVS（已落入 screen43，待验收）

厂商 host 2.0.0 同时启用 SVS 和 VCO manual tuning。0012 已移植 serdes/TX/RX/PCS 表与 PCS ready 后 SVS 写序列。

VCO manual tuning 的厂商行为是“init 读取原值，calibrate 后恢复”；0012 当前保留表中的 `0xd6`，没有完整实现保存/恢复。厂商校准表本身也含 `0xd6`，因此不能预先认定这是错误，但真机原值尚未读取。

### A4. regulator/clock 顺序不同（中优先级）

厂商：`vdda_phy` → power-down 释放/common reset → `vdda_pll` → ref clk → 可选 `vddp_ref_clk`。  
主线：regulator bulk + clock bulk → 清 power-down。

若 A1/A2 单独修复无效，再对齐顺序；不建议第一轮同时改全部变量。

## 4. 角度 B：UniPro link startup 与设备 quirk

### B1. RX LineCfg post-link disable 在 x2 上不会执行（排除项）

厂商 `ufshcd_get_local_unipro_ver()`：HCI 1.0/1.1 返回 UniPro 1.41，其余返回 1.6。x2 是 HCI 2.0，因此走 UniPro 1.6：

- 厂商 post-link `if (local_unipro_ver == 1.41) disable RX LineCfg` **不会执行**。
- 厂商 pre-link TX LCC disable 与主线行为一致。

主线缺 post-link LineCfg 接口不是当前根因候选；pre-link 强制 enable 仅保留为低优先级检查，不值得先做大改。

### B2. Samsung quirk 差异不是首要方向

主线已有 Samsung `DELAY_BEFORE_LPM`、`HOST_PA_TACTIVATE`、`PA_HIBER8TIME`、`RECOVERY_FROM_DL_NAC_ERRORS`，Qcom 侧另有 HSG1 sync length 和 de-emphasis tuning。厂商旧表还有 `NO_VCCQ` / `NO_FASTAUTO`。

这些差异可能影响 LPM 或协商，但全关 PM 后写稳定，且 recovery quirk 只能处理已发生的 DL 错误，不能解释最初为何产生错误。因此优先级低于 host/PHY 电源路径。

## 5. 角度 C：PM、模拟断电与错误恢复

### C1. 普通 clock-off 被主线扩大成 PHY 模拟断电（最高优先级，写路径）

主线 `ufs_qcom_setup_clocks(false, PRE_CHANGE)`（`ufs-qcom.c:1194`）无条件执行 `phy_power_off()`；`POST_CHANGE(on=true)` 再 `phy_power_on()`。

厂商 `ufs_qcom_setup_clocks(false)`（`ufs-qcom.c:1293`）只关 iface/ref clock、device ref clock 和总线投票，**不调用 `phy_power_off()`**。厂商只有 `ufs_qcom_suspend()` 在 link off 或 link not active 时才关闭 PHY；link off 还 assert PHY soft reset。

这能统一解释 screen38/39：

- 只关 gating/hibern8 时，RPM/scaling 仍可能进入 clock-off → PHY power-off。
- 只关 scaling/aggressive/RPM 时，clock gating/hibern8 仍进入同一 PHY power-off。
- 两组各自都保留了一条模拟断电路径，所以两组都失败；全关才稳定。

**根因候选**：不是“六个 cap 天然都不能开”，而是它们共享的 `setup_clocks(false) → phy_power_off()` 对 x2 14 nm PHY 不安全。  
**最小修复方向**：msm8996 的普通 clock-gating 不做模拟断电；模拟断电只留在真正的 suspend 路径，并补厂商 reset/供电时序。

### C2. `no_phy_retention` 不是现成修复

主线该 drvdata 当前只用于 SM8550/SM8650，作用是把 `spm_lvl` 设为 `UFS_PM_LVL_5`；它不会修改 `setup_clocks(false)` 的无条件 `phy_power_off()`，不能直接套给 msm8996。

### C3. 错误恢复不是第一现场

主线 `ufshcd_host_reset_and_restore()` 会 stop HBA、重新 enable、重新 device init/probe；厂商 `full_reset` 的框架差异已被主线新架构替代。应先阻止第一次 DL replay/PA 错误，而不是给 tag 耗尽后的恢复继续叠 workaround。

## 6. 角度 D：DTS、时钟与供电

### D1. `vddp-ref-clk` 独立 always-on 缺失（PM 次要候选）

厂商 PHY：`vddp-ref-clk-supply = <&pm8994_l25>`，`vddp-ref-clk-always-on`。  
x2 主线没有该属性，QMP 驱动也没有独立 consumer；L25 只作为 `vccq` / `vdd-hba` 被引用。

generic `vccq` 在 variant/PHY init 前已上电，所以这**不能解释首次冷启动**。但 suspend/device rails 下电时，厂商会保持 refclk pad rail，主线可能随 L25 consumer 关闭，是后续恢复 PM 时要处理的差异。

### D2. UniPro core clock 上限不同（低优先级，已有负结果）

- 厂商 `core_clk_unipro`: 150–300 MHz。
- 主线 `core_clk_unipro`: 75–150 MHz。

此前改成厂商 150–300 MHz 未解决持续写，已撤回；它不是写故障的充分修复。若电源路径修复后仍有 PA/timer 异常，再单独复核。

### D3. 其余供电差异暂不动

`vcc` / `vccq` / `vccq2` 轨一致。DTS 的 `vdda-phy-max-microamp` 数值不同，但主线 QMP 使用固定 `init_load`；过请求电流通常不是 PA 错误根因。暂不作为首轮变量。

## 7. 根因候选排序

| 排名 | 候选 | 对应故障 | 证据强度 | 当前状态 |
|---|---|---|---|---|
| 1 | 普通 clock-off 无条件 `phy_power_off()` | 持续写、tag 耗尽 | 强：源码 + 三组 PM A/B 可统一解释 | 待最小补丁验证 |
| 2 | 首次 HCE 前额外 PHY 断电/重上电 | 冷启动 PA generic/init | 强：厂商无此循环 | 待最小补丁验证 |
| 3 | 模拟断电缺 common reset 配对 | 冷启动 + PM 恢复 | 强：厂商 2.0.0 专用 quirk | 待移植验证 |
| 4 | 完整校准/PCS/SVS 差异 | 冷启动/链路裕量 | 中：寄存器差异明确 | screen43 待测 |
| 5 | regulator/clock 顺序、`vddp-ref-clk` 保持 | PM 恢复为主 | 中 | 后续单独对齐 |
| 6 | RX LineCfg post-disable | 无 | 已排除：x2 走 UniPro 1.6 | 不做首轮实验 |

## 8. 最小实验序列（每次只回答一个问题）

### E0：关闭 screen43 的悬而未决项

使用现有 `out/boot-va39-debian-screen43.img`，不再新增变量。

验收：

1. 冷启动无 `fDeviceInit -5`、无新增 PA generic/init 错误，能看到 `sda`。
2. `/data` 以 `rw` 挂载，journal replay 真正完成。
3. no-PM 下对 cache 做 256 MiB 写 + `sync`，`Dirty=0`、`Writeback=0`，无新增 UIC/OCS。

结果只回答“完整校准/SVS 是否足够”；不把它当作 PM 根治。

### E1：只移除首次 HCE 前的多余 PHY 电源循环

若 E0 仍冷启动失败，在 `ufs_qcom_power_up_sequence()` 对 host 2.x/msm8996 保留已上电 PHY，不执行第二次 off/on；其余 init/mode/calibrate 顺序不变。

验收同 E0 的冷启动项。成功才能说“多余电源循环是冷启动根因”。

### E2：只补 14 nm common reset 配对

若仍需 power collapse，在 msm8996 QMP `power_off/on` 前后加入厂商 `QSERDES_COM_SW_RESET` 配对，不与 DTS、时钟表或其它 quirk 同改。

验收：冷启动与一次明确的 PHY power-cycle 后链路均可恢复。

### E3：验证持续写的共享根因

在 no-PM 基线上：

1. msm8996 `setup_clocks(false)` 不再做 PHY 模拟断电。
2. 只重新启用 clock gating + hibern8-with-clk-gating；scaling/aggressive/RPM 仍关闭。
3. cache 连续写 256 MiB、1 GiB并 `sync`，再做 userdata journal replay/apt 写负载。

稳定即证明“gating 本身可开，错误的是把 gating 扩大成模拟断电”。失败则保留 no-PM 并回到寄存器/时钟证据，不继续盲目组合 cap。

### E4：最后恢复真正的 suspend/runtime PM

在 E2/E3 结论上，把模拟断电限制到 link not active 的 suspend 路径，补 link-off PHY soft reset 与 `vddp-ref-clk` 保持，再逐项恢复 RPM/scaling/aggressive。每项都要经过写 + `sync` + 多轮 suspend/resume，不能一次全开。

## 9. 当前边界

- 不删除 Android，不重分区 system/userdata；双系统共存保持不变。
- 不再使用 deferred-probe、原地 retry、`swiotlb=force` 或长期全关 PM 冒充根因修复。
- 本轮只完成静态分析与文档，不改补丁、不构建、不刷机。
- 在任何 E0–E4 实测前，以上根因排序均是“有源码证据的候选”，不是已宣布修复。
