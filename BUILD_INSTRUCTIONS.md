# Nuitka Build Instructions for E-Commerce Product Manager

## Overview

This project uses **Nuitka** to compile the PySide6 application into standalone Windows executables with **string obfuscation** for protecting sensitive configuration values.

### Key Features

- ✅ **Nuitka Compilation**: Compiles Python to machine code (better protection than PyInstaller)
- ✅ **String Obfuscation**: Sensitive config values are obfuscated to protect against reverse engineering
- ✅ **Multi-Architecture Support**: Build for both Windows 32-bit (x86) and 64-bit (x64)
- ✅ **Standalone Executables**: No Python installation required on target machines
- ✅ **One-file Distribution**: Single .exe file includes all dependencies

## Prerequisites

1. **Python 3.8+** (64-bit recommended for building)
2. **Windows 10/11** (for building Windows executables)
3. **Nuitka** - Will be installed automatically if missing
4. **All project dependencies** - Install with:
   ```powershell
   pip install -r requirements.txt
   ```

5. **Microsoft Visual C++ Build Tools** (for Nuitka compilation)
   - Download from: https://visualstudio.microsoft.com/downloads/
   - Select "Build Tools for Visual Studio" and install "C++ build tools" workload

## Quick Start

### Build All Architectures (Recommended)

Build both 32-bit and 64-bit versions:

```powershell
.\build_nuitka_all.ps1
```

### Build Specific Architecture

Build only 64-bit:
```powershell
.\build_nuitka_win64.ps1
```

Build only 32-bit:
```powershell
.\build_nuitka_win32.ps1
```

### Clean Build

Remove previous build artifacts before building:
```powershell
.\build_nuitka_all.ps1 -Clean
```

## Build Scripts

### `build_nuitka_all.ps1`
Unified build script that can build both architectures:
```powershell
# Build all architectures
.\build_nuitka_all.ps1

# Build only 64-bit
.\build_nuitka_all.ps1 -Architecture x64

# Build only 32-bit
.\build_nuitka_all.ps1 -Architecture x86

# Clean build
.\build_nuitka_all.ps1 -Clean
```

### `build_nuitka_win64.ps1`
Builds Windows 64-bit executable:
- Output: `dist\win64\EcommProductManager_x64.exe`
- Architecture: x64 (AMD64)

### `build_nuitka_win32.ps1`
Builds Windows 32-bit executable:
- Output: `dist\win32\EcommProductManager_x86.exe`
- Architecture: x86 (IA-32)

## String Obfuscation

Sensitive configuration values are obfuscated using base64 encoding to protect against reverse engineering.

### Protected Values

The following values in `config.py` are automatically obfuscated:
- `COGNITO_USER_POOL_ID`
- `COGNITO_CLIENT_ID`
- `COGNITO_IDENTITY_POOL_ID`
- `API_GATEWAY_URL`
- API keys (if configured)

### Updating Obfuscated Values

If you need to update sensitive config values:

1. **Edit the obfuscation script** (`obfuscate_config.py`):
   ```python
   SENSITIVE_VALUES = {
       "COGNITO_USER_POOL_ID": "your-new-value",
       # ... other values
   }
   ```

2. **Run the obfuscation script**:
   ```powershell
   python obfuscate_config.py
   ```

3. **Update `config.py`** with the new obfuscated values (or copy from `config_obfuscated_values.txt`)

4. **Rebuild** the executables

### How It Works

1. `config_obfuscation.py` provides `_decode_string()` function for runtime decoding
2. `obfuscate_config.py` generates base64-encoded versions of sensitive values
3. `config.py` uses `_decode_string()` to decode obfuscated values at runtime
4. Nuitka compiles everything into machine code, making reverse engineering more difficult

**Note**: While obfuscation makes reverse engineering harder, it's not impossible. Always follow security best practices (rotating keys, IP restrictions, etc.).

## Build Output

After successful build:
- **64-bit executable**: `dist\win64\EcommProductManager_x64.exe`
- **32-bit executable**: `dist\win32\EcommProductManager_x86.exe`
- **Size**: Typically 50-150 MB per executable (includes Python runtime + all dependencies)

