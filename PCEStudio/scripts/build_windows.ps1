$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$invalidPathEntry = "C:\Users\Administrator\AppData\Roaming\Programs\Zero Install"
$safePathParts = $env:Path -split ";" | Where-Object {
    $_ -ne $invalidPathEntry -and $_ -notmatch '\\poppler\\Library\\bin$'
}
$env:Path = $safePathParts -join ";"

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $projectRoot ".venv")
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $projectRoot "requirements-dev.txt")
Push-Location $projectRoot
try {
    & $venvPython -m pytest
    & $venvPython -m PyInstaller --noconfirm --clean "PCEStudio.spec"
}
finally {
    Pop-Location
}

Write-Host "Build complete: $projectRoot\dist\PCEStudio_portable\PCEStudio.exe"
