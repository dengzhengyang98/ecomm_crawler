"""
Scrapers module for E-Commerce Crawler.

Provides web scraping functionality for various e-commerce platforms.
"""

from .aliexpress import AliExpressScraper
from .amazon import AmazonScraper

__all__ = [
    'AliExpressScraper',
    'AmazonScraper',
]

