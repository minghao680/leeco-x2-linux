#requires -Version 7
<#
Extract the x2 firmware/calibration set from the local partition backups.

The proprietary blobs are intentionally written under out/ (gitignored), never
into the repository. The resulting bundle has two layers:

  stage/      files that the current mainline Debian boot actually consumes
  reference/  untouched vendor/modem/persist material kept for future drivers

Usage:
  pwsh -File scripts/extract-x2-firmware.ps1
  pwsh -File scripts/extract-x2-firmware.ps1 -BackupDir G:\other\backup
#>
param(
    [string]$BackupDir = 'G:\LeEco-Max2\backup\x2-partitions-20261112\pmos-backup',
    [string]$OutDir = 'G:\LeEco-Max2\leeco-x2-linux\out\x2-firmware'
)

$ErrorActionPreference = 'Stop'
$Wsl = 'C:\Windows\System32\wsl.exe'
$SevenZip = 'C:\Program Files\7-Zip\7z.exe'

foreach ($tool in @($Wsl, $SevenZip)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "required tool missing: $tool"
    }
}

function ConvertTo-WslPath([string]$Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "not a Windows drive path: $Path"
    }
    $drive = $Matches[1].ToLowerInvariant()
    $rest = $Matches[2] -replace '\\', '/'
    return "/mnt/$drive/$rest"
}

function Invoke-Debugfs([string]$Image, [string]$Command) {
    $wslImage = ConvertTo-WslPath $Image
    $output = & $Wsl -e /usr/sbin/debugfs -R $Command $wslImage 2>&1
    $code = $LASTEXITCODE
    # debugfs tries to restore vendor uid/gid on drvfs. Windows rejects chown,
    # but file contents are already written correctly. Ignore only that warning.
    $realErrors = @($output | Where-Object {
        $_ -notmatch '^debugfs [0-9]' -and
        $_ -notmatch 'Operation not permitted while changing ownership'
    })
    if ($code -ne 0) {
        throw "debugfs failed for $Image ($Command): $($realErrors -join '; ')"
    }
    if ($realErrors.Count -gt 0) {
        Write-Warning ($realErrors -join '; ')
    }
}

function Invoke-DebugfsDump([string]$Image, [string]$Source, [string]$Destination) {
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Force
    }
    Invoke-Debugfs $Image ("dump $Source " + (ConvertTo-WslPath $Destination)) | Out-Null
    if (-not (Test-Path -LiteralPath $Destination)) {
        throw "debugfs did not create $Destination"
    }
}

function Invoke-SevenZip {
    param(
        [string]$Image,
        [string]$Destination,
        [string[]]$Patterns,
        [switch]$AllowTruncated
    )
    $args = @('x', '-y', "-o$Destination", $Image) + $Patterns
    $output = & $SevenZip @args 2>&1
    $code = $LASTEXITCODE
    # The old bluetooth.img backup is 1 MiB while its FAT header claims 1 GiB.
    # 7-Zip still extracts every real file but reports a truncated archive (2).
    if ($code -ne 0 -and -not ($AllowTruncated -and $code -eq 2)) {
        throw "7-Zip failed for $Image (exit $code): $($output -join '; ')"
    }
    if ($AllowTruncated -and $code -eq 2) {
        foreach ($name in @('image\btfw32.tlv', 'image\btnv32.bin', 'image\btnv32.b15')) {
            if (-not (Test-Path -LiteralPath (Join-Path $Destination $name))) {
                throw "truncated archive $Image did not yield $name"
            }
        }
    }
}

$VendorImage = Join-Path $BackupDir 'vendor.img'
$ModemImage = Join-Path $BackupDir 'modem.img'
$BluetoothImage = Join-Path $BackupDir 'bluetooth.img'
$PersistImage = Join-Path $BackupDir 'persist.img'
$DspImage = Join-Path $BackupDir 'dsp.img'
foreach ($image in @($VendorImage, $ModemImage, $BluetoothImage, $PersistImage)) {
    if (-not (Test-Path -LiteralPath $image)) {
        throw "backup image missing: $image"
    }
}

$Reference = Join-Path $OutDir 'reference'
$Stage = Join-Path $OutDir 'stage'
New-Item -ItemType Directory -Force -Path $Reference,$Stage | Out-Null

# Vendor ext4: GPU firmware, OEM zaps, audio/camera/CCG blobs.
$VendorRef = Join-Path $Reference 'vendor'
New-Item -ItemType Directory -Force -Path $VendorRef | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $VendorRef 'firmware\a530_pm4.fw'))) {
    Invoke-Debugfs $VendorImage ("rdump /firmware " + (ConvertTo-WslPath $VendorRef)) | Out-Null
}

# Modem FAT image: ADSP, SLPI, Venus, modem, secure apps and board data.
$ModemRef = Join-Path $Reference 'modem'
Invoke-SevenZip $ModemImage $ModemRef @('image\*')

# Bluetooth partition: stock rampatch/NVM blobs, kept as reference because the
# mainline btqca driver currently consumes linux-firmware's qca/ files instead.
$BluetoothRef = Join-Path $Reference 'bluetooth'
Invoke-SevenZip $BluetoothImage $BluetoothRef @('image\bt*') -AllowTruncated

