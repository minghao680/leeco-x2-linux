# ADSP / `qcom_q6v5_pas` 启动锁死

日期：2026-11-20

## 结论

`qcom_q6v5_pas`（ADSP 的 PAS remoteproc 驱动）在 MSM8996 / Le Max 2 主线上启动时会把系统锁死：
CPU1 hard LOCKUP，随后 RPM SMD 和 UFS 带宽请求超时。该问题与 Adreno GPU、0029 补丁、电池
供电都无关。

**临时绕过**：内核 cmdline 加入

```text
module_blacklist=rmtfs_mem,qcom_q6v5_pas,qcom_q6v5_adsp
```

GPU/显示/WiFi/蓝牙/UFS 都不依赖 ADSP；音频和部分传感器（SSC/SLPI）以后需要，到阶段 G/音频
bring-up 时再修。

## 复现证据

1. 最小诊断 initramfs（不启动 systemd、不 chroot、不加载 WiFi）稳定运行 300 秒以上：
   - 电池 `voltage_now ≈ 4.03 V`、`current_now ≈ 300 mA`、`capacity 70%`
   - HTTP/telnet 正常，`/proc/uptime` 持续增长
2. 在同一最小系统里手动执行：

   ```sh
   busybox chroot /data/debian/root /sbin/modprobe qcom_q6v5_pas
   ```

   命令打印 `MODPROBE_DONE` 后，下一条 `cat /proc/uptime` 不再返回，HTTP/telnet 全部断掉。
   说明锁死是 ADSP 驱动 probe/加载触发的，不是 systemd 或 WiFi 本身。
3. production（systemd18/0029）启动日志：

   ```text
   [44.126692] remoteproc remoteproc0: adsp is available
   [44.129041] remoteproc remoteproc0: powering up adsp
   [44.129101] remoteproc remoteproc0: Booting fw image adsp.mdt, size 7196
   [49.645055] msm: dual display: attempt 4: -11
   [57.837054] msm: dual display: attempt 5: -11
   [60.012880] watchdog: CPU0: Watchdog detected hard LOCKUP on cpu 1
   [67.564903] qcom_icc_rpm_smd_send slv 143 error -110
   [70.027613] ufshcd-qcom 624000.ufshc: failed to set bandwidth request: -110
   ```

   `adsp.mdt` 只有 7196 B，是固件清单/头，不是完整镜像；后面 `adsp.b00...` 段没有看到成功加载
   或 ADSP ready 的回执。

## 驱动是做什么的

- `qcom_q6v5_pas`：Q6v5 Hexagon DSP 的 remoteproc 驱动，通过 Qualcomm PAS
  （Peripheral Authentication Service）走 SCM 认证并加载固件，释放 ADSP 复位，等待 handshake。
- `qcom_q6v5`：Q6v5 核心状态/复位/SMP2P 支持。
- `qcom_sysmon`：子系统事件通知。
- ADSP 在 Android 上主要跑音频、传感器（SSC/SLPI）、语音和低功耗算法；不参与 Adreno GPU。

## 待查项

1. DTS 的 `adsp` / `remoteproc` 节点是否完整：
   - `qcom,pas-id`（ADSP 的 PAS ID）
   - `memory-region` / PIL carveout
   - `qcom,smem-states`、`qcom,smem-state-names`
   - `qcom,halt-regs`
   - `qcom,glink-edge` / SMP2P 中断
   - ADSP 所需 clocks、power-domains、regulators
2. 固件段是否齐全：`adsp.mdt`、`adsp.b00`…`adsp.b0x` 的实际大小/版本，是否与 MSM8996 ADSP 匹配。
3. SCM/PAS 调用是否返回、卡在 auth、reset 还是 wait-for-ready。
4. 与 vendor 3.18 内核的 `adsp` DTS、`qcom_q6v5_pas` / `adsp_loader` 实现逐项对比。
5. RPM SMD（`qcom_icc_rpm_smd_send slv 143 -110`）是 ADSP 挂死后的 Secondary 现象，还是
   RPM 本身也被影响；需要 ADSP 不启动时的基线对照。

## 相关文件

- 最小诊断 initramfs：`out/x2-initramfs-debug-minimal.gz`
- 最小诊断镜像：`out/boot-x2-debug-minimal.img`
- no-ADSP 稳定镜像（systemd18 内核）：
  `out/boot-x2-debian-systemd18-noadsp-clean.img`
- 持久 kmsg：`/data/debian/logs/kmsg.log`（设备侧）
- 已抓回主机：`out/logs/x2-http-kmsg-20261120-110136.log`
- HTTP/电池抓取脚本：`scripts/capture-x2-http.ps1`
- SSH dmesg/电池抓取脚本：`scripts/capture-x2-logs.ps1`
