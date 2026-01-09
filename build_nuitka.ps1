# Nuitka Build Script for E-Commerce Product Manager
# 
# NOTE: This is the legacy build script. For better protection and multi-architecture support,
# please use the new build scripts:
#   - build_nuitka_all.ps1      (recommended - builds both 32-bit and 64-bit)
#   - build_nuitka_win64.ps1    (64-bit only)
#   - build_nuitka_win32.ps1    (32-bit only)
#
# This script is kept for backward compatibility and builds 64-bit by default.

Write-Host "========================================" -ForegroundColor Yellow
Write-Host "WARNING: Using Legacy Build Script" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "For better protection and multi-architecture support," -ForegroundColor Yellow
Write-Host "please use: .\build_nuitka_all.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to cancel, or wait 3 seconds to continue..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Nuitka Build Script (Legacy - 64-bit)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Nuitka is installed
Write-Host "Checking Nuitka installation..." -ForegroundColor Yellow
try {
    python -m nuitka --version | Out-Null
    Write-Host "✓ Nuitka is installed" -ForegroundColor Green
} catch {
    Write-Host "✗ Nuitka is not installed. Installing..." -ForegroundColor Red
    pip install nuitka
}

Write-Host ""
Write-Host "Starting build process..." -ForegroundColor Yellow
Write-Host ""

# Build command with all necessary flags (includes config_obfuscation module)
python -m nuitka `
    --standalone `
    --onefile `
    --windows-console-mode=disable `
    --enable-plugin=pyside6 `
    --include-module=config `
    --include-module=config_obfuscation `
    --include-module=auth_service `
    --include-module=ui.main_window `
    --include-module=ui.login_dialog `
    --include-module=ui.components.scraper_thread `
    --include-module=ui.components.sku_gallery `
    --include-module=ui.components.image_gallery `
    --include-module=ui.components.collapsible_section `
    --include-module=scraper_firefox `
    --include-module=scraper_amazon `
    --include-module=image_processor `
    --include-module=boto3 `
    --include-module=keyring `
    --include-module=selenium `
    --include-module=PIL `
    --include-package-data=ui `
    --assume-yes-for-downloads `
    --output-dir=dist `
    --output-filename=EcommProductManager.exe `
    --python-flag=no_warnings `
    main.py

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Build complete! ✓" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Executable location: dist\EcommProductManager.exe" -ForegroundColor Cyan
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
}

