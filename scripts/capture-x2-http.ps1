param(
    [string]$OutDir = 'G:\LeEco-Max2\leeco-x2-linux\out\logs'
)

$ErrorActionPreference = 'SilentlyContinue'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$base = 'http://192.168.42.1:8080'
$powerLatest = Join-Path $OutDir "x2-http-power-$stamp.log"
$dmesgLatest = Join-Path $OutDir "x2-http-dmesg-$stamp.log"
$kmsgCopy = Join-Path $OutDir "x2-http-kmsg-$stamp.log"
$statusLatest = Join-Path $OutDir "x2-http-status-$stamp.txt"

while ($true) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$base/status"
        $r.Content | Out-File -Encoding utf8 $statusLatest
    } catch {}
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$base/power.log" -OutFile "$powerLatest.tmp"
        Move-Item -Force "$powerLatest.tmp" $powerLatest
    } catch {}
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "$base/dmesg-live.log" -OutFile "$dmesgLatest.tmp"
        Move-Item -Force "$dmesgLatest.tmp" $dmesgLatest
    } catch {}
    if (-not (Test-Path $kmsgCopy)) {
        try {
            Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "$base/kmsg.log" -OutFile "$kmsgCopy.tmp"
            Move-Item -Force "$kmsgCopy.tmp" $kmsgCopy
        } catch {}
    }
    Start-Sleep -Milliseconds 1000
}
