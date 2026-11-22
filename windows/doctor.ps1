[CmdletBinding()]
param()
$ErrorActionPreference = 'Continue'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'yt-essential'
$Python = Join-Path $InstallRoot 'venv\Scripts\python.exe'

Write-Host 'yt-dlp-essential — Windows diagnostics' -ForegroundColor Cyan
Write-Host "OS: $([Environment]::OSVersion.VersionString)"
Write-Host "PowerShell: $($PSVersionTable.PSVersion)"
Write-Host "Architecture: $env:PROCESSOR_ARCHITECTURE"
Write-Host "Install root: $InstallRoot"
Write-Host "Config: $env:APPDATA\yt-essential\config.json"

foreach ($tool in @('python.exe', 'ffmpeg.exe', 'ffprobe.exe', 'deno.exe', 'node.exe', 'winget.exe')) {
    $found = Get-Command $tool -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { Write-Host "[OK] $tool -> $($found.Source)" -ForegroundColor Green }
    else { Write-Host "[MISSING] $tool" -ForegroundColor Yellow }
}

$failed = $false
if (Test-Path -LiteralPath $Python) {
    & $Python -X utf8 -c "import sys,yt_essential,yt_dlp,gallery_dl; print('venv Python:',sys.version.split()[0]); print('essential:',yt_essential.__version__); print('yt-dlp:',yt_dlp.version.__version__); print('gallery-dl: OK')"
    if ($LASTEXITCODE -ne 0) {
        Write-Host '[ERROR] Проверка Python-пакетов не пройдена.' -ForegroundColor Red
        $failed = $true
    }
    else {
        & $Python -X utf8 -c "from yt_essential.windows_compat import config_directory,default_download_directory; print('config:',config_directory()); print('downloads:',default_download_directory())"
        if ($LASTEXITCODE -ne 0) { $failed = $true }
    }
}
else {
    Write-Host '[MISSING] Виртуальное окружение. Выполните windows\install.ps1.' -ForegroundColor Yellow
    $failed = $true
}
if ($failed) { exit 1 }
exit 0
