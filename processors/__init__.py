"""
Processors module for E-Commerce Crawler.

Provides image processing and other data processing utilities.
"""

from processors.image import (
    ImageProcessor,
    S3_BUCKET,
    CLOUDFRONT_DOMAIN,
    TARGET_SIZE,
    get_processor,
    process_product_images,
)

__all__ = [
    'ImageProcessor',
    'S3_BUCKET',
    'CLOUDFRONT_DOMAIN',
    'TARGET_SIZE',
    'get_processor',
    'process_product_images',
]

