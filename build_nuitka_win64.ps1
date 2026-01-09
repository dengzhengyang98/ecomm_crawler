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
    Write-Host "[OK] Clean complete" -ForegroundColor Green
    Write-Host ""
}

# Check if Python is available
Write-Host "Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1 | Out-String
    Write-Host "[OK] Python is installed: $($pythonVersion.Trim())" -ForegroundColor Green
} catch {
    Write-Host "[X] Python is not installed or not in PATH!" -ForegroundColor Red
    Write-Host "Please install Python 3.8+ and add it to your PATH." -ForegroundColor Yellow
    exit 1
}

# Check if Nuitka is installed
Write-Host "Checking Nuitka installation..." -ForegroundColor Yellow
try {
    $nuitkaVersion = python -m nuitka --version 2>&1 | Out-String
    Write-Host "[OK] Nuitka is installed: $($nuitkaVersion.Trim())" -ForegroundColor Green
} catch {
    Write-Host "[X] Nuitka is not installed. Installing..." -ForegroundColor Red
    pip install nuitka
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Failed to install Nuitka!" -ForegroundColor Red
        exit 1
    }
}

# Check if required packages are installed
Write-Host "Checking required dependencies..." -ForegroundColor Yellow
$packageMap = @{
    "PySide6" = "PySide6"
    "selenium" = "selenium"
    "boto3" = "boto3"
    "keyring" = "keyring"
    "Pillow" = "PIL"
    "webdriver-manager" = "webdriver_manager"
    "requests" = "requests"
}
$missingPackages = @()

