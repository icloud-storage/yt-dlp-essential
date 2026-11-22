[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$EssnArguments
)
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA 'yt-essential'
$Launcher = Join-Path $InstallRoot 'bin\essn.cmd'

if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) {
    $installer = Join-Path $PSScriptRoot 'install.ps1'
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw "Не найден установщик: $installer"
    }
    $sourceArg = @()
    if (Test-Path -LiteralPath (Join-Path $RepoRoot 'pyproject.toml')) {
        $sourceArg = @('-SourcePath', $RepoRoot)
    }
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $installer @sourceArg
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) {
        throw 'Установщик завершился без ошибки, но команда essn.cmd не создана.'
    }
}

& $Launcher @EssnArguments
exit $LASTEXITCODE
