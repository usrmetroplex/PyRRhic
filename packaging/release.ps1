param(
    [string]$Python = "python",
    [switch]$NoClean,
    [switch]$SkipInstaller,
    [string]$IsccPath,
    [string]$Version,
    [switch]$KeepAllInstallers,
    [switch]$KeepAllReleaseFolders
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
$BuildScript = Join-Path $ScriptDir "build_windows.ps1"
$IssFile = Join-Path $ScriptDir "PyRRhic.iss"

Write-Host "[PyRRhic] Release root: $RootDir"

$buildArgs = @{
    Python = $Python
}
if ($NoClean) {
    $buildArgs.NoClean = $true
}

& $BuildScript @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "Build falló (exit code $LASTEXITCODE)."
}

if ($SkipInstaller) {
    Write-Host "Installer omitido por -SkipInstaller"
    exit 0
}

function Resolve-ReleaseVersion {
    param([string]$RequestedVersion)

    if ($RequestedVersion) {
        return $RequestedVersion
    }

    $tag = ""
    try {
        $tag = (git describe --tags --abbrev=0 2>$null | Select-Object -First 1).Trim()
    }
    catch {
        $tag = ""
    }

    if ($tag) {
        if ($tag.StartsWith('v')) {
            return $tag.Substring(1)
        }
        return $tag
    }

    return "0.1.0"
}

function Get-SafeFilenameVersion {
    param([string]$RawVersion)

    if (-not $RawVersion) {
        return "0.1.0"
    }

    return ($RawVersion -replace '[^0-9A-Za-z._-]', '-')
}

function Resolve-IsccPath {
    param([string]$RequestedPath)

    if ($RequestedPath -and (Test-Path $RequestedPath)) {
        return $RequestedPath
    }

    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($null -ne $cmd -and $cmd.Source) {
        return $cmd.Source
    }

    $candidates = @(
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Remove-OldInstallers {
    param(
        [string]$InstallerDir,
        [string]$CurrentInstallerName
    )

    if (-not (Test-Path $InstallerDir)) {
        return
    }

    $allInstallers = Get-ChildItem -Path $InstallerDir -File -Filter "PyRRhic-Setup*.exe" -ErrorAction SilentlyContinue
    foreach ($installer in $allInstallers) {
        if ($installer.Name -ne $CurrentInstallerName) {
            Remove-Item -Path $installer.FullName -Force
            Write-Host "[PyRRhic] Instalador antiguo eliminado: $($installer.Name)"
        }
    }
}

function Publish-VersionedRelease {
    param(
        [string]$RootPath,
        [string]$VersionLabel,
        [string]$InstallerFileName
    )

    $releasesRoot = Join-Path $RootPath "dist_releases"
    $releaseDir = Join-Path $releasesRoot $VersionLabel
    $installerSource = Join-Path (Join-Path $RootPath "dist_installer") $InstallerFileName
    $appSource = Join-Path $RootPath "dist\PyRRhic"

    New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

    if (Test-Path $installerSource) {
        Copy-Item -Path $installerSource -Destination $releaseDir -Force
    }

    if (Test-Path $appSource) {
        $zipPath = Join-Path $releaseDir ("PyRRhic-App-{0}.zip" -f $VersionLabel)
        if (Test-Path $zipPath) {
            Remove-Item -Path $zipPath -Force
        }
        Compress-Archive -Path (Join-Path $appSource "*") -DestinationPath $zipPath -CompressionLevel Optimal
    }

    return $releaseDir
}

function Remove-OldReleaseFolders {
    param(
        [string]$RootPath,
        [string]$CurrentVersion
    )

    $releasesRoot = Join-Path $RootPath "dist_releases"
    if (-not (Test-Path $releasesRoot)) {
        return
    }

    $folders = Get-ChildItem -Path $releasesRoot -Directory -ErrorAction SilentlyContinue
    foreach ($folder in $folders) {
        if ($folder.Name -ne $CurrentVersion) {
            Remove-Item -Path $folder.FullName -Recurse -Force
            Write-Host "[PyRRhic] Release antiguo eliminado: $($folder.Name)"
        }
    }
}

$resolvedIscc = Resolve-IsccPath -RequestedPath $IsccPath
if (-not $resolvedIscc) {
    throw "No se encontró ISCC.exe. Instala Inno Setup o pasa -IsccPath <ruta>."
}

 $resolvedVersion = Resolve-ReleaseVersion -RequestedVersion $Version
 $safeVersion = Get-SafeFilenameVersion -RawVersion $resolvedVersion
 $outputBaseFilename = "PyRRhic-Setup-$safeVersion"

Write-Host "[PyRRhic] ISCC: $resolvedIscc"
Write-Host "[PyRRhic] Version: $resolvedVersion"

& $resolvedIscc "/DMyAppVersion=$resolvedVersion" "/DMyOutputBaseFilename=$outputBaseFilename" $IssFile
if ($LASTEXITCODE -ne 0) {
    throw "Compilación de instalador falló (exit code $LASTEXITCODE)."
}

$installerName = "$outputBaseFilename.exe"
$installerDir = Join-Path $RootDir "dist_installer"
if (-not $KeepAllInstallers) {
    Remove-OldInstallers -InstallerDir $installerDir -CurrentInstallerName $installerName
}

$versionedReleaseDir = Publish-VersionedRelease -RootPath $RootDir -VersionLabel $safeVersion -InstallerFileName $installerName
if (-not $KeepAllReleaseFolders) {
    Remove-OldReleaseFolders -RootPath $RootDir -CurrentVersion $safeVersion
}

Write-Host ""
Write-Host "Release completo:"
Write-Host "  App:       $(Join-Path $RootDir 'dist\PyRRhic')"
Write-Host "  Installer: $(Join-Path $RootDir ("dist_installer\$installerName"))"
Write-Host "  Release:   $versionedReleaseDir"