# Persistent calibration / identity data. Never publish this to GitHub.
$PersistRef = Join-Path $Reference 'persist'
New-Item -ItemType Directory -Force -Path $PersistRef | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $PersistRef 'sensors\sns.reg'))) {
    Invoke-Debugfs $PersistImage ("rdump /sensors " + (ConvertTo-WslPath $PersistRef)) | Out-Null
}
Invoke-DebugfsDump $PersistImage '/bluetooth/.bt_nv.bin' (Join-Path $PersistRef 'bluetooth\.bt_nv.bin')
Invoke-DebugfsDump $PersistImage '/wlan_mac.bin' (Join-Path $PersistRef 'wlan_mac.bin')

if (Test-Path -LiteralPath $DspImage) {
    $DspRef = Join-Path $Reference 'dsp'
    Invoke-SevenZip $DspImage $DspRef @('*')
}

# Everything below is consumed by the current kernel/rootfs layout.
# Debian is usr-merged: /lib is a symlink to usr/lib.  Stage the bundle under
# usr/lib/firmware so extracting it can never replace the /lib symlink with a
# real directory (which would also hide the dynamic loader).
$FirmwareStage = Join-Path $Stage 'usr\lib\firmware'
$QcomStage = Join-Path $FirmwareStage 'qcom'
$ZapStage = Join-Path $QcomStage 'msm8996\leeco-x2'
$QcaStage = Join-Path $FirmwareStage 'ath10k\QCA6174\hw3.0'
$ModemImageDir = Join-Path $ModemRef 'image'
$VendorFirmwareDir = Join-Path $VendorRef 'firmware'
New-Item -ItemType Directory -Force -Path $FirmwareStage,$QcomStage,$ZapStage,$QcaStage | Out-Null

# Adreno 530: driver requests qcom/a530_*. The zap shader is board-specific and
# is requested at qcom/msm8996/leeco-x2/a530_zap.mdt by the x2 DTS.
foreach ($name in @('a530_pm4.fw', 'a530_pfp.fw', 'a530_gpmu.fw2', 'a530v3_gpmu.fw2')) {
    Copy-Item -LiteralPath (Join-Path $VendorFirmwareDir $name) -Destination $QcomStage -Force
}
foreach ($name in @('a530_zap.mdt', 'a530_zap.b00', 'a530_zap.b01', 'a530_zap.b02')) {
    Copy-Item -LiteralPath (Join-Path $VendorFirmwareDir $name) -Destination $ZapStage -Force
}

# ADSP and SLPI are split-image (mdt + bNN) firmware. The current x2 DTS does
# not override adsp_pil's firmware-name, so the ADSP driver asks for plain
# "adsp.mdt"; SLPI uses the same convention if enabled later.
foreach ($prefix in @('adsp', 'slpi')) {
    Get-ChildItem -LiteralPath $ModemImageDir -File |
        Where-Object { $_.Name -match "^$prefix\.(mdt|b[0-9a-f]{2})$" } |
        ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $FirmwareStage -Force
        }
}

# TFA9890 SmartPA tuning data (only useful once a mainline TFA9890 driver exists).
$Tfa = Join-Path $VendorFirmwareDir 'tfa98xx.cnt'
if (Test-Path -LiteralPath $Tfa) {
    Copy-Item -LiteralPath $Tfa -Destination $FirmwareStage -Force
}

# Android-extracted QCA6174 board data. Keep both names required by ath10k:
# board.bin and the PCI-path-specific board-pci-0000:01:00.0.bin.
$BoardData = Join-Path $PSScriptRoot '..\firmware\qca6174\bdwlan30.bin'
Copy-Item -LiteralPath $BoardData -Destination (Join-Path $QcaStage 'board.bin') -Force
# Win32 cannot create a filename containing ':', but Linux and NTFS can. Use
# WSL for this one so the staged name matches ath10k's requested path exactly.
& $Wsl -e cp -f (ConvertTo-WslPath $BoardData) `
    (ConvertTo-WslPath (Join-Path $QcaStage 'board-pci-0000:01:00.0.bin'))
if ($LASTEXITCODE -ne 0) {
    throw 'failed to create QCA6174 PCI board filename'
}

# Build a checksum manifest and a rootfs tarball for later scp/SSH deployment.
# Paths are usr/lib/firmware/... on purpose (see usr-merged note above).
# The manifest generator runs inside WSL so Linux-only filenames are preserved.
$Manifest = Join-Path $OutDir 'manifest.tsv'
$ManifestPy = Join-Path $PSScriptRoot 'firmware-manifest.py'
& $Wsl -e python3 (ConvertTo-WslPath $ManifestPy) `
    (ConvertTo-WslPath $Stage) (ConvertTo-WslPath $Manifest)
if ($LASTEXITCODE -ne 0) {
    throw 'failed to create firmware manifest'
}

$Tarball = Join-Path $OutDir 'x2-firmware-rootfs.tar.gz'
& $Wsl -e tar -C (ConvertTo-WslPath $Stage) -czf (ConvertTo-WslPath $Tarball) .
if ($LASTEXITCODE -ne 0) {
    throw 'failed to create rootfs firmware tarball'
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'install-x2-firmware.sh') `
    -Destination (Join-Path $OutDir 'install.sh') -Force

Write-Output "firmware bundle: $OutDir"
Write-Output "rootfs tarball:  $Tarball"
Write-Output "manifest:        $Manifest"
