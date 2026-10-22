<#
.SYNOPSIS
    Reproducible Release Build Script for Findora.
.DESCRIPTION
    Builds the standalone Python backend via PyInstaller and the C# WPF frontend via dotnet publish,
    assembling the complete distributable package into dist/Findora/.
#>

[CmdletBinding()]
param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
Set-Location $RootDir

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "      Building Findora Release          " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Run Tests (Quality Gate)
if (-not $SkipTests) {
    Write-Host "`n[1/4] Running test suites..." -ForegroundColor Yellow
    python -m unittest discover -s "tests\python"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Python test suite failed. Aborting release build."
    }

    dotnet test Findora.sln -c Release
    if ($LASTEXITCODE -ne 0) {
        Write-Error ".NET test suite failed. Aborting release build."
    }
    Write-Host "All test suites passed!" -ForegroundColor Green
} else {
    Write-Host "`n[1/4] Skipping test suites (-SkipTests specified)." -ForegroundColor DarkGray
}

# 2. Prepare Distribution Directories
Write-Host "`n[2/4] Preparing output directories..." -ForegroundColor Yellow
$DistDir = Join-Path $RootDir "dist\Findora"
$BackendDistDir = Join-Path $DistDir "backend"
$PyDist = Join-Path $RootDir "build\py_dist"
$PyWork = Join-Path $RootDir "build\py_work"

# Stop any running instances to unlock binaries
Get-Process -Name "Findora", "FindoraBackend" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir
}
New-Item -ItemType Directory -Force -Path $BackendDistDir | Out-Null

# 3. Build Standalone Python Backend
Write-Host "`n[3/4] Building standalone Python backend with PyInstaller..." -ForegroundColor Yellow
$MainPy = Join-Path $RootDir "src\Findora.Backend\main.py"
$BackendDir = Join-Path $RootDir "src\Findora.Backend"

pyinstaller --clean -y `
    --name FindoraBackend `
    --distpath $PyDist `
    --workpath $PyWork `
    --paths $BackendDir `
    $MainPy

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
}

# Copy compiled backend into dist/Findora/backend
Write-Host "Copying backend files to $BackendDistDir..." -ForegroundColor DarkGray
Copy-Item -Recurse -Force "$PyDist\FindoraBackend\*" $BackendDistDir

# 4. Build & Publish C# WPF Frontend
Write-Host "`n[4/4] Publishing Findora WPF frontend in Release mode..." -ForegroundColor Yellow
$WpfProject = Join-Path $RootDir "src\Findora.Wpf\Findora.Wpf.csproj"

dotnet publish $WpfProject `
    -c Release `
    -o $DistDir `
    --no-self-contained

if ($LASTEXITCODE -ne 0) {
    Write-Error "dotnet publish failed."
}

# 5. Verification
$MainExe = Join-Path $DistDir "Findora.exe"
$BackendExe = Join-Path $BackendDistDir "FindoraBackend.exe"

if ((Test-Path $MainExe) -and (Test-Path $BackendExe)) {
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host " Findora Release Build Succeeded!" -ForegroundColor Green
    Write-Host " Main Executable: $MainExe" -ForegroundColor White
    Write-Host " Backend Executable: $BackendExe" -ForegroundColor White
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Error "Build finished but required output executables are missing!"
}
