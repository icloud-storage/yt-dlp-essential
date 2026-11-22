[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'yt-essential'
$VenvPython = Join-Path $InstallRoot 'venv\Scripts\python.exe'
$PackageDir = Join-Path $InstallRoot 'venv\Lib\site-packages\yt_essential'
$CompatSource = Join-Path $PSScriptRoot 'yt_essential_windows.py'
$CompatTarget = Join-Path $PackageDir 'windows_compat.py'
$InstalledCopy = Join-Path $InstallRoot 'windows\yt_essential_windows.py'

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "Python virtual environment not found: $VenvPython. Install yt-dlp-essential first."
}
if (-not (Test-Path -LiteralPath $CompatSource -PathType Leaf)) {
    throw "Windows compatibility module not found: $CompatSource"
}
if (-not (Test-Path -LiteralPath $PackageDir -PathType Container)) {
    throw "yt_essential package not found: $PackageDir"
}

# Update the runtime module and the saved adapter copy used by future repair/update tasks.
Copy-Item -LiteralPath $CompatSource -Destination $CompatTarget -Force
$InstalledWindowsDir = Split-Path -Parent $InstalledCopy
if (Test-Path -LiteralPath $InstalledWindowsDir -PathType Container) {
    Copy-Item -LiteralPath $CompatSource -Destination $InstalledCopy -Force
}

& $VenvPython -X utf8 -m py_compile $CompatTarget
if ($LASTEXITCODE -ne 0) {
    throw 'Python could not compile the Windows compatibility module.'
}

$proxyCheck = & $VenvPython -X utf8 -c "from yt_essential.windows_compat import detect_ffmpeg_http_proxy; print('HTTP(S) proxy detected:', bool(detect_ffmpeg_http_proxy()))"
if ($LASTEXITCODE -ne 0) {
    throw 'Could not verify HTTP(S) proxy detection.'
}
Write-Host $proxyCheck

Write-Host '[OK] Windows compatibility module updated.' -ForegroundColor Green
Write-Host 'The configured HTTP(S) proxy will be forwarded to the FFmpeg input downloader.'
Write-Host 'Close ESSENTIAL completely and start it again before testing.'
