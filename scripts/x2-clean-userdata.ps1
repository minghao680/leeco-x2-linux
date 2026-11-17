# 清 userdata 的 ext4 journal，供主线 Debian 用 -- 需手机已在 TWRP recovery。
# 用法：  pwsh -File scripts\x2-clean-userdata.ps1            # 只检查（e2fsck -fn）
#         pwsh -File scripts\x2-clean-userdata.ps1 -Fix     # 实际修复（e2fsck -fp）
param(
    [switch]$Fix,
    [string]$Serial = "33470699",
    [string]$Adb = "C:\Program Files\UotanToolbox\Bin\platform-tools\adb.exe"
)

if (-not (Test-Path -LiteralPath $Adb)) { throw "adb not found: $Adb" }

$state = & $Adb -s $Serial get-state 2>$null
if ($LASTEXITCODE -ne 0 -or $state -ne "recovery") {
    throw "device $Serial is not in recovery (state=$state). Boot TWRP first."
}

& $Adb -s $Serial shell "umount /sdcard; umount /data; sync; grep -c userdata /proc/mounts"
if ($LASTEXITCODE -ne 0) { throw "unmount /data failed" }

$fsckFlag = if ($Fix) { "-fp" } else { "-fn" }
$out = & $Adb -s $Serial shell "/sbin/e2fsck $fsckFlag /dev/block/bootdevice/by-name/userdata 2>&1 | tail -8"
$out | ForEach-Object { $_.TrimEnd() }
if ($LASTEXITCODE -ne 0) { throw "e2fsck failed; check output above" }

$incompat = (& $Adb -s $Serial shell "dd if=/dev/block/bootdevice/by-name/userdata bs=1024 skip=1 count=1 2>/dev/null | od -An -tx4 -j96 -N4").Trim()
$recoverBit = 0x4
$value = [Convert]::ToInt32(($incompat -replace "0x", ""), 16)
if ($value -band $recoverBit) {
    Write-Output "incompat=$incompat -> RECOVER still set; do NOT boot mainline yet (run with -Fix?)"
    exit 1
}
Write-Output "incompat=$incompat -> RECOVER clear; safe to Reboot -> Bootloader"
