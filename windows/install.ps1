[CmdletBinding()]
param(
    [string]$SourcePath = "",
    [switch]$SkipSystemDependencies,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA 'yt-essential'
$VenvPath = Join-Path $InstallRoot 'venv'
$SourceDir = Join-Path $InstallRoot 'source'
$BinDir = Join-Path $InstallRoot 'bin'
$LogRoot = Join-Path $env:APPDATA 'yt-essential\logs'

function Write-Section([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}
function Write-Ok([string]$Message) { Write-Host "  [OK] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "  [!]  $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { throw $Message }

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPathNow = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machinePath, $userPathNow, $env:Path) -join ';'
}

function Add-UserPathEntry([string]$Entry) {
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @($current -split ';' | Where-Object { $_ -and $_.TrimEnd('\') -ne $Entry.TrimEnd('\') })
    $parts += $Entry
    [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}

function Remove-UserPathEntry([string]$Entry) {
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @($current -split ';' | Where-Object { $_ -and $_.TrimEnd('\') -ne $Entry.TrimEnd('\') })
    [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}

function Test-PythonCandidate([string]$Candidate) {
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
    $probe = & $Candidate -c "import struct,sys; print('%d|%d|%s' % (sys.version_info.major,sys.version_info.minor,struct.calcsize('P')*8))" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $probe) { return $false }
    $parts = $probe.Trim() -split '\|'
    if ($parts.Count -ne 3) { return $false }
    $version = ([int]$parts[0] * 100) + [int]$parts[1]
    return ($version -ge 310 -and [int]$parts[2] -eq 64)
}

function Find-Python {
    $candidates = New-Object System.Collections.Generic.List[string]

    # The Python Launcher gives concrete interpreter paths even when PATH is stale.
    $pyLauncher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $listed = & $pyLauncher.Source -0p 2>$null
        foreach ($line in $listed) {
            if ($line -match '(?i)([A-Z]:\\.*?python(?:\.exe)?)\s*$') {
                $candidates.Add($Matches[1].Trim())
            }
        }
    }

    foreach ($commandName in @('python.exe', 'python3.exe')) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command -and $command.Source) { $candidates.Add($command.Source) }
    }

    foreach ($base in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        (Join-Path $env:ProgramFiles 'Python'),
        (Join-Path $env:ProgramFiles 'Python314'),
        (Join-Path $env:ProgramFiles 'Python313'),
        (Join-Path $env:ProgramFiles 'Python312'),
        (Join-Path ${env:ProgramFiles(x86)} 'Python')
    )) {
        if ($base -and (Test-Path -LiteralPath $base)) {
            Get-ChildItem -LiteralPath $base -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue |
                ForEach-Object { $candidates.Add($_.FullName) }
        }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-PythonCandidate $candidate) { return $candidate }
    }
    return $null
}

function Invoke-WinGetInstall([string]$PackageId, [string]$DisplayName) {
    $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Warn "WinGet не найден. Автоматическая установка $DisplayName пропущена. Установите App Installer из Microsoft Store или установите компонент вручную."
        return $false
    }
    Write-Section "Установка $DisplayName через WinGet"
    # `winget install` does not accept `--upgrade`; upgrades are a separate command.
    # Pin the community source to avoid ambiguity when package IDs overlap.
    & $winget.Source install --exact --id $PackageId --source winget --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "WinGet вернул код $LASTEXITCODE при установке $DisplayName. Продолжаю проверку; при необходимости установите компонент вручную."
        return $false
    }
    Refresh-ProcessPath
    Write-Ok "${DisplayName}: установщик WinGet завершился успешно"
    return $true
}

function Ensure-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Install-ProjectSource {
    param([string]$LocalSource)

    $stage = Join-Path $InstallRoot 'source-staging'
    $zipPath = Join-Path $InstallRoot 'source.zip'
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    Ensure-Directory $stage

    if ($LocalSource) {
        $resolved = (Resolve-Path -LiteralPath $LocalSource).Path
        if (-not (Test-Path -LiteralPath (Join-Path $resolved 'pyproject.toml'))) {
            Write-Fail "В SourcePath не найден pyproject.toml: $resolved"
        }
        Write-Section "Подготовка локального исходного кода"
        Get-ChildItem -LiteralPath $resolved -Force | Where-Object { $_.Name -notin @('.git', '.venv', 'venv', '__pycache__') } | Copy-Item -Destination $stage -Recurse -Force
    }
    else {
        Write-Section 'Загрузка исходного кода оригинального проекта'
        $url = 'https://github.com/icloud-storage/yt-dlp-essential/archive/refs/heads/main.zip'
        try {
            Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing
            Expand-Archive -LiteralPath $zipPath -DestinationPath $stage -Force
        }
        catch {
            Write-Fail "Не удалось загрузить исходники GitHub. Проверьте интернет/доступ к github.com. Подробности: $($_.Exception.Message)"
        }
        $extracted = Get-ChildItem -LiteralPath $stage -Directory | Select-Object -First 1
        if (-not $extracted) { Write-Fail 'Архив GitHub пуст или имеет неизвестную структуру.' }
        $inner = $extracted.FullName
        $content = Join-Path $stage 'content'
        New-Item -ItemType Directory -Path $content -Force | Out-Null
        Get-ChildItem -LiteralPath $inner -Force | Copy-Item -Destination $content -Recurse -Force
        Remove-Item -LiteralPath $inner -Recurse -Force
        Get-ChildItem -LiteralPath $content -Force | Copy-Item -Destination $stage -Recurse -Force
        Remove-Item -LiteralPath $content -Recurse -Force
    }

    if (-not (Test-Path -LiteralPath (Join-Path $stage 'pyproject.toml')) -or
        -not (Test-Path -LiteralPath (Join-Path $stage 'yt_essential\__init__.py'))) {
        Write-Fail 'В исходном архиве отсутствует ожидаемая структура Python-пакета yt_essential.'
    }

    if (Test-Path -LiteralPath $SourceDir) { Remove-Item -LiteralPath $SourceDir -Recurse -Force }
    Move-Item -LiteralPath $stage -Destination $SourceDir
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
}

function Write-Launchers {
    Ensure-Directory $BinDir
    $cmd = @'
@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "YTES_LOG_DIR=%APPDATA%\yt-essential\logs"
"%~dp0..\venv\Scripts\python.exe" -X utf8 -m yt_essential.windows_compat %*
set "YTES_EXIT=%ERRORLEVEL%"
endlocal & exit /b %YTES_EXIT%
'@
    # ASCII wrapper, paths are resolved relative to %~dp0 and safely quoted.
    [System.IO.File]::WriteAllText((Join-Path $BinDir 'essn.cmd'), $cmd, [System.Text.Encoding]::ASCII)

    $installedWindows = Join-Path $InstallRoot 'windows'
    $sameWindowsFolder = [System.String]::Equals(
        [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd([char]'\'),
        [System.IO.Path]::GetFullPath($installedWindows).TrimEnd([char]'\'),
        [System.StringComparison]::OrdinalIgnoreCase
    )
    if (-not $sameWindowsFolder) {
        if (Test-Path -LiteralPath $installedWindows) { Remove-Item -LiteralPath $installedWindows -Recurse -Force }
        Ensure-Directory $installedWindows
        Get-ChildItem -LiteralPath $PSScriptRoot -Force | Copy-Item -Destination $installedWindows -Recurse -Force
    }
    Add-UserPathEntry $BinDir
    Refresh-ProcessPath
}

try {
    Ensure-Directory $LogRoot
    $logFile = Join-Path $LogRoot ("install-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    try { Start-Transcript -Path $logFile -Append | Out-Null } catch { }

    if ($Uninstall) {
        Write-Section 'Удаление yt-dlp-essential'
        Remove-UserPathEntry $BinDir
        if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
        Write-Ok 'Файлы приложения и виртуальное окружение удалены.'
        Write-Host 'Пользовательские настройки в %APPDATA%\yt-essential и скачанные файлы в Downloads сохранены.'
        exit 0
    }

    if ($PSVersionTable.PSVersion -lt [version]'5.1') { Write-Fail 'Требуется Windows PowerShell 5.1 или PowerShell 7+.' }
    if (-not [Environment]::Is64BitOperatingSystem) { Write-Fail 'Поддерживается только Windows x64.' }
    $osVersion = [Environment]::OSVersion.Version
    if ($osVersion.Major -lt 10 -or ($osVersion.Major -eq 10 -and $osVersion.Build -lt 16299)) {
        Write-Fail 'Требуется Windows 10 версии 1709 (сборка 16299) или Windows 11.'
    }

    Write-Section 'Проверка системных зависимостей'
    if ($PSVersionTable.PSVersion.Major -eq 5) { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 }
    Refresh-ProcessPath
    $python = Find-Python
    if (-not $python -and -not $SkipSystemDependencies) {
        Invoke-WinGetInstall 'Python.Python.3.14' 'Python 3.14 x64' | Out-Null
        Refresh-ProcessPath
        $python = Find-Python
    }
    if (-not $python) {
        Write-Fail 'Не найден 64-разрядный Python 3.10+. Установите Python x64 с https://www.python.org/downloads/windows/ и повторите запуск.'
    }
    $pythonVersion = & $python --version
    Write-Ok "$pythonVersion ($python)"

    $ffmpeg = Get-Command 'ffmpeg.exe' -ErrorAction SilentlyContinue
    $ffprobe = Get-Command 'ffprobe.exe' -ErrorAction SilentlyContinue
    if ((-not $ffmpeg -or -not $ffprobe) -and -not $SkipSystemDependencies) {
        Invoke-WinGetInstall 'Gyan.FFmpeg.Shared' 'FFmpeg (ffmpeg + ffprobe)' | Out-Null
        Refresh-ProcessPath
        $ffmpeg = Get-Command 'ffmpeg.exe' -ErrorAction SilentlyContinue
        $ffprobe = Get-Command 'ffprobe.exe' -ErrorAction SilentlyContinue
    }
    if ($ffmpeg -and $ffprobe) {
        Write-Ok 'FFmpeg и ffprobe найдены'
    }
    else {
        Write-Warn 'FFmpeg/ffprobe не найдены. Простое скачивание отдельных потоков будет доступно, но объединение аудио/видео, извлечение аудио и обрезка фрагментов требуют FFmpeg.'
    }

    $deno = Get-Command 'deno.exe' -ErrorAction SilentlyContinue
    $denoVersion = $null
    $denoSupported = $false
    if ($deno) {
        $denoVersion = (& $deno.Source --version 2>$null | Select-Object -First 1)
        if ($denoVersion -match '(?i)deno\s+(\d+)\.(\d+)\.(\d+)') {
            $parsedDeno = [version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])
            $denoSupported = ($parsedDeno -ge [version]'2.3.0')
        }
    }
    if (-not $denoSupported -and -not $SkipSystemDependencies) {
        Invoke-WinGetInstall 'DenoLand.Deno' 'Deno JavaScript runtime 2.3+' | Out-Null
        Refresh-ProcessPath
        $deno = Get-Command 'deno.exe' -ErrorAction SilentlyContinue
        if ($deno) {
            $denoVersion = (& $deno.Source --version 2>$null | Select-Object -First 1)
            if ($denoVersion -match '(?i)deno\s+(\d+)\.(\d+)\.(\d+)') {
                $parsedDeno = [version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])
                $denoSupported = ($parsedDeno -ge [version]'2.3.0')
            }
        }
    }
    if ($deno -and $denoSupported) {
        Write-Ok "Deno найден: $denoVersion"
    }
    else {
        Write-Warn 'Поддерживаемый Deno 2.3+ не найден. YouTube может выдавать ошибки JavaScript challenge. Установите Deno с https://docs.deno.com/runtime/getting_started/installation/ (WinGet: DenoLand.Deno).'
    }

    Write-Section 'Подготовка каталога установки'
    Ensure-Directory $InstallRoot
    Ensure-Directory $LogRoot
    if (-not (Test-Path -LiteralPath (Join-Path $VenvPath 'Scripts\python.exe'))) {
        if (Test-Path -LiteralPath $VenvPath) { Remove-Item -LiteralPath $VenvPath -Recurse -Force }
        & $python -m venv $VenvPath
        if ($LASTEXITCODE -ne 0) { Write-Fail 'Не удалось создать Python virtual environment.' }
    }
    $venvPython = Join-Path $VenvPath 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) { Write-Fail 'В venv не найден Scripts\python.exe.' }
    & $venvPython -m pip install --upgrade --disable-pip-version-check pip
    if ($LASTEXITCODE -ne 0) { Write-Fail 'Не удалось обновить pip в виртуальном окружении.' }

    $localSource = $SourcePath
    if (-not $localSource -and (Test-Path -LiteralPath (Join-Path $RepoRoot 'pyproject.toml'))) {
        $localSource = $RepoRoot
    }
    Install-ProjectSource -LocalSource $localSource

    Write-Section 'Установка yt-dlp-essential и библиотек'
    & $venvPython -m pip install --upgrade --force-reinstall --disable-pip-version-check $SourceDir
    if ($LASTEXITCODE -ne 0) { Write-Fail 'pip не смог установить проект или его зависимости. См. журнал установки.' }

    # Install the adapter outside pip's RECORD manifest. The upstream app can
    # update itself with pip; its uninstall/reinstall must not delete this file.
    $compatSource = Join-Path $PSScriptRoot 'yt_essential_windows.py'
    $packageDir = Join-Path $VenvPath 'Lib\site-packages\yt_essential'
    if (-not (Test-Path -LiteralPath $compatSource -PathType Leaf)) {
        Write-Fail "Не найден Windows compatibility module: $compatSource"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $packageDir '__init__.py'))) {
        Write-Fail "После установки не найден пакет yt_essential: $packageDir"
    }
    Copy-Item -LiteralPath $compatSource -Destination (Join-Path $packageDir 'windows_compat.py') -Force

    Write-Section 'Создание команды запуска'
    Write-Launchers

    Write-Section 'Проверка Python-пакетов'
    & $venvPython -X utf8 -c "import yt_essential, yt_dlp, gallery_dl; print('yt-dlp-essential', yt_essential.__version__); print('yt-dlp', yt_dlp.version.__version__); print('gallery-dl import: OK')"
    if ($LASTEXITCODE -ne 0) { Write-Fail 'Проверка Python-пакетов завершилась ошибкой.' }
    & $venvPython -X utf8 -c "import yt_essential.windows_compat as w; print('Windows compatibility module: OK; config=', w.config_directory())"
    if ($LASTEXITCODE -ne 0) { Write-Fail 'Не удалось импортировать Windows compatibility module.' }

    Write-Section 'Готово'
    Write-Ok 'Установка завершена.'
    Write-Host "Команда: essn" -ForegroundColor Green
    Write-Host "Установлено в: $InstallRoot"
    Write-Host "Конфигурация: $env:APPDATA\yt-essential\config.json"
    Write-Host "Загрузки по умолчанию: $env:USERPROFILE\Downloads\yt-essential"
    Write-Host 'Откройте новое окно PowerShell/Windows Terminal, затем выполните: essn'
    Write-Host 'Также можно запустить непосредственно: .\windows\run.ps1'
}
catch {
    Write-Host "`nОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Журнал: $logFile" -ForegroundColor Yellow
    exit 1
}
finally {
    try { Stop-Transcript | Out-Null } catch { }
}
