[CmdletBinding()]
param([switch]$SkipSystemDependencies)
$ErrorActionPreference = 'Stop'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'yt-essential'
$Installer = Join-Path $InstallRoot 'windows\install.ps1'
if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
    $Installer = Join-Path $PSScriptRoot 'install.ps1'
}
if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
    throw 'Не найден install.ps1. Запустите установку из распакованной Windows-версии.'
}
$argsToPass = @()
if ($SkipSystemDependencies) { $argsToPass += '-SkipSystemDependencies' }
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $Installer @argsToPass
exit $LASTEXITCODE
