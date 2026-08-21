<#
.SYNOPSIS
    Remove atalho, comando e ambiente virtual do Farol no Windows.

.DESCRIPTION
    Seus dados NÃO são apagados: banco e currículos continuam onde estão.
    Para apagá-los também, use -ComDados (a confirmação é pedida).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
#>

[CmdletBinding()]
param([switch]$ComDados)

$ErrorActionPreference = 'Stop'

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $AppDir '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'

$dataDir = Join-Path $env:LOCALAPPDATA 'Farol'
if (Test-Path $VenvPython) {
    $reported = & $VenvPython -c 'from farol import db; print(db.home())' 2>$null
    if ($LASTEXITCODE -eq 0 -and $reported) { $dataDir = $reported.Trim() }
}

$BinDir = Join-Path $env:LOCALAPPDATA 'Programs\Farol'
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Farol.lnk'
$desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Farol.lnk'

foreach ($path in @($startMenu, $desktopLink, $BinDir, $Venv)) {
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -like "*$BinDir*") {
    $cleaned = ($userPath -split ';' | Where-Object { $_ -and $_ -ne $BinDir }) -join ';'
    [Environment]::SetEnvironmentVariable('Path', $cleaned, 'User')
}

Write-Host 'Atalho, comando e ambiente removidos.'

if ($ComDados) {
    Write-Host ''
    Write-Host "Isto apaga PARA SEMPRE o banco e os currículos em:`n  $dataDir" -ForegroundColor Yellow
    $answer = Read-Host 'Digite APAGAR para confirmar'
    if ($answer -ceq 'APAGAR') {
        Remove-Item -Recurse -Force $dataDir
        Write-Host 'Dados apagados.'
    } else {
        Write-Host 'Nada foi apagado.'
    }
} else {
    Write-Host "Seus dados continuam em $dataDir (use -ComDados para apagá-los)."
}
