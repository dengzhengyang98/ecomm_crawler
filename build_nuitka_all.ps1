# Unified Nuitka Build Script for E-Commerce Product Manager
# This script builds both Windows 32-bit and 64-bit versions

param(
    [ValidateSet("all", "x64", "x86")]
    [string]$Architecture = "all",
    [switch]$Clean = $false
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Nuitka Build Script - Multi-Architecture" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Clean build directories if requested
if ($Clean) {
    Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
    if (Test-Path "dist\win64") {
        Remove-Item -Recurse -Force "dist\win64"
    }
    if (Test-Path "dist\win32") {
        Remove-Item -Recurse -Force "dist\win32"
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
Write-Host "Build configuration:" -ForegroundColor Cyan
Write-Host "  Architecture: $Architecture" -ForegroundColor White
Write-Host "  Clean: $Clean" -ForegroundColor White
Write-Host ""

$buildSuccess = $true
$buildResults = @()

# Build 64-bit version
if ($Architecture -eq "all" -or $Architecture -eq "x64") {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Building Windows 64-bit (x64)..." -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    $cleanFlag = if ($Clean) { "-Clean" } else { "" }
    & "$PSScriptRoot\build_nuitka_win64.ps1" $cleanFlag
    
    if ($LASTEXITCODE -eq 0) {
        $buildResults += @{Arch = "x64"; Status = "Success"; Path = "dist\win64\EcommProductManager_x64.exe"}
        Write-Host ""
        Write-Host "✓ 64-bit build completed successfully" -ForegroundColor Green
    } else {
        $buildResults += @{Arch = "x64"; Status = "Failed"; Path = ""}
        $buildSuccess = $false
        Write-Host ""
        Write-Host "✗ 64-bit build failed" -ForegroundColor Red
    }
    Write-Host ""
}

# Build 32-bit version
if ($Architecture -eq "all" -or $Architecture -eq "x86") {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Building Windows 32-bit (x86)..." -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    $cleanFlag = if ($Clean) { "-Clean" } else { "" }
    & "$PSScriptRoot\build_nuitka_win32.ps1" $cleanFlag
    
    if ($LASTEXITCODE -eq 0) {
        $buildResults += @{Arch = "x86"; Status = "Success"; Path = "dist\win32\EcommProductManager_x86.exe"}
        Write-Host ""
        Write-Host "✓ 32-bit build completed successfully" -ForegroundColor Green
    } else {
        $buildResults += @{Arch = "x86"; Status = "Failed"; Path = ""}
        $buildSuccess = $false
        Write-Host ""
        Write-Host "✗ 32-bit build failed" -ForegroundColor Red
    }
    Write-Host ""
}

# Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Build Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

foreach ($result in $buildResults) {
    $statusColor = if ($result.Status -eq "Success") { "Green" } else { "Red" }
    $statusSymbol = if ($result.Status -eq "Success") { "✓" } else { "✗" }
    Write-Host "$statusSymbol $($result.Arch): $($result.Status)" -ForegroundColor $statusColor
    if ($result.Status -eq "Success" -and $result.Path) {
        Write-Host "   Location: $($result.Path)" -ForegroundColor Gray
    }
}

Write-Host ""

if ($buildSuccess) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "All builds completed successfully! ✓" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Executables are ready for distribution." -ForegroundColor Cyan
    Write-Host "Note: Sensitive config values are obfuscated for protection." -ForegroundColor Yellow
} else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Some builds failed! ✗" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    exit 1
}

