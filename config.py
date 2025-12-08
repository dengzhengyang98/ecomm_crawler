# config.py

# AWS Configuration
AWS_REGION = "us-west-2"
DYNAMODB_TABLE = "AliExpressProducts"

# Local Storage
IMAGE_STORE_DIR = "./downloaded_images"

# Scraping Limits
MAX_PRODUCTS_TO_SCRAPE = 10

# --- CSS SELECTORS ---

# Search Page
SEARCH_ITEM_SELECTOR = "a.search-card-item"

# Product Detail Page
# 1. Title
PRODUCT_TITLE_SELECTOR = "h1[data-pl='product-title']"

# 2. Prices
PRODUCT_PRICE_CURRENT_SELECTOR = "span[class*='price-default--current']"
PRODUCT_PRICE_ORIGINAL_SELECTOR = "span[class*='price-default--original']"

# 3. Gallery
PRODUCT_GALLERY_SELECTOR = "div[class*='slider--img'] img"

# 4. SKUs
PRODUCT_SKU_SELECTOR = "div[data-sku-col] img"

# 5. Description
# Main container for rich text (images + text)
PRODUCT_DESCRIPTION_CONTAINER = "#product-description"
# The div that contains the Shadow DOM (nested inside product-description)
PRODUCT_DESCRIPTION_SHADOW_HOST = "#product-description > div[data-spm-anchor-id]"
# The richtext element inside Shadow DOM
PRODUCT_DESCRIPTION_RICHTEXT = ".product-description"
# Hidden SEO description that appears after expanding
PRODUCT_SEO_DESCRIPTION = "div[data-pl='seo-description']"
# The "View More" button to expand description
PRODUCT_DESC_VIEW_MORE_BTN = "button[class*='extend--btn']"
# Sellpoints (seller points) - class name has variable part, so use partial match
PRODUCT_SELLPOINTS_SELECTOR = "ul[class*='seo-sellpoints--sellerPoint']"