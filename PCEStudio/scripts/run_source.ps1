$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment not found. Run scripts\build_windows.ps1 first."
}

Push-Location $projectRoot
try {
    & $venvPython -m pce_app
}
finally {
    Pop-Location
}

