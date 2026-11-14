# boot-test.ps1 — full lk2nd boot + ramoops readback loop for the x2
# (PowerShell port of scripts/boot-test.sh; WSL bash cannot see Windows USB)
param(
	[Parameter(Mandatory=$true)][string]$Boot,
	[string]$Lk2nd,
	[string]$Serial = "33470699"
)
$ErrorActionPreference = "Continue"
if (-not $Lk2nd) { throw "usage: boot-test.ps1 <boot.img> <lk2nd.img>" }

function Wait-Fastboot([int]$Seconds = 40) {
	for ($i = 0; $i -lt $Seconds; $i++) {
		$devs = (& fastboot devices 2>$null)
		if ($devs -match $Serial) { return $true }
		Start-Sleep -Seconds 1
	}
	return $false
}
function Product {
	(& fastboot getvar product 2>&1 | Select-String 'product:') -replace '.*product:\s*', ''
}

Write-Host "== [1/6] reboot to bootloader =="
$adbDevs = (& adb devices 2>$null) -join ' '
if ($adbDevs -match $Serial) { & adb -s $Serial reboot bootloader }
if (-not (Wait-Fastboot 60)) { Write-Host "FATAL: no fastboot device"; exit 1 }
Write-Host ("   stock product: " + (Product))

Write-Host "== [2/6] boot lk2nd (memory only) =="
& fastboot boot "$Lk2nd" 2>&1 | Out-Null
Start-Sleep -Seconds 5
if (-not (Wait-Fastboot 30)) { Write-Host "FATAL: lk2nd did not come up"; exit 1 }
$lk2ndProduct = Product
Write-Host ("   lk2nd product: " + $lk2ndProduct)
if ($lk2ndProduct -notmatch 'lk2nd') { Write-Host "FATAL: product is not lk2nd"; exit 1 }

Write-Host "== [3/6] boot kernel (panic=15 auto-reboots on panic) =="
& fastboot boot "$Boot" 2>&1 | Select-String 'OKAY|FAILED' | ForEach-Object { "   $_" }
Write-Host "   waiting up to 90s for crash-reboot..."
$back = $false
for ($i = 1; $i -le 45; $i++) {
	Start-Sleep -Seconds 2
	if (Wait-Fastboot 1) { Write-Host ("   back at t=$($i*2)s"); $back = $true; break }
}
if (-not $back) { Write-Host "   device did not come back in 90s" }
Write-Host ("   product after kernel: " + (Product))

Write-Host "== [4/6] re-enter lk2nd =="
& fastboot boot "$Lk2nd" 2>&1 | Out-Null
Start-Sleep -Seconds 5
if (-not (Wait-Fastboot 30)) { Write-Host "FATAL: lk2nd did not come up"; exit 1 }
Write-Host ("   lk2nd product: " + (Product))

Write-Host "== [5/6] fetch ramoops console =="
& fastboot oem ramoops console 2>&1 | Select-Object -First 2 | ForEach-Object { "   $_" }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logfile = "console-$stamp.log"
& fastboot get_staged $logfile 2>&1 | Select-Object -Last 1 | ForEach-Object { "   $_" }
if (Test-Path $logfile) {
	$size = (Get-Item $logfile).Length
	Write-Host ("   log saved: $logfile ($size bytes)")
	if ($size -gt 0) {
		Write-Host "   first lines:"
		Get-Content $logfile -TotalCount 8 | ForEach-Object { "   | $_" }
	}
} else {
	Write-Host "   no staged log; try 'oem ramoops regions'"
}
Write-Host "== [6/6] done =="
