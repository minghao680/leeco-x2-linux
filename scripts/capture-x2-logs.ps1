param(
    [string]$OutDir = 'G:\LeEco-Max2\leeco-x2-linux\out\logs'
)

$ErrorActionPreference = 'SilentlyContinue'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$dmesgLog = Join-Path $OutDir "x2-dmesg-$stamp.log"
$powerLog = Join-Path $OutDir "x2-power-$stamp.log"
$ssh = 'C:\Windows\System32\OpenSSH\ssh.exe'
$askpass = 'G:\LeEco-Max2\leeco-x2-linux\scripts\.tmp-askpass.bat'
$target = 'root@192.168.42.1'
$opts = @(
    '-o','StrictHostKeyChecking=no',
    '-o','UserKnownHostsFile=NUL',
    '-o','PreferredAuthentications=password',
    '-o','PubkeyAuthentication=no',
    '-o','ConnectTimeout=4',
    '-o','ServerAliveInterval=10',
    '-o','ServerAliveCountMax=2'
)

$env:SSH_ASKPASS = $askpass
$env:SSH_ASKPASS_REQUIRE = 'force'

$dmesgJob = Start-Job -ScriptBlock {
    param($ssh, $opts, $target, $log)
    while ($true) {
        "=== reconnect $(Get-Date -Format o) ===" | Out-File -Append -Encoding utf8 $log
        & $ssh @opts $target 'dmesg -w' 2>&1 | Out-File -Append -Encoding utf8 $log
        Start-Sleep -Seconds 2
    }
} -ArgumentList $ssh, $opts, $target, $dmesgLog

$powerJob = Start-Job -ScriptBlock {
    param($ssh, $opts, $target, $log)
    $cmd = 'while true; do printf "%s " "$(date +%s)"; cat /sys/class/power_supply/qcom-battery/voltage_now 2>/dev/null; cat /sys/class/power_supply/qcom-battery/current_now 2>/dev/null; cat /sys/class/power_supply/qcom-battery/capacity 2>/dev/null; cat /proc/uptime 2>/dev/null; sleep 1; done'
    while ($true) {
        "=== reconnect $(Get-Date -Format o) ===" | Out-File -Append -Encoding utf8 $log
        & $ssh @opts $target $cmd 2>&1 | Out-File -Append -Encoding utf8 $log
        Start-Sleep -Seconds 2
    }
} -ArgumentList $ssh, $opts, $target, $powerLog

"dmesg log: $dmesgLog"
"power log: $powerLog"
Wait-Job -Job $dmesgJob, $powerJob
