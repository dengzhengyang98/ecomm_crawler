# Build Quick Reference

## Quick Commands

### Build All Architectures
```powershell
.\build_nuitka_all.ps1
```

### Build Specific Architecture
```powershell
# 64-bit only
.\build_nuitka_win64.ps1

# 32-bit only
.\build_nuitka_win32.ps1

# Or use the unified script
.\build_nuitka_all.ps1 -Architecture x64
.\build_nuitka_all.ps1 -Architecture x86
```

### Clean Build
```powershell
.\build_nuitka_all.ps1 -Clean
```

## Output Locations

- **64-bit**: `dist\win64\EcommProductManager_x64.exe`
- **32-bit**: `dist\win32\EcommProductManager_x86.exe`

## Updating Obfuscated Config Values

1. Edit `obfuscate_config.py` with new values
2. Run: `python obfuscate_config.py`
3. Copy obfuscated values to `config.py`
4. Rebuild executables

## File Structure

```
.
├── build_nuitka_all.ps1       # Unified build script (recommended)
├── build_nuitka_win64.ps1     # 64-bit build script
├── build_nuitka_win32.ps1     # 32-bit build script
├── config.py                   # Main config (uses obfuscated values)
├── config_obfuscation.py       # Obfuscation helper module
├── obfuscate_config.py         # Script to generate obfuscated values
└── dist/
    ├── win64/
    │   └── EcommProductManager_x64.exe
    └── win32/
        └── EcommProductManager_x86.exe
```

## Key Features

✅ **Nuitka compilation** - Machine code, better protection  
✅ **String obfuscation** - Sensitive values protected  
✅ **Multi-architecture** - Both 32-bit and 64-bit support  
✅ **Standalone** - No Python required on target machines  

See `BUILD_INSTRUCTIONS.md` for detailed documentation.