foreach ($packageName in $packageMap.Keys) {
    $importName = $packageMap[$packageName]
    $result = python -c "import $importName; print('OK')" 2>&1
    if ($LASTEXITCODE -eq 0 -and $result -match "OK") {
        Write-Host "  [OK] $packageName" -ForegroundColor Green
    } else {
        $missingPackages += $packageName
        Write-Host "  [X] $packageName `(missing`)" -ForegroundColor Yellow
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host ""
    Write-Host "[WARN] Some packages are missing. Installing from requirements.txt..." -ForegroundColor Yellow
    if (Test-Path "requirements.txt") {
        pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[X] Failed to install dependencies!" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "[X] requirements.txt not found!" -ForegroundColor Red
        exit 1
    }
}

# Check for C compiler (required for Nuitka)
Write-Host "Checking for C compiler..." -ForegroundColor Yellow
$hasCompiler = $false
$useMingw = $false

# First, check if Nuitka detected a compiler (it shows this in version output)
$nuitkaInfo = python -m nuitka --version 2>&1 | Out-String
if ($nuitkaInfo -match "Version C compiler:.*cl\.exe") {
    Write-Host "[OK] Microsoft Visual C++ compiler detected by Nuitka" -ForegroundColor Green
    $hasCompiler = $true
    
    # Try to find and initialize Visual Studio environment
    $vsPaths = @(
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvars64.bat",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat",
        "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat"
    )
    
    foreach ($vcvarsPath in $vsPaths) {
        if (Test-Path $vcvarsPath) {
            Write-Host "  Initializing Visual Studio environment..." -ForegroundColor Gray
            # Initialize Visual Studio environment
            & cmd /c "`"$vcvarsPath`" && set" | ForEach-Object {
                if ($_ -match "^(.+?)=(.*)$") {
                    [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2])
                }
            }
            break
        }
    }
} elseif ($nuitkaInfo -match "Version C compiler:.*gcc") {
    Write-Host "[OK] MinGW compiler detected by Nuitka `(gcc`)" -ForegroundColor Green
    $hasCompiler = $true
    $useMingw = $true
} else {
    # Fallback: Check for compiler in PATH
    $clPath = Get-Command cl -ErrorAction SilentlyContinue
    if ($clPath) {
        Write-Host "[OK] Microsoft Visual C++ compiler found in PATH" -ForegroundColor Green
        $hasCompiler = $true
    } else {
        # Check for MinGW (gcc.exe)
        $gccPath = Get-Command gcc -ErrorAction SilentlyContinue
        if ($gccPath) {
            Write-Host "[OK] MinGW compiler found in PATH `(gcc`)" -ForegroundColor Green
            $hasCompiler = $true
            $useMingw = $true
        } else {
            Write-Host "[WARN] No C compiler found in PATH, but Nuitka may still work" -ForegroundColor Yellow
            Write-Host "  Proceeding with build - Nuitka will attempt to locate compiler automatically" -ForegroundColor Yellow
            $hasCompiler = $true  # Trust Nuitka to find it
        }
    }
}

Write-Host ""
Write-Host "Starting build process for Windows 64-bit..." -ForegroundColor Yellow
Write-Host ""

# Verify main.py exists
if (-not (Test-Path "main.py")) {
    Write-Host "[X] main.py not found in current directory!" -ForegroundColor Red
    Write-Host "Please run this script from the project root directory." -ForegroundColor Yellow
    exit 1
}

# Create output directory
$outputDir = "dist\win64"
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
    Write-Host "[OK] Created output directory: $outputDir" -ForegroundColor Green
}

# Build command with all necessary flags for 64-bit
# Core application modules, UI modules, scraper modules, third-party packages,
# package data, hidden imports, and optimization options are all included
$buildCommand = @(
    "python", "-m", "nuitka"
    "--standalone"
    "--onefile"
    "--windows-console-mode=disable"
    "--enable-plugin=pyside6"
    # Core application modules
    "--include-module=config"
    "--include-module=config_obfuscation"
    "--include-module=auth_service"
    # UI modules
    "--include-module=ui.main_window"
    "--include-module=ui.login_dialog"
    "--include-module=ui.components.scraper_thread"
    "--include-module=ui.components.sku_gallery"
    "--include-module=ui.components.image_gallery"
    "--include-module=ui.components.collapsible_section"
    # Scraper modules
    "--include-module=scraper_firefox"
    "--include-module=scraper_amazon"
    "--include-module=image_processor"
    # Third-party packages (core)
    "--include-module=boto3"
    "--include-module=botocore"
    "--include-module=keyring"
    "--include-module=selenium"
    "--include-module=PIL"
    "--include-module=webdriver_manager"
    "--include-module=requests"
    # Boto3 submodules
    "--include-module=boto3.s3"
    "--include-module=boto3.dynamodb"
    "--include-module=boto3.dynamodb.types"
    "--include-module=boto3.exceptions"
    # Botocore submodules (required by boto3)
    "--include-module=botocore.exceptions"
    "--include-module=botocore.credentials"
    # Selenium submodules
    "--include-module=selenium.webdriver.firefox.service"
    "--include-module=selenium.webdriver.firefox.options"
    "--include-module=selenium.webdriver.common.by"
    "--include-module=selenium.webdriver.support.ui"
    "--include-module=selenium.webdriver.support.expected_conditions"
    # Webdriver manager submodules
    "--include-module=webdriver_manager.firefox"
    # PIL submodules
    "--include-module=PIL.Image"
    "--include-module=PIL.ImageOps"
    "--include-module=PIL.ImageFilter"
    "--include-module=PIL.ImageEnhance"
    # Package data
    "--include-package-data=ui"
    "--include-package-data=webdriver_manager"
    "--include-package-data=PySide6"
    # Build options
    "--assume-yes-for-downloads"
    "--output-dir=$outputDir"
    "--output-filename=EcommProductManager_x64.exe"
    "--python-flag=no_warnings"
    "--show-progress"
    "--show-memory"
)

# Add MinGW flag if using MinGW compiler
if ($useMingw) {
    $buildCommand += "--mingw64"
}

# Add main.py at the end
$buildCommand += "main.py"

Write-Host "Build command:" -ForegroundColor Cyan
Write-Host ($buildCommand -join " ") -ForegroundColor Gray
Write-Host ""

& $buildCommand[0] $buildCommand[1..($buildCommand.Length-1)]

if ($LASTEXITCODE -eq 0) {
    $exePath = "$outputDir\EcommProductManager_x64.exe"
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Build complete! [OK]" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Executable location: $exePath" -ForegroundColor Cyan
    Write-Host "Architecture: Windows 64-bit `(x64`)" -ForegroundColor Cyan
    
    if (Test-Path $exePath) {
        $fileSize = (Get-Item $exePath).Length / 1MB
        Write-Host "File size: $([math]::Round($fileSize, 2)) MB" -ForegroundColor Cyan
    }
    
    Write-Host ""
    Write-Host "Encapsulation Summary:" -ForegroundColor Yellow
    Write-Host "  [OK] All Python dependencies bundled" -ForegroundColor Green
    Write-Host "  [OK] PySide6 GUI framework included" -ForegroundColor Green
    Write-Host "  [OK] Selenium and webdriver_manager included" -ForegroundColor Green
    Write-Host "  [OK] AWS SDK `(boto3 + botocore`) fully included" -ForegroundColor Green
    Write-Host "  [OK] Image processing `(PIL`) included" -ForegroundColor Green
    Write-Host "  [OK] All application modules encapsulated" -ForegroundColor Green
    Write-Host "  [OK] Standalone executable - no Python required" -ForegroundColor Green
    Write-Host "  [OK] Config values obfuscated for protection" -ForegroundColor Green
    Write-Host "  [OK] All submodules and dependencies included" -ForegroundColor Green
    Write-Host ""
    Write-Host "The executable is ready for distribution!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Build failed! [X]" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Check the error messages above for details." -ForegroundColor Yellow
    exit 1
}

