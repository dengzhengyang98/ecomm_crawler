# config/settings.py

# Import obfuscation helper
from config.obfuscation import _decode_string

# AWS Configuration
AWS_REGION = "us-west-2"
DYNAMODB_TABLE = "AliExpressProducts"

# AWS Cognito Configuration
# Obfuscated values to protect against reverse engineering
COGNITO_USER_POOL_ID = _decode_string("dXMtd2VzdC0yX3NCVWw2RFllZA==")
COGNITO_CLIENT_ID = _decode_string("MTdmNXVkMTQyODJvcTFoaXRuaHZubzY0N3E=")
COGNITO_REGION = "us-west-2"

# AWS Cognito Identity Pool Configuration (for DynamoDB access)
# Get this from AWS Console: Cognito > Federated Identities > Your Identity Pool
# Format: "us-west-2:XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
COGNITO_IDENTITY_POOL_ID = _decode_string("dXMtd2VzdC0yOjU4ZDkyZjU0LWRhMGUtNGVjZC1iYzVlLWVjMGMzYzY0ZmI2Ng==")

# Keyring service name for storing tokens securely
KEYRING_SERVICE_NAME = "EcommCrawler"

# Session validation interval (in milliseconds) - 5 minutes = 300,000 ms
SESSION_VALIDATION_INTERVAL_MS = 300000

# Local Storage
IMAGE_STORE_DIR = "./downloaded_images"

# Scraping Limits
MAX_PRODUCTS_TO_SCRAPE = 20

# Scraping Mode: "silent", "detailed", or "debug"
MODE = "detailed"

# --- API Gateway (suggested content) ---
# Fill these values if auth is needed.
API_GATEWAY_URL = _decode_string("aHR0cHM6Ly91NW9oa2dsdnc3LmV4ZWN1dGUtYXBpLnVzLXdlc3QtMi5hbWF6b25hd3MuY29tL2ludm9rZQ==")
API_GATEWAY_HEADERS = {
    # "x-api-key": _decode_string("your-obfuscated-api-key-here"),
    # "Authorization": "Bearer ",
}

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


# --- AMAZON CSS SELECTORS ---

# Search Page
# Primary selector: links inside search result items with s-no-outline class
AMAZON_SEARCH_ITEM_SELECTOR = "[data-component-type='s-search-result'] a.a-link-normal.s-no-outline"
# Fallback: any link containing /dp/
AMAZON_SEARCH_ITEM_FALLBACK = "a[href*='/dp/']"
AMAZON_SEARCH_ITEM_CONTAINER = "div[data-component-type='s-search-result']"

# Product Detail Page
# 1. Title
AMAZON_PRODUCT_TITLE_SELECTOR = "#productTitle"

# 2. Prices
AMAZON_PRODUCT_PRICE_SELECTOR = "span.a-price span.a-offscreen"  # Current/sale price
AMAZON_PRODUCT_PRICE_WHOLE = "span.a-price-whole"
AMAZON_PRODUCT_PRICE_FRACTION = "span.a-price-fraction"
AMAZON_PRODUCT_LIST_PRICE = "span.a-price[data-a-strike='true'] span.a-offscreen"  # Original/list price

# 3. Gallery Images
AMAZON_PRODUCT_GALLERY_SELECTOR = "#altImages img, #imageBlock img"
AMAZON_PRODUCT_MAIN_IMAGE = "#landingImage, #imgTagWrapperId img"
AMAZON_PRODUCT_THUMBNAIL_SELECTOR = "#altImages .imageThumbnail img"

# 4. SKU/Variants
# Primary: twister feature div contains all variant options
AMAZON_PRODUCT_VARIANT_CONTAINER = "#twister_feature_div"
AMAZON_PRODUCT_VARIANT_ITEMS = "#twister_feature_div li"
# Alternative selectors for different variant types
AMAZON_PRODUCT_VARIANT_IMAGES = "#twister li[data-defaultasin] img"
AMAZON_PRODUCT_VARIANT_BUTTONS = "#twister_feature_div li span.a-button-text"
AMAZON_PRODUCT_VARIANT_DROPDOWN = "#variation_size_name select option, #native_dropdown_selected_size_name option"

# 5. Description/About This Item
AMAZON_PRODUCT_FEATURE_BULLETS = "#feature-bullets ul li span.a-list-item"
AMAZON_PRODUCT_DESCRIPTION = "#productDescription"
AMAZON_PRODUCT_DESCRIPTION_TEXT = "#productDescription p"
AMAZON_PRODUCT_APluS_CONTENT = "#aplus, #dpx-aplus-product-description_feature_div"

# 6. Additional Info
AMAZON_PRODUCT_ASIN_SELECTOR = "th:contains('ASIN') + td"
AMAZON_PRODUCT_BRAND_SELECTOR = "#bylineInfo"
AMAZON_PRODUCT_RATING_SELECTOR = "#acrPopover"
AMAZON_PRODUCT_REVIEW_COUNT = "#acrCustomerReviewText"

# 7. Technical Details / Product Information
AMAZON_PRODUCT_TECH_DETAILS = "#productDetails_techSpec_section_1"
AMAZON_PRODUCT_INFO_TABLE = "#productDetails_detailBullets_sections1"

# 8. SKU/Variant "See more" link
AMAZON_SKU_SEE_MORE_LINK = "#twister-plus-inline-twister-card, a[id*='seeMoreLink'], .twisterSwatchViewAll, [id*='swatch_hover']"

# --- IMAGE FILTERING ---
# Images to skip (UI elements, icons, etc.)
AMAZON_SKIP_IMAGE_PATTERNS = [
    "360_icon",  # 360 view icon
    "play-icon",  # Video play icon
    "sprite",  # Sprite sheets
    "transparent-pixel",  # Tracking pixels
    "loading",  # Loading placeholders
    "G/01/x-locale",  # Amazon locale icons
]

# --- AMAZON PRICE COMPARISON ---
# When scraping AliExpress, search Amazon for competitor prices
ENABLE_AMAZON_PRICE_SEARCH = True
AMAZON_PRICE_SEARCH_MAX_RESULTS = 10

# --- PRICE CALCULATION ---
# Discount factor for final price calculation
# Final price logic:
#   if aliexpress_rec_price < amazon_min_price * discount → use aliexpress_rec_price
#   else if aliexpress_rec_price < amazon_min_price → use aliexpress_rec_price
#   else (aliexpress_rec_price >= amazon_min_price) → leave blank
PRICE_DISCOUNT = 0.95

# --- WAIT TIME CONFIGURATION ---
# All times are in seconds
# Page load wait times (min, max for random selection)
WAIT_PAGE_LOAD = (1.0, 2.0)
WAIT_SCROLL = (0.3, 0.8)
WAIT_ELEMENT_LOAD = (0.5, 1.0)
WAIT_BETWEEN_ACTIONS = (0.2, 0.5)
WAIT_BETWEEN_PRODUCTS = (1.5, 3.0)  # Delay between scraping products

# Explicit wait timeout for elements
ELEMENT_WAIT_TIMEOUT = 10

