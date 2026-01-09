"""
Cache utilities for E-Commerce Crawler.

Provides centralized cache directory management.
"""
import os

# Cache directories
CACHE_DIR = os.path.join(os.getcwd(), "cache")
PRODUCT_CACHE_DIR = os.path.join(CACHE_DIR, "products")
IMAGE_CACHE_DIR = os.path.join(CACHE_DIR, "images")


def ensure_dir(path: str):
    """Ensure a directory exists, creating it if necessary."""
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def get_cache_dir() -> str:
    """Get the main cache directory path."""
    ensure_dir(CACHE_DIR)
    return CACHE_DIR


def get_product_cache_dir() -> str:
    """Get the product cache directory path."""
    ensure_dir(PRODUCT_CACHE_DIR)
    return PRODUCT_CACHE_DIR


def get_image_cache_dir() -> str:
    """Get the image cache directory path."""
    ensure_dir(IMAGE_CACHE_DIR)
    return IMAGE_CACHE_DIR

