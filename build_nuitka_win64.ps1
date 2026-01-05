# Nuitka Build Script for E-Commerce Product Manager (Windows 64-bit)
# This script compiles the PySide6 application into a standalone .exe

param(
    [switch]$Clean = $false
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Nuitka Build Script - Windows 64-bit" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Clean build directory if requested
if ($Clean) {
    Write-Host "Cleaning previous build..." -ForegroundColor Yellow
    if (Test-Path "dist\win64") {
        Remove-Item -Recurse -Force "dist\win64"
    }
    Write-Host "✓ Clean complete" -ForegroundColor Green
    Write-Host ""
}

# Check if Nuitka is installed
Write-Host "Checking Nuitka installation..." -ForegroundColor Yellow
try {
    $nuitkaVersion = python -m nuitka --version 2>&1 | Out-String
    Write-Host "✓ Nuitka is installed: $($nuitkaVersion.Trim())" -ForegroundColor Green
} catch {
    Write-Host "✗ Nuitka is not installed. Installing..." -ForegroundColor Red
    pip install nuitka
}

Write-Host ""
Write-Host "Starting build process for Windows 64-bit..." -ForegroundColor Yellow
Write-Host ""

# Create output directory
$outputDir = "dist\win64"
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

# Build command with all necessary flags for 64-bit
$buildCommand = @(
    "python", "-m", "nuitka"
    "--standalone"
    "--onefile"
    "--windows-disable-console"
    "--enable-plugin=pyside6"
    "--include-module=config"
    "--include-module=config_obfuscation"
    "--include-module=auth_service"
    "--include-module=ui.main_window"
    "--include-module=ui.login_dialog"
    "--include-module=ui.components.scraper_thread"
    "--include-module=ui.components.sku_gallery"
    "--include-module=ui.components.image_gallery"
    "--include-module=ui.components.collapsible_section"
    "--include-module=scraper_firefox"
    "--include-module=scraper_amazon"
    "--include-module=image_processor"
    "--include-module=boto3"
    "--include-module=keyring"
    "--include-module=selenium"
    "--include-module=PIL"
    "--include-package-data=ui"
    "--assume-yes-for-downloads"
    "--output-dir=$outputDir"
    "--output-filename=EcommProductManager_x64.exe"
    "--python-flag=no_warnings"
    "--show-progress"
    "main.py"
)

Write-Host "Build command:" -ForegroundColor Cyan
Write-Host ($buildCommand -join " ") -ForegroundColor Gray
Write-Host ""

& $buildCommand[0] $buildCommand[1..($buildCommand.Length-1)]

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Build complete! ✓" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Executable location: $outputDir\EcommProductManager_x64.exe" -ForegroundColor Cyan
    Write-Host "Architecture: Windows 64-bit (x64)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Note: The .exe includes all dependencies and is standalone." -ForegroundColor Yellow
    Write-Host "      No Python installation required on target machines." -ForegroundColor Yellow
    Write-Host "      Sensitive config values are obfuscated for protection." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Build failed! ✗" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Check the error messages above for details." -ForegroundColor Yellow
    exit 1
}

