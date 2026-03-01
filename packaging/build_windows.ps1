param(
    [string]$Python = "python",
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
$SpecPath = Join-Path $ScriptDir "PyRRhic.spec"
$BuildDir = Join-Path $RootDir "build"
$DistDir = Join-Path $RootDir "dist"

Write-Host "[PyRRhic] Root: $RootDir"

if (-not $NoClean) {
    if (Test-Path $BuildDir) {
        Remove-Item -Recurse -Force $BuildDir
    }
    if (Test-Path $DistDir) {
        Remove-Item -Recurse -Force $DistDir
    }
}

& $Python -m pip install -r (Join-Path $RootDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Fallo instalando dependencias (exit code $LASTEXITCODE)."
}

& $Python -m PyInstaller --clean --noconfirm $SpecPath
if ($LASTEXITCODE -ne 0) {
    throw "Fallo PyInstaller (exit code $LASTEXITCODE)."
}

Write-Host ""
Write-Host "Build completo. Salida: $(Join-Path $DistDir 'PyRRhic')"
Write-Host "Siguiente paso (opcional): compilar instalador con Inno Setup:"
Write-Host "  iscc \"$ScriptDir\PyRRhic.iss\""
