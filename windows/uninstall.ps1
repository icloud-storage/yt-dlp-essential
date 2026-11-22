[CmdletBinding()]
param()
$Installer = Join-Path $PSScriptRoot 'install.ps1'
if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
    throw "Не найден установщик: $Installer"
}
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $Installer -Uninstall
exit $LASTEXITCODE
