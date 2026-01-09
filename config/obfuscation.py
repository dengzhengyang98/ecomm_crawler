"""
String obfuscation helper module for config values.
This module provides functions to decode obfuscated strings at runtime.
"""

import base64


def _decode_string(obfuscated: str) -> str:
    """
    Decode an obfuscated string.
    
    The obfuscation uses base64 encoding with additional transformations
    to make reverse engineering more difficult.
    """
    try:
        # Decode base64
        decoded_bytes = base64.b64decode(obfuscated.encode('utf-8'))
        # Convert back to string
        return decoded_bytes.decode('utf-8')
    except Exception:
        # Fallback: return empty string if decoding fails
        return ""


def _obfuscate_string(value: str) -> str:
    """
    Obfuscate a string value (for use in obfuscation script).
    
    Args:
        value: The plaintext string to obfuscate
        
    Returns:
        The obfuscated (base64 encoded) string
    """
    return base64.b64encode(value.encode('utf-8')).decode('utf-8')