## Distribution

### File Structure

```
dist/
├── win64/
│   └── EcommProductManager_x64.exe  (for 64-bit Windows)
└── win32/
    └── EcommProductManager_x86.exe  (for 32-bit Windows)
```

### System Requirements

**Target systems** (where the .exe will run):
- **Windows 7 SP1+** (for 32-bit) or **Windows 10/11** (recommended)
- **No Python installation required**
- **Visual C++ Redistributable** (usually pre-installed on Windows 10/11)
  - If missing, download from: https://aka.ms/vs/17/release/vc_redist.x64.exe

### Testing the Build

1. **Test on the build machine**:
   ```powershell
   .\dist\win64\EcommProductManager_x64.exe
   ```

2. **Test on a clean Windows machine** (without Python installed) to ensure it's truly standalone

3. **Test both architectures** if you built both versions

## Troubleshooting

### Issue: Missing modules
**Solution**: Add `--include-module=module_name` to the build command in the build script.

### Issue: Missing data files
**Solution**: Add `--include-data-file=source=dest` or `--include-data-dir=source=dest` to the build script.

### Issue: Large executable size
**Solution**: This is normal for PySide6 apps. The executable includes Python runtime + all dependencies.

### Issue: Antivirus false positives
**Solution**: This is common with compiled Python executables. You may need to:
- Sign the executable with a code signing certificate
- Submit to antivirus vendors for whitelisting
- Use `--windows-uac-admin` if admin rights are needed

### Issue: Build fails with compiler errors
**Solution**: 
- Ensure Microsoft Visual C++ Build Tools are installed
- Try updating Nuitka: `pip install --upgrade nuitka`
- Check Python version compatibility

### Issue: Module not found at runtime
**Solution**: 
- Check that the module is included with `--include-module`
- For packages, use `--include-package=package_name`
- Check the Nuitka documentation for plugin-specific includes

## Advanced Configuration

### Code Signing (Recommended for Distribution)

Sign the executable after building to avoid antivirus false positives:

```powershell
# Using signtool (requires code signing certificate)
signtool sign /f your_certificate.pfx /p your_password /t http://timestamp.digicert.com dist\win64\EcommProductManager_x64.exe
```

### Custom Icon

Add a custom icon to the executable:

```powershell
# Add to build script:
--windows-icon-from-ico=icon.ico
```

### Additional Nuitka Flags

Optional flags you might want to add to the build scripts:

```powershell
--show-progress `                    # Show build progress
--show-memory `                      # Show memory usage
--remove-output `                    # Remove build directory after completion
--windows-uac-admin `               # Request admin privileges
--company-name="Your Company" `      # Set company name in executable metadata
--product-name="Ecomm Product Manager" `  # Set product name
--file-version="1.0.0.0" `          # Set file version
--product-version="1.0.0" `         # Set product version
```

## Security Best Practices

1. **Don't hardcode secrets** if avoidable:
   - Use AWS IAM roles where possible
   - Keep sensitive keys server-side when possible
   - Rotate API keys regularly

2. **Minimize embedded secrets**:
   - Cognito User Pool ID and Client ID are somewhat public (can be extracted from web apps)
   - API Gateway keys should be protected with IP restrictions
   - Use temporary credentials (Cognito Identity Pool) instead of permanent keys

3. **Runtime protection**:
   - Consider adding license validation
   - Add integrity checks
   - Monitor for tampering

4. **Distribution**:
   - Always sign executables for production use
   - Use HTTPS for downloads
   - Provide checksums for verification

## Manual Build Command

If you prefer to run the command directly (for 64-bit):

```powershell
python -m nuitka `
    --standalone `
    --onefile `
    --windows-disable-console `
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
    --output-dir=dist/win64 `
    --output-filename=EcommProductManager_x64.exe `
    --python-flag=no_warnings `
    --show-progress `
    main.py
```

## See Also

- [Nuitka Documentation](https://nuitka.net/doc/)
- [PySide6 Documentation](https://doc.qt.io/qtforpython/)
- Project README.md
