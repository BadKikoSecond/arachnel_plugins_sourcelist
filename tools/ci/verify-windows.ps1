#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root

$ArachnelVersion = if ($env:ARACHNEL_VERSION) { $env:ARACHNEL_VERSION } else { "0.1.34a" }
$QtVersion = if ($env:QT_VERSION) { $env:QT_VERSION } else { "6.11.1" }

Write-Host "=== Verify plugins on Windows (Arachnel v$ArachnelVersion, Qt $QtVersion MinGW) ==="

$packages = Get-ChildItem -Path $Root -Filter "*.arach" -File | Sort-Object Name
if ($packages.Count -eq 0) {
    Write-Host "No .arach packages in repo root"
    exit 0
}

$workDir = Join-Path $env:TEMP "arachnel-plugin-verify"
New-Item -ItemType Directory -Force -Path $workDir | Out-Null

# Match Arachnel release.yml: MinGW kit (plugins are MinGW DLLs).
$qtRoot = Join-Path $workDir "qt"
$qtPath = Join-Path $qtRoot "$QtVersion\mingw_64"
$qtBin = Join-Path $qtPath "bin"

if (-not (Test-Path (Join-Path $qtBin "Qt6Core.dll"))) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        choco install python3 -y --no-progress --execution-timeout 1200
    }
    $venv = Join-Path $workDir "aqt-venv"
    if (-not (Test-Path (Join-Path $venv "Scripts\aqt.exe"))) {
        python -m venv $venv
        & (Join-Path $venv "Scripts\pip.exe") install --upgrade pip aqtinstall
    }
    & (Join-Path $venv "Scripts\aqt.exe") install-qt windows desktop $QtVersion win64_mingw `
        -m qtshadertools qtmultimedia `
        -O $qtRoot
}

# Prefer runner-local MinGW Qt if present (same as plugin CI).
$localQt = "D:\Qt\$QtVersion\mingw_64\bin"
if (Test-Path (Join-Path $localQt "Qt6Core.dll")) {
    $qtBin = $localQt
    Write-Host "Using local Qt: $qtBin"
}

$runtimeDirs = @($qtBin)
$args = @(
    "python",
    (Join-Path $Root "tools\verify_plugins.py"),
    "--platform", "windows"
)
foreach ($dir in $runtimeDirs) {
    $args += @("--runtime-dir", $dir)
}
foreach ($pkg in $packages) {
    $args += $pkg.FullName
}

Write-Host "Running: $($args -join ' ')"
& $args[0] $args[1..($args.Length - 1)]
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
