"""
Script to obfuscate sensitive config values.
Run this script to generate obfuscated versions of sensitive configuration values.

Usage:
    python obfuscate_config.py
"""

import base64
from config_obfuscation import _obfuscate_string

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
    print("\nAdd these obfuscated values to config.py using _decode_string() function.\n")
    print("Example usage in config.py:")
    print("-" * 60)
    for key, obf_value in obfuscated.items():
        print(f"{key} = _decode_string(\"{obf_value}\")")
    print("-" * 60)
    
    # Also save to a file for easy copying
    with open("config_obfuscated_values.txt", "w") as f:
        f.write("# Obfuscated config values - Copy these to config.py\n")
        f.write("# Import _decode_string from config_obfuscation first\n\n")
        for key, obf_value in obfuscated.items():
            f.write(f"{key} = _decode_string(\"{obf_value}\")\n")
    
    print("\nObfuscated values have been saved to: config_obfuscated_values.txt")
    print("You can copy the values from there to config.py\n")

if __name__ == "__main__":
    main()

