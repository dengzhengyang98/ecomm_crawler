"""
Script to obfuscate sensitive config values.
Run this script to generate obfuscated versions of sensitive configuration values.

Usage:
    python tools/obfuscate_config.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.obfuscation import _obfuscate_string

# Sensitive values from config.py that should be obfuscated
SENSITIVE_VALUES = {
    "COGNITO_USER_POOL_ID": "us-west-2_sBUl6DYed",
    "COGNITO_CLIENT_ID": "17f5ud14282oq1hitnhvno647q",
    "COGNITO_IDENTITY_POOL_ID": "us-west-2:58d92f54-da0e-4ecd-bc5e-ec0c3c64fb66",
    "API_GATEWAY_URL": "https://u5ohkglvw7.execute-api.us-west-2.amazonaws.com/invoke",
    # Add API keys here if needed:
    # "API_GATEWAY_KEY": "your-api-key-here",
}

def main():
    print("=" * 60)
    print("Config Obfuscation Tool")
    print("=" * 60)
    print("\nObfuscating sensitive configuration values...\n")
    
    obfuscated = {}
    for key, value in SENSITIVE_VALUES.items():
        obfuscated_value = _obfuscate_string(value)
        obfuscated[key] = obfuscated_value
        print(f"{key}:")
        print(f"  Original: {value}")
        print(f"  Obfuscated: {obfuscated_value}")
        print()
    
    print("=" * 60)
    print("Obfuscation Complete!")
    print("=" * 60)
    print("\nAdd these obfuscated values to config/settings.py using _decode_string() function.\n")
    print("Example usage in config/settings.py:")
    print("-" * 60)
    for key, obf_value in obfuscated.items():
        print(f"{key} = _decode_string(\"{obf_value}\")")
    print("-" * 60)
    
    # Also save to a file for easy copying
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config_obfuscated_values.txt")
    with open(output_path, "w") as f:
        f.write("# Obfuscated config values - Copy these to config/settings.py\n")
        f.write("# Import _decode_string from config.obfuscation first\n\n")
        for key, obf_value in obfuscated.items():
            f.write(f"{key} = _decode_string(\"{obf_value}\")\n")
    
    print(f"\nObfuscated values have been saved to: {output_path}")
    print("You can copy the values from there to config/settings.py\n")

if __name__ == "__main__":
    main()

