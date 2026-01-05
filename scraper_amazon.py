"""Amazon Product Scraper using Selenium/Firefox."""
import time
import os
import json
import requests
import boto3
import random
import uuid
import re
import platform
import subprocess
import shutil
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager

# --- CONFIGURATION ---
try:
    import config
except ImportError:
    pass

# Image processing
try:
    from image_processor import process_product_images
    IMAGE_PROCESSING_AVAILABLE = True
except ImportError:
    IMAGE_PROCESSING_AVAILABLE = False
    print("⚠️ Image processor not available. Install with: pip install rembg pillow boto3")

# Cache directories
CACHE_DIR = os.path.join(os.getcwd(), "cache")
PRODUCT_CACHE_DIR = os.path.join(CACHE_DIR, "products")
IMAGE_CACHE_DIR = os.path.join(CACHE_DIR, "images")

# --- CONSTANTS ---
PROFILE_DIR = os.path.join(os.getcwd(), 'firefox_real_profile')
if not os.path.exists(PROFILE_DIR):
    os.makedirs(PROFILE_DIR)


def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def get_geckodriver_path():
    """
    Get geckodriver path, ensuring the correct architecture for the system.
    On Apple Silicon (ARM64) Macs, ensures we get the ARM64 version.
    """
    try:
        # Get system architecture
        machine = platform.machine().lower()
        is_arm64_mac = (platform.system() == 'Darwin' and machine in ('arm64', 'aarch64'))
        
        # Install geckodriver
        driver_path = GeckoDriverManager().install()
        
        # If on ARM64 Mac, verify the binary architecture
        if is_arm64_mac and os.path.exists(driver_path):
            try:
                # Check if the binary is actually ARM64
                result = subprocess.run(['file', driver_path], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    file_output = result.stdout.lower()
                    # If it's x86_64 on ARM64, we need to force re-download
                    if 'x86_64' in file_output and 'arm64' not in file_output:
                        print(f"⚠️ Detected x86_64 geckodriver on ARM64 Mac. Removing cache to force re-download...")
                        # Remove the cached driver directory to force re-download
                        driver_dir = os.path.dirname(driver_path)
                        if os.path.exists(driver_dir):
                            try:
                                shutil.rmtree(os.path.dirname(driver_dir))  # Remove version directory
                                print(f"✅ Cache cleared. Re-downloading correct architecture...")
                                # Re-install to get correct architecture
                                driver_path = GeckoDriverManager().install()
                            except Exception as e:
                                print(f"⚠️ Could not clear cache: {e}")
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
                # file command might not be available, continue with downloaded driver
                pass
        
        return driver_path
    except Exception as e:
        print(f"⚠️ Error getting geckodriver: {e}")
        # Fallback to default behavior
        return GeckoDriverManager().install()


# --- UTILITIES ---
def generate_id():
    """Generates a unique ID for every run to allow re-crawling same URLs."""
    return str(uuid.uuid4())


def clean_url(url):
    """Clean and normalize Amazon URLs."""
    if url.startswith("//"):
        url = "https:" + url
    # Remove tracking parameters
    if "?" in url:
        base_url = url.split("?")[0]
        # Keep only essential params like th=1 for variants
        return base_url
    return url


def clean_amazon_image_url(url):
    """Clean Amazon image URLs to get high resolution version."""
    if not url:
        return None
    
    # Handle protocol-relative URLs
    if url.startswith("//"):
        url = "https:" + url
    
    # Amazon image URL patterns to clean
    # Example: https://m.media-amazon.com/images/I/71xyz123._AC_SX679_.jpg
    # We want: https://m.media-amazon.com/images/I/71xyz123.jpg
    
    # Remove size modifiers like _AC_SX679_, _AC_US40_, etc.
    url = re.sub(r'\._[A-Z]{2}_[A-Z]{2,}\d*_', '.', url)
    url = re.sub(r'\._[A-Z]+\d+_', '.', url)
    
    # Remove remaining underscores before extension
    url = re.sub(r'_+\.', '.', url)
    
    return url


def should_skip_image(url: str) -> bool:
    """Check if an image URL should be skipped (UI elements, icons, etc.)."""
    if not url:
        return True
    
    url_lower = url.lower()
    skip_patterns = getattr(config, 'AMAZON_SKIP_IMAGE_PATTERNS', [
        "360_icon", "play-icon", "sprite", "transparent-pixel", "loading", "G/01/x-locale"
    ])
    
    for pattern in skip_patterns:
        if pattern.lower() in url_lower:
            return True
    
    return False


def random_wait(wait_range: tuple) -> float:
    """Get a random wait time from config range and sleep."""
    min_wait, max_wait = wait_range
    delay = random.uniform(min_wait, max_wait)
    time.sleep(delay)
    return delay


def extract_asin_from_url(url: str) -> str:
    """Extract ASIN from Amazon product URL."""
    # Pattern: /dp/ASIN or /gp/product/ASIN
    patterns = [
        r'/dp/([A-Z0-9]{10})',
        r'/gp/product/([A-Z0-9]{10})',
        r'/product/([A-Z0-9]{10})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def download_image(url, folder_path, filename):
    if not url:
        return None
    ensure_dir(folder_path)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        }
        response = requests.get(url, stream=True, timeout=10, headers=headers)
        if response.status_code == 200:
            file_path = os.path.join(folder_path, filename)
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return file_path
    except Exception:
        pass
    return None


# --- MAIN SCRAPER CLASS ---
class AmazonScraper:
    def __init__(self, mode=None, resume_event=None):
        # Get mode from config if not provided, default to "detailed"
        self.mode = mode or getattr(config, 'MODE', 'detailed')
        self.debug_mode = (self.mode == "debug")
        self.silent_mode = (self.mode == "silent")
        self.detailed_mode = (self.mode == "detailed")
        self.resume_event = resume_event
        
        try:
            # Try to use Cognito Identity Pool credentials if authenticated
            from auth_service import get_dynamodb_resource
            self.dynamodb = get_dynamodb_resource()
            if self.dynamodb:
                self.table = self.dynamodb.Table(config.DYNAMODB_TABLE)
            else:
                raise Exception("Failed to get DynamoDB resource")
        except Exception as e:
            print(f"⚠️ Warning: DynamoDB connection failed ({e}). Running in local-only mode.")
            self.table = None
            self.dynamodb = None
        
        # Ensure cache directories
        ensure_dir(CACHE_DIR)
        ensure_dir(PRODUCT_CACHE_DIR)
        ensure_dir(IMAGE_CACHE_DIR)

        options = Options()
        options.add_argument("-profile")
        options.add_argument(PROFILE_DIR)
        options.add_argument('--window-size=1920,1080')  
        options.add_argument('--headless')
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        options.set_preference("general.useragent.override", user_agent)
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference('useAutomationExtension', False)
        options.set_preference("permissions.default.image", 1)
        options.set_preference("dom.webnotifications.enabled", False)
        options.set_preference("geo.enabled", False)

        print(f"🚀 Launching Firefox with profile: {PROFILE_DIR}")
        geckodriver_path = get_geckodriver_path()
        service = Service(geckodriver_path)
        self.driver = webdriver.Firefox(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 15)
    
    def debug_print(self, message):
        """Print debug message if debug mode is enabled."""
        if self.debug_mode:
            print(f"   [DEBUG] {message}")
    
    def scrape_product_details(self, url):
        """Scrape a single Amazon product page."""
        # 1. Generate Unique ID (UUID)
        p_id = generate_id()
        asin = extract_asin_from_url(url)

        if not self.silent_mode:
            print(f"\n--- SCRAPING: {p_id} ---")
            print(f"    URL: {url}")
            print(f"    ASIN: {asin}")
        else:
            print(f"Scraping: {url}")
        
        self.driver.get(url)
        random_wait(getattr(config, 'WAIT_PAGE_LOAD', (1.0, 2.0)))  # Wait for page load

        # Check for CAPTCHA
        if self._check_captcha():
            if not self.silent_mode:
                print("⚠️ CAPTCHA detected. Pausing for manual fix...")
            if getattr(self, "resume_event", None):
                print("Click Resume in UI after solving CAPTCHA...")
                self.resume_event.clear()
                self.resume_event.wait()
            else:
                input("Press ENTER after solving...")

        # Scroll to load lazy images
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
        random_wait(getattr(config, 'WAIT_SCROLL', (0.3, 0.8)))

        # Initialize data dict
        data = {
            'product_id': p_id,
            'asin': asin,
            'title': None,
            'url': url,
            'source': 'amazon',
        }

        try:
            # --- A. TITLE ---
            data['title'] = self._extract_title()
            
            # --- B. PRICES ---
            data['current_price'], data['original_price'] = self._extract_prices()
            
            # --- C. BRAND ---
            data['brand'] = self._extract_brand()
            
            # --- D. RATING ---
            data['rating'], data['review_count'] = self._extract_rating()
            
            # --- E. GALLERY IMAGES ---
            data['gallery_images'] = self._extract_gallery_images()
            
            # --- F. SKU/VARIANTS ---
            data['skus'] = self._extract_variants()
            
            # --- G. FEATURE BULLETS (Sellpoints) ---
            data['sellpoints'] = self._extract_feature_bullets()
            
            # --- H. DESCRIPTION ---
            data['description_text'], data['description_images'] = self._extract_description()
            
            # Add metadata
            data['status'] = 'scraped'
            data['timestamp'] = str(int(time.time()))

            # --- LOGGING ---
            if self.detailed_mode or self.debug_mode:
                title_preview = data.get('title', '')[:50] if data.get('title') else 'N/A'
                print(f"   Title: {title_preview}...")
                print(f"   Price: {data.get('current_price')}")
                print(f"   Brand: {data.get('brand')}")
                print(f"   Rating: {data.get('rating')} ({data.get('review_count')} reviews)")
                print(f"   Gallery Images: {len(data.get('gallery_images', []))}")
                print(f"   Variants: {len(data.get('skus', []))}")
                print(f"   Feature Bullets: {len(data.get('sellpoints', []))}")
                print(f"   Description Length: {len(data.get('description_text', ''))} chars")
                print(f"   Description Images: {len(data.get('description_images', []))}")

            # --- CALL API GATEWAY FOR SUGGESTED CONTENT ---
            try:
                input_text = f"{data.get('title','')}\n" + "\n".join(data.get('sellpoints', [])) + "\n" + data.get('description_text', '')
                payload = {"input_text": input_text}
                headers = {"Content-Type": "application/json"}
                try:
                    extra = getattr(config, "API_GATEWAY_HEADERS", {})
                    if isinstance(extra, dict):
                        headers.update(extra)
                except Exception:
                    pass
                api_url = getattr(config, "API_GATEWAY_URL", "")
                suggested = {}
                if api_url:
                    resp = requests.post(api_url, json=payload, headers=headers, timeout=30)
                    if resp.status_code == 200:
                        raw = resp.json() or {}
                        suggested = raw.get("result_structured", raw)
                        if not self.silent_mode:
                            print("✅ Suggested content received.")
                data["suggested_title"] = suggested.get("title", "")
                data["suggested_seller_point"] = suggested.get("bullet_point", "")
                data["suggested_description"] = suggested.get("description", "")
            except Exception as e:
                if not self.silent_mode:
                    print(f"⚠️ Suggested content API error: {e}")
                data["suggested_title"] = ""
                data["suggested_seller_point"] = ""
                data["suggested_description"] = ""

            # --- DOWNLOAD IMAGES LOCALLY ---
            try:
                product_img_dir = os.path.join(IMAGE_CACHE_DIR, p_id)
                gallery_dir = os.path.join(product_img_dir, "gallery")
                desc_dir = os.path.join(product_img_dir, "description")
                sku_dir = os.path.join(product_img_dir, "sku")
                
                # Preserve remote URLs
                data['gallery_images_remote'] = data.get('gallery_images', [])[:]
                data['description_images_remote'] = data.get('description_images', [])[:]
                skus_remote_list = []
                for sku in data.get('skus', []):
                    skus_remote_list.append({
                        "name": sku.get("name", ""),
                        "image_url_remote": sku.get("image_url", ""),
                        "image_url": sku.get("image_url", ""),
                    })
                
                # Gallery images
                gallery_local = []
                for idx, g_url in enumerate(data.get('gallery_images', [])):
                    local_path = download_image(g_url, gallery_dir, f"gallery_{idx}.jpg")
                    if local_path:
                        gallery_local.append(local_path)
                data['gallery_images'] = gallery_local
                
                # Description images
                desc_local = []
                for idx, d_url in enumerate(data.get('description_images', [])):
                    local_path = download_image(d_url, desc_dir, f"desc_{idx}.jpg")
                    if local_path:
                        desc_local.append(local_path)
                data['description_images'] = desc_local
                
                # SKU images
                skus_local = []
                for idx, sku in enumerate(data.get('skus', [])):
                    img_url = skus_remote_list[idx].get("image_url", "")
                    local_path = download_image(img_url, sku_dir, f"sku_{idx}.jpg")
                    merged = {
                        "name": sku.get("name", ""),
                        "image_url": local_path if local_path else skus_remote_list[idx].get("image_url", ""),
                        "image_url_remote": skus_remote_list[idx].get("image_url_remote", ""),
                    }
                    skus_local.append(merged)
                data['skus'] = skus_local
            except Exception as e:
                if not self.silent_mode:
                    print(f"⚠️ Image download error: {e}")
            
            # --- PROCESS IMAGES (Resize, Remove BG, Upload to S3) ---
            if IMAGE_PROCESSING_AVAILABLE:
                try:
                    if not self.silent_mode:
                        print("🖼️ Processing images...")
                    data = process_product_images(data, silent_mode=self.silent_mode)
                except Exception as e:
                    if not self.silent_mode:
                        print(f"⚠️ Image processing error: {e}")
            
            # --- SAVE LOCALLY (JSON per product) ---
            try:
                prod_path = os.path.join(PRODUCT_CACHE_DIR, f"{p_id}.json")
                with open(prod_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                if not self.silent_mode:
                    print(f"💾 Saved locally: {prod_path}")
            except Exception as e:
                if not self.silent_mode:
                    print(f"❌ Failed to save local JSON: {e}")

        except Exception as e:
            if not self.silent_mode:
                print(f"❌ Error scraping details: {e}")
                import traceback
                traceback.print_exc()
            else:
                print(f"Error: {e}")
    
    def _check_captcha(self) -> bool:
        """Check if Amazon CAPTCHA is present."""
        captcha_indicators = [
            "captcha",
            "robot check",
            "sorry! something went wrong",
        ]
        page_source = self.driver.page_source.lower()
        for indicator in captcha_indicators:
            if indicator in page_source:
                return True
        return False
    
    def _extract_title(self) -> str:
        """Extract product title."""
        try:
            title_el = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, config.AMAZON_PRODUCT_TITLE_SELECTOR))
            )
            return title_el.text.strip()
        except Exception as e:
            self.debug_print(f"Title extraction failed: {e}")
            return "Unknown"
    
    def _extract_prices(self) -> tuple:
        """Extract current and original prices."""
        current_price = "N/A"
        original_price = "N/A"
        
        try:
            # Try to get the main price
            price_selectors = [
                "#corePrice_feature_div span.a-price span.a-offscreen",
                "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen",
                "span.a-price span.a-offscreen",
                "#priceblock_ourprice",
                "#priceblock_dealprice",
                "#priceblock_saleprice",
            ]
            
            for selector in price_selectors:
                try:
                    price_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if price_elements:
                        price_text = price_elements[0].get_attribute("textContent") or price_elements[0].text
                        if price_text:
                            current_price = price_text.strip()
                            break
                except Exception:
                    continue
            
            # Try to get the original/list price
            list_price_selectors = [
                "span.a-price[data-a-strike='true'] span.a-offscreen",
                "#listPrice",
                "span.priceBlockStrikePriceString",
            ]
            
            for selector in list_price_selectors:
                try:
                    list_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if list_elements:
                        list_text = list_elements[0].get_attribute("textContent") or list_elements[0].text
                        if list_text:
                            original_price = list_text.strip()
                            break
                except Exception:
                    continue
                    
        except Exception as e:
            self.debug_print(f"Price extraction failed: {e}")
        
        return current_price, original_price
    
    def _extract_brand(self) -> str:
        """Extract brand name."""
        try:
            brand_el = self.driver.find_elements(By.CSS_SELECTOR, config.AMAZON_PRODUCT_BRAND_SELECTOR)
            if brand_el:
                brand_text = brand_el[0].text.strip()
                # Clean up "Visit the X Store" or "Brand: X" patterns
                brand_text = re.sub(r'^Visit the\s+', '', brand_text)
                brand_text = re.sub(r'\s+Store$', '', brand_text)
                brand_text = re.sub(r'^Brand:\s*', '', brand_text)
                return brand_text
        except Exception as e:
            self.debug_print(f"Brand extraction failed: {e}")
        return ""
    
    def _extract_rating(self) -> tuple:
        """Extract product rating and review count."""
        rating = ""
        review_count = ""
        
        try:
            rating_el = self.driver.find_elements(By.CSS_SELECTOR, config.AMAZON_PRODUCT_RATING_SELECTOR)
            if rating_el:
                rating_text = rating_el[0].get_attribute("title") or rating_el[0].text
                rating = rating_text.strip()
            
            review_el = self.driver.find_elements(By.CSS_SELECTOR, config.AMAZON_PRODUCT_REVIEW_COUNT)
            if review_el:
                review_text = review_el[0].text.strip()
                # Extract just the number
                review_count = re.sub(r'[^\d,]', '', review_text)
        except Exception as e:
            self.debug_print(f"Rating extraction failed: {e}")
        
        return rating, review_count
    
    def _extract_gallery_images(self) -> list:
        """Extract gallery images."""
        gallery_urls = []
        seen_urls = set()
        
        try:
            # First try to get the main/landing image
            main_img_selectors = [
                "#landingImage",
                "#imgTagWrapperId img",
                "#main-image-container img",
            ]
            
            for selector in main_img_selectors:
                try:
                    main_imgs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for img in main_imgs:
                        # Try data-old-hires first, then src
                        src = img.get_attribute("data-old-hires") or img.get_attribute("src")
                        if src and src not in seen_urls:
                            clean_src = clean_amazon_image_url(src)
                            if clean_src and not should_skip_image(clean_src):
                                gallery_urls.append(clean_src)
                                seen_urls.add(src)
                except Exception:
                    continue
            
            # Then get thumbnail images from altImages
            thumbnail_selectors = [
                "#altImages li.imageThumbnail img",
                "#altImages .a-button-thumbnail img",
                "#imageBlock_feature_div img",
            ]
            
            for selector in thumbnail_selectors:
                try:
                    thumb_imgs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for img in thumb_imgs:
                        src = img.get_attribute("src")
                        if src and src not in seen_urls:
                            clean_src = clean_amazon_image_url(src)
                            if clean_src and not should_skip_image(clean_src):
                                # Replace thumbnail size with larger size
                                clean_src = re.sub(r'\._[A-Z]{2}\d+_', '.', clean_src)
                                gallery_urls.append(clean_src)
                                seen_urls.add(src)
                except Exception:
                    continue
            
            if self.detailed_mode or self.debug_mode:
                print(f"   [+] Found {len(gallery_urls)} gallery images")
                
        except Exception as e:
            self.debug_print(f"Gallery extraction failed: {e}")
        
        return gallery_urls[:20]  # Limit to 20 images
    
    def _click_see_more_options(self):
        """Click 'See more options' link if present to reveal all variants."""
        see_more_selectors = [
            # Inline twister card (common for many options)
            "#twister-plus-inline-twister-card",
            # Various "See more" link patterns
            "a[id*='seeMoreLink']",
            "a.twisterSwatchViewAll",
            ".a-expander-header",
            # "See all X options" links
            "a[contains(text(), 'See all')]",
            "#twister .a-size-small a",
        ]
        
        for selector in see_more_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    text = el.text.lower()
                    if "see" in text or "more" in text or "all" in text or "option" in text:
                        if self.detailed_mode or self.debug_mode:
                            print(f"   [+] Clicking 'See more' link: {el.text[:30]}")
                        el.click()
                        random_wait(getattr(config, 'WAIT_ELEMENT_LOAD', (0.5, 1.0)))
                        return True
            except Exception:
                continue
        return False
    
    def _extract_variants(self) -> list:
        """Extract product variants/SKUs."""
        variants = []
        seen_names = set()
        
        try:
            # First, try to click "See more options" if there are many variants
            self._click_see_more_options()
            
            # Method 1: Look for variant items in twister_feature_div (most common)
            try:
                twister_items = self.driver.find_elements(By.CSS_SELECTOR, config.AMAZON_PRODUCT_VARIANT_ITEMS)
                if twister_items:
                    if self.detailed_mode or self.debug_mode:
                        print(f"   [+] Found {len(twister_items)} twister items")
                    
                    for item in twister_items:
                        try:
                            # Get the text content (variant name)
                            text = item.text.strip()
                            if not text:
                                continue
                            
                            # Clean up variant name - remove price if present
                            lines = text.split('\n')
                            name = lines[0].strip() if lines else text
                            
                            # Skip empty or very short names
                            if not name or len(name) < 2:
                                continue
                            
                            # Skip if already seen
                            if name in seen_names:
                                continue
                            
                            # Skip price-like patterns
                            if name.startswith('$') or re.match(r'^\$?\d+\.?\d*$', name):
                                continue
                            
                            # Try to get an image from inside this li
                            img_url = ""
                            try:
                                img = item.find_element(By.TAG_NAME, "img")
                                if img:
                                    src = img.get_attribute("src") or ""
                                    img_url = clean_amazon_image_url(src)
                            except Exception:
                                pass
                            
                            variants.append({
                                "name": name,
                                "image_url": img_url
                            })
                            seen_names.add(name)
                        except Exception:
                            continue
            except Exception:
                pass
            
            # Method 2: Look for variant images with data-defaultasin attribute
            if not variants:
                try:
                    variant_imgs = self.driver.find_elements(By.CSS_SELECTOR, config.AMAZON_PRODUCT_VARIANT_IMAGES)
                    for img in variant_imgs:
                        try:
                            name = img.get_attribute("alt") or ""
                            src = img.get_attribute("src") or ""
                            if name and name not in seen_names:
                                clean_src = clean_amazon_image_url(src)
                                variants.append({
                                    "name": name.strip(),
                                    "image_url": clean_src
                                })
                                seen_names.add(name)
                        except Exception:
                            continue
                except Exception:
                    pass
            
            # Method 3: Look for popup/modal variant images (after clicking "See more")
            if len(variants) < 5:
                try:
                    # These are images inside the expanded variant view
                    modal_imgs = self.driver.find_elements(By.CSS_SELECTOR, 
                        "#twister-plus-inline-twister-card img, .twister-swatch-plus img, li[data-asin] img")
                    for img in modal_imgs:
                        try:
                            name = img.get_attribute("alt") or ""
                            src = img.get_attribute("src") or ""
                            if name and name not in seen_names and not should_skip_image(src):
                                clean_src = clean_amazon_image_url(src)
                                variants.append({
                                    "name": name.strip(),
                                    "image_url": clean_src
                                })
                                seen_names.add(name)
                        except Exception:
                            continue
                except Exception:
                    pass
            
            # Method 4: Look for dropdown options (size selection)
            if not variants:
                try:
                    dropdown_options = self.driver.find_elements(By.CSS_SELECTOR, config.AMAZON_PRODUCT_VARIANT_DROPDOWN)
                    for option in dropdown_options:
                        try:
                            name = option.text.strip()
                            # Skip placeholder options
                            if name and "Select" not in name and name not in seen_names:
                                variants.append({
                                    "name": name,
                                    "image_url": ""
                                })
                                seen_names.add(name)
                        except Exception:
                            continue
                except Exception:
                    pass
            
            if self.detailed_mode or self.debug_mode:
                print(f"   [+] Found {len(variants)} variants/SKUs")
                for v in variants[:5]:
                    print(f"      - {v['name']}")
                
        except Exception as e:
            self.debug_print(f"Variant extraction failed: {e}")
        
        return variants
    
    def _extract_feature_bullets(self) -> list:
        """Extract feature bullet points (About this item)."""
        bullets = []
        
        try:
            bullet_selectors = [
                "#feature-bullets ul li span.a-list-item",
                "#feature-bullets li span",
                "#productFactsDesktopExpander ul li",
            ]
            
            for selector in bullet_selectors:
                try:
                    bullet_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in bullet_elements:
                        text = elem.text.strip()
                        # Filter out empty or very short bullets
                        if text and len(text) > 5 and text not in bullets:
                            # Skip "See more product details" type texts
                            if "see more" not in text.lower() and "make sure this fits" not in text.lower():
                                bullets.append(text)
                except Exception:
                    continue
            
            if self.detailed_mode or self.debug_mode:
                print(f"   [+] Found {len(bullets)} feature bullets")
                
        except Exception as e:
            self.debug_print(f"Feature bullets extraction failed: {e}")
        
        return bullets[:10]  # Limit to 10 bullets
    
    def _extract_description(self) -> tuple:
        """Extract product description text and images."""
        desc_text_parts = []
        desc_images = []
        seen_urls = set()
        
        try:
            # Scroll down to load description section
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            random_wait(getattr(config, 'WAIT_SCROLL', (0.3, 0.8)))
            
            # Extract text from product description
            desc_selectors = [
                "#productDescription p",
                "#productDescription",
                "#productDescription_feature_div",
            ]
            
            for selector in desc_selectors:
                try:
                    desc_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in desc_elements:
                        text = elem.text.strip()
                        if text and len(text) > 10:
                            desc_text_parts.append(text)
                except Exception:
                    continue
            
            # Extract from A+ content
            aplus_selectors = [
                "#aplus",
                "#dpx-aplus-product-description_feature_div",
                "#aplus_feature_div",
            ]
            
            for selector in aplus_selectors:
                try:
                    aplus_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for aplus in aplus_elements:
                        # Get text
                        aplus_text = aplus.text.strip()
                        if aplus_text and len(aplus_text) > 10:
                            desc_text_parts.append(aplus_text)
                        
                        # Get images from A+ content
                        aplus_imgs = aplus.find_elements(By.TAG_NAME, "img")
                        for img in aplus_imgs:
                            src = img.get_attribute("data-src") or img.get_attribute("src")
                            if src and src not in seen_urls:
                                clean_src = clean_amazon_image_url(src)
                                if clean_src and not should_skip_image(clean_src):
                                    desc_images.append(clean_src)
                                    seen_urls.add(src)
                except Exception:
                    continue
            
            if self.detailed_mode or self.debug_mode:
                print(f"   [+] Extracted description with {len(desc_text_parts)} text sections and {len(desc_images)} images")
                
        except Exception as e:
            self.debug_print(f"Description extraction failed: {e}")
        
        # Join text parts
        full_description = "\n\n".join(desc_text_parts)
        
        return full_description, desc_images[:20]  # Limit images
    
    def scrape_search_results(self, search_url=None):
        """Scrape Amazon search results page."""
        print("\n\n#####################################################")
        print("ACTION REQUIRED:")
        print("1. Navigate to the Amazon Search Results page.")
        print("   (e.g., https://www.amazon.com/s?k=bmw+headlight)")
        print("2. Solve any CAPTCHA if prompted.")
        if getattr(self, "resume_event", None):
            print("3. Click Resume in the UI when the results page is ready to be scraped...")
            self.resume_event.wait()
        else:
            input("3. Press ENTER in this console when the results page is ready to be scraped...")
        print("#####################################################\n")

        if not self.silent_mode:
            print("🔍 Starting scraping of current page...")

        # Scroll down multiple times to load lazy content
        for i in range(3):
            self.driver.execute_script("window.scrollBy(0, 800);")
            random_wait(getattr(config, 'WAIT_SCROLL', (0.3, 0.8)))
        
        # Scroll back to top
        self.driver.execute_script("window.scrollTo(0, 0);")
        random_wait(getattr(config, 'WAIT_SCROLL', (0.3, 0.8)))

        links_found = []
        
        # Method 1: Try the primary selector
        try:
            result_selector = config.AMAZON_SEARCH_ITEM_SELECTOR
            elements = self.driver.find_elements(By.CSS_SELECTOR, result_selector)
            
            if self.detailed_mode or self.debug_mode:
                print(f"   [+] Primary selector found {len(elements)} elements")

            for el in elements:
                raw_href = el.get_attribute("href")
                if raw_href and "/dp/" in raw_href:
                    clean_href = clean_url(raw_href)
                    if clean_href not in links_found:
                        links_found.append(clean_href)
        except Exception as e:
            if not self.silent_mode:
                print(f"   [!] Primary selector error: {e}")
        
        # Method 2: Fallback - find all links with /dp/
        if len(links_found) < 5:
            try:
                fallback_selector = config.AMAZON_SEARCH_ITEM_FALLBACK
                all_dp_links = self.driver.find_elements(By.CSS_SELECTOR, fallback_selector)
                
                if self.detailed_mode or self.debug_mode:
                    print(f"   [+] Fallback selector found {len(all_dp_links)} /dp/ links")
                
                for el in all_dp_links:
                    raw_href = el.get_attribute("href")
                    if raw_href and "/dp/" in raw_href:
                        # Skip sponsored/ad links (usually have tracking redirects)
                        if "aax-us-east" not in raw_href and "amazon-adsystem" not in raw_href:
                            clean_href = clean_url(raw_href)
                            if clean_href not in links_found:
                                links_found.append(clean_href)
            except Exception as e:
                if not self.silent_mode:
                    print(f"   [!] Fallback selector error: {e}")
        
        # Remove duplicates while preserving order
        unique_links = list(dict.fromkeys(links_found))

        if self.detailed_mode or self.debug_mode:
            print(f"✅ Found {len(unique_links)} unique product links on the page.")
        
        if not unique_links:
            print("⚠️ No product links found. Please ensure you are on an Amazon search results page.")
            print("   Example URL: https://www.amazon.com/s?k=bmw+headlight")
            return
        
        targets = unique_links[:config.MAX_PRODUCTS_TO_SCRAPE]
        if self.detailed_mode or self.debug_mode:
            print(f"🎯 Targeting the following {len(targets)} links:")
            for link in targets:
                print(f"   -> {link}")

        for link in targets:
            self.scrape_product_details(link)

            # Add randomized delay between pages
            wait_range = getattr(config, 'WAIT_BETWEEN_PRODUCTS', (1.5, 3.0))
            delay = random_wait(wait_range)
            if self.detailed_mode or self.debug_mode:
                print(f"   (Paused for {delay:.2f}s)")


if __name__ == "__main__":
    import sys
    # Allow override via command line
    mode = None
    if "--debug" in sys.argv or "-d" in sys.argv:
        mode = "debug"
    elif "--silent" in sys.argv or "-s" in sys.argv:
        mode = "silent"
    elif "--detailed" in sys.argv:
        mode = "detailed"
    
    bot = AmazonScraper(mode=mode)
    # Test with search results
    bot.scrape_search_results()

