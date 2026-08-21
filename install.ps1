<#
.SYNOPSIS
    Instalador do Farol para Windows.

.DESCRIPTION
    Cria um ambiente Python isolado, instala o aplicativo, prepara o banco e
    coloca o atalho no Menu Iniciar. Rodar de novo atualiza o que já existe:
    nenhuma etapa apaga dados.

.PARAMETER SemAtalho
    Instala apenas o ambiente e o comando de terminal, sem atalho no menu.

.PARAMETER ComAreaDeTrabalho
    Cria também um atalho na área de trabalho.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
#>

[CmdletBinding()]
param(
    [switch]$SemAtalho,
    [switch]$ComAreaDeTrabalho
)

$ErrorActionPreference = 'Stop'

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $AppDir '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$VenvFarol = Join-Path $Venv 'Scripts\farol.exe'

function Write-Step($text) { Write-Host $text -ForegroundColor White }
function Write-Detail($text) { Write-Host "   $text" -ForegroundColor DarkGray }

# ---------------------------------------------------------------- 1. Python

function Find-Python {
    # o launcher `py` é o caminho mais confiável no Windows
    foreach ($candidate in @(
        @{ Exe = 'py';      Args = @('-3.13') },
        @{ Exe = 'py';      Args = @('-3.12') },
        @{ Exe = 'py';      Args = @('-3.11') },
        @{ Exe = 'py';      Args = @('-3') },
        @{ Exe = 'python';  Args = @() }
    )) {
        $exe = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        $probe = $candidate.Args + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)')
        & $exe.Source @probe 2>$null
        if ($LASTEXITCODE -eq 0) { return @{ Exe = $exe.Source; Args = $candidate.Args } }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Host @'
Python 3.10 ou mais novo não foi encontrado.

  Microsoft Store   procure por "Python 3.12"
  winget            winget install Python.Python.3.12
  site oficial      https://www.python.org/downloads/windows/

Ao instalar pelo site, marque "Add python.exe to PATH".
'@ -ForegroundColor Red
    exit 1
}

$versionArgs = $python.Args + @('-V')
$versionText = (& $python.Exe @versionArgs 2>&1) -join ' '
Write-Step "1/5 - ambiente Python ($versionText)"

$venvArgs = $python.Args + @('-m', 'venv', $Venv)
& $python.Exe @venvArgs
& $VenvPython -m pip install --quiet --upgrade pip
& $VenvPython -m pip install --quiet -e $AppDir

# ---------------------------------------------------------------- 2. banco

Write-Step '2/5 - banco de dados'
& $VenvPython -m farol caminho | ForEach-Object { Write-Detail $_ }

# ---------------------------------------------------------------- 3. comando

Write-Step '3/5 - comando de terminal'
$BinDir = Join-Path $env:LOCALAPPDATA 'Programs\Farol'
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
@"
@echo off
"$VenvFarol" %*
"@ | Set-Content -Path (Join-Path $BinDir 'farol.cmd') -Encoding ASCII
Write-Detail (Join-Path $BinDir 'farol.cmd')

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$BinDir*") {
    [Environment]::SetEnvironmentVariable('Path', "$userPath;$BinDir", 'User')
    Write-Detail 'PATH do usuário atualizado (abra um terminal novo para valer)'
}

# ---------------------------------------------------------------- 4. atalho

function New-Shortcut($path, $icon) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $VenvFarol
    $link.Arguments = 'abrir'
    $link.WorkingDirectory = $AppDir
    $link.Description = 'Vagas remotas, candidaturas, currículos e roadmap de estudos'
    $link.WindowStyle = 7  # minimizado: o app abre no navegador, não num console
    if (Test-Path $icon) { $link.IconLocation = $icon }
    $link.Save()
}

if (-not $SemAtalho) {
    Write-Step '4/5 - atalho no Menu Iniciar'
    $icon = Join-Path $AppDir 'assets\farol.ico'
    $startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
    New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
    New-Shortcut (Join-Path $startMenu 'Farol.lnk') $icon
    Write-Detail (Join-Path $startMenu 'Farol.lnk')

    if ($ComAreaDeTrabalho) {
        $desktop = [Environment]::GetFolderPath('Desktop')
        New-Shortcut (Join-Path $desktop 'Farol.lnk') $icon
        Write-Detail (Join-Path $desktop 'Farol.lnk')
    }
} else {
    Write-Step '4/5 - atalho ignorado (-SemAtalho)'
}

# ---------------------------------------------------------------- 5. fim

Write-Step '5/5 - instalado'
Write-Host @"

  Abrir            farol
  Só o servidor    farol servir
  Só a coleta      farol atualizar
  Onde ficam       farol caminho
  Desinstalar      powershell -ExecutionPolicy Bypass -File "$AppDir\uninstall.ps1"

"@
