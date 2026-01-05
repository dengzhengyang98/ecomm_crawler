import time
import hashlib
import os
import json
import requests
import boto3
import random
import uuid  # Added for unique IDs
import re
import urllib.parse
import platform
import subprocess
import shutil
import itertools
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
    if url.startswith("//"):
        url = "https:" + url
    if ".html" in url:
        return url.split(".html")[0] + ".html"
    return url


def clean_image_url(url):
    if not url: return None
    # Remove query params first (e.g., ?width=800&height=800&hash=1600)
    base_url = url.split("?")[0]
    # Remove trailing patterns like _220x220q75.jpg_.avif, _main.jpg, _profile.jpg, etc.
    # Pattern: _[dimensions][quality][format].[ext]_.avif or similar
    # Example: https://ae-pic-a1.aliexpress-media.com/kf/S2041dd6b7379433da5ed1bf55ccdbef7s.jpg_220x220q75.jpg_.avif
    # Should become: https://ae-pic-a1.aliexpress-media.com/kf/S2041dd6b7379433da5ed1bf55ccdbef7s.jpg
    base_url = re.sub(r'_\d+x\d+[^.]*\.(jpg|jpeg|png|webp)(_\.avif)?$', '', base_url, flags=re.IGNORECASE)
    base_url = re.sub(r'_main\.(jpg|jpeg|png|webp)$', r'.\1', base_url, flags=re.IGNORECASE)
    base_url = re.sub(r'_profile\.(jpg|jpeg|png|webp)$', r'.\1', base_url, flags=re.IGNORECASE)
    # Handle protocol-relative URLs
    if base_url.startswith("//"):
        base_url = "https:" + base_url
    return base_url


def download_image(url, folder_path, filename):
    if not url: return None
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


def random_wait(wait_range: tuple) -> float:
    """Get a random wait time from config range and sleep."""
    min_wait, max_wait = wait_range
    delay = random.uniform(min_wait, max_wait)
    time.sleep(delay)
    return delay


def parse_price_to_float(price_str: str) -> float:
    """Parse a price string like '$1,234.56' to float. Returns 0 if invalid."""
    if not price_str or price_str == "N/A":
        return 0.0
    try:
        cleaned = price_str.replace("$", "").replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def calculate_amazon_price_stats(amazon_prices: dict, aliexpress_price: str) -> dict:
    """
    Calculate Amazon price statistics from the competitor prices map.
    
    Args:
        amazon_prices: Dict mapping product titles to price info.
            Can be either old format: {"Product A": "$19.99"}
            Or new format: {"Product A": {"price": "$19.99", "url": "https://..."}}
        aliexpress_price: The AliExpress price string
    
    Returns dict with:
        - amazon_avg_price: Average of all Amazon prices
        - amazon_min_price: Minimum Amazon price
        - amazon_min_price_product: Product name with minimum price
        - amazon_min_price_product_url: URL of the product with minimum price
        - ali_express_rec_price: Recommended AliExpress price (same as input for now)
    """
    if not amazon_prices:
        return {
            "amazon_avg_price": "N/A",
            "amazon_min_price": "N/A",
            "amazon_min_price_product": "N/A",
            "amazon_min_price_product_url": "",
            "ali_express_rec_price": aliexpress_price or "N/A"
        }
    
    # Parse all prices - handle both old and new format
    valid_prices = []
    min_price = float('inf')
    min_product = ""
    min_product_url = ""
    
    for product, price_info in amazon_prices.items():
        # Handle new format: {"price": "$19.99", "url": "..."}
        if isinstance(price_info, dict):
            price_str = price_info.get("price", "N/A")
            url = price_info.get("url", "")
        else:
            # Handle old format: just the price string
            price_str = price_info
            url = ""
        
        price_float = parse_price_to_float(price_str)
        if price_float > 0:
            valid_prices.append(price_float)
            if price_float < min_price:
                min_price = price_float
                min_product = product
                min_product_url = url
    
    if not valid_prices:
        return {
            "amazon_avg_price": "N/A",
            "amazon_min_price": "N/A",
            "amazon_min_price_product": "N/A",
            "amazon_min_price_product_url": "",
            "ali_express_rec_price": aliexpress_price or "N/A"
        }
    
    avg_price = sum(valid_prices) / len(valid_prices)
    
    return {
        "amazon_avg_price": f"${avg_price:,.2f}",
        "amazon_min_price": f"${min_price:,.2f}",
        "amazon_min_price_product": min_product,
        "amazon_min_price_product_url": min_product_url,
        "ali_express_rec_price": aliexpress_price or "N/A"
    }


def search_amazon_prices_with_driver(driver, query: str, max_results: int = 10) -> dict:
    """
    Search Amazon for a product using existing Selenium driver and return a map of product titles to price info.
    
    Args:
        driver: Selenium WebDriver instance
        query: The search query (product title)
        max_results: Maximum number of results to return (default 10)
        
    Returns:
        Dict mapping product titles to price info, e.g. 
        {"Product A": {"price": "$19.99", "url": "https://amazon.com/dp/..."}}
    """
    if not query or not driver:
        return {}
    
    # NOTE: We don't store/restore original URL since we've already scraped the product
    
    try:
        # Build Amazon search URL
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.amazon.com/s?k={encoded_query}"
        
        driver.get(search_url)
        time.sleep(2)  # Wait for page load
        
        results = {}
        
        # Find search result containers
        try:
            from selenium.webdriver.common.by import By
            result_elements = driver.find_elements(By.CSS_SELECTOR, "[data-component-type='s-search-result']")
            
            for elem in result_elements[:max_results]:
                try:
                    # Get title and URL from the title link
                    title_link = elem.find_elements(By.CSS_SELECTOR, "h2 a.a-link-normal")
                    if not title_link:
                        # Fallback to other link patterns
                        title_link = elem.find_elements(By.CSS_SELECTOR, "a.a-link-normal.s-no-outline")
                    
                    title = ""
                    url = ""
                    
                    if title_link:
                        # Get URL from the link
                        href = title_link[0].get_attribute("href")
                        if href:
                            url = href
                        # Get title from span inside the link or the link text
                        title_span = title_link[0].find_elements(By.CSS_SELECTOR, "span")
                        if title_span:
                            title = title_span[0].text.strip()
                        else:
                            title = title_link[0].text.strip()
                    
                    # Fallback: try other title selectors if no title found
                    if not title:
                        title_elem = elem.find_elements(By.CSS_SELECTOR, "h2 a span, .a-size-medium.a-text-normal, .a-size-base-plus.a-text-normal")
                        if title_elem:
                            title = title_elem[0].text.strip()
                    
                    # Get price
                    price = "N/A"
                    price_elem = elem.find_elements(By.CSS_SELECTOR, "span.a-price span.a-offscreen")
                    if price_elem:
                        price = price_elem[0].get_attribute("textContent").strip()
                    else:
                        # Try alternative price selectors
                        price_whole = elem.find_elements(By.CSS_SELECTOR, "span.a-price-whole")
                        price_frac = elem.find_elements(By.CSS_SELECTOR, "span.a-price-fraction")
                        if price_whole:
                            whole = price_whole[0].text.replace(",", "")
                            frac = price_frac[0].text if price_frac else "00"
                            price = f"${whole}.{frac}"
                    
                    if title and len(results) < max_results:
                        results[title] = {"price": price, "url": url}
                        
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"   [!] Error parsing Amazon results: {e}")
        
        return results
        
    except Exception as e:
        print(f"   [!] Amazon search error: {e}")
        return {}


# --- MAIN SCRAPER CLASS ---
class AliExpressScraper:
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
        self.wait = WebDriverWait(self.driver, 10)
    
    def debug_print_element(self, element, name="Element", max_html_length=500):
        """Print detailed information about an element for debugging."""
        if not self.debug_mode:
            return
        
        try:
            tag = element.tag_name
            classes = element.get_attribute('class') or ''
            text_preview = (element.text or '')[:200]
            html_preview = (element.get_attribute('outerHTML') or '')[:max_html_length]
            element_id = element.get_attribute('id') or ''
            
            print(f"\n{'='*60}")
            print(f"🔍 DEBUG: {name}")
            print(f"{'='*60}")
            print(f"Tag: {tag}")
            if element_id:
                print(f"ID: {element_id}")
            if classes:
                print(f"Classes: {classes}")
            print(f"Text preview ({len(element.text) if element.text else 0} chars):")
            print(f"  {text_preview}...")
            print(f"\nHTML preview ({len(html_preview)} chars):")
            print(f"  {html_preview}...")
            print(f"{'='*60}\n")
        except Exception as e:
            print(f"   [!] Error printing element: {e}")
    
    def debug_find_and_print(self, selector, name=None):
        """Find elements by selector and print their details."""
        if not self.debug_mode:
            return []
        
        name = name or selector
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            print(f"\n🔍 DEBUG: Found {len(elements)} element(s) with selector: {selector}")
            
            for idx, elem in enumerate(elements[:5]):  # Print first 5
                self.debug_print_element(elem, f"{name} #{idx + 1}")
            
            if len(elements) > 5:
                print(f"   ... and {len(elements) - 5} more elements")
            
            return elements
        except Exception as e:
            print(f"   [!] Error finding elements: {e}")
            return []
    
    def debug_pause(self, message="Press ENTER to continue..."):
        """Pause execution for manual inspection."""
        if self.debug_mode:
            print(f"\n⏸️  DEBUG PAUSE: {message}")
            print("   You can now inspect the browser manually.")
            input("   Press ENTER to continue...\n")
    
    def debug_save_html(self, filename, element=None):
        """Save HTML to file for inspection."""
        if not self.debug_mode:
            return
        
        debug_dir = os.path.join(os.getcwd(), 'debug_html')
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        
        filepath = os.path.join(debug_dir, filename)
        try:
            if element:
                html_content = element.get_attribute('outerHTML')
            else:
                html_content = self.driver.page_source
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"   💾 Saved HTML to: {filepath}")
        except Exception as e:
            print(f"   [!] Failed to save HTML: {e}")
    
    def debug_execute_js(self, js_code, description="JavaScript"):
        """Execute JavaScript and print result for debugging."""
        if not self.debug_mode:
            return None
        
        try:
            result = self.driver.execute_script(js_code)
            print(f"\n🔍 DEBUG: {description}")
            print(f"Result: {result}")
            return result
        except Exception as e:
            print(f"   [!] JavaScript error: {e}")
            return None
    
    def debug_check_shadow_dom(self, selector):
        """Check if an element has Shadow DOM and print details."""
        if not self.debug_mode:
            return False
        
        try:
            element = self.driver.find_element(By.CSS_SELECTOR, selector)
            has_shadow = self.driver.execute_script("""
                return arguments[0].shadowRoot !== null;
            """, element)
            
            print(f"\n🔍 DEBUG: Shadow DOM Check for '{selector}'")
            print(f"   Element found: {element.tag_name}")
            print(f"   Has Shadow DOM: {has_shadow}")
            
            if has_shadow:
                try:
                    shadow_root = element.shadow_root
                    shadow_info = self.driver.execute_script("""
                        var root = arguments[0].shadowRoot;
                        if (root) {
                            return {
                                mode: root.mode,
                                hasContent: root.innerHTML.length > 0,
                                innerHTMLPreview: root.innerHTML.substring(0, 200)
                            };
                        }
                        return null;
                    """, element)
                    print(f"   Shadow Root Info: {shadow_info}")
                except Exception as e:
                    print(f"   [!] Cannot access shadow root: {e}")
            
            return has_shadow
        except Exception as e:
            print(f"   [!] Error checking Shadow DOM: {e}")
            return False
    
    def debug_interactive_selector(self):
        """Interactive mode to test CSS selectors."""
        if not self.debug_mode:
            return
        
        print("\n" + "="*60)
        print("🔍 INTERACTIVE SELECTOR TESTING")
        print("="*60)
        print("Enter CSS selectors to test (or 'quit' to exit)")
        
        while True:
            try:
                selector = input("\nEnter CSS selector: ").strip()
                if selector.lower() in ['quit', 'exit', 'q']:
                    break
                
                if not selector:
                    continue
                
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                print(f"\nFound {len(elements)} element(s)")
                
                if elements:
                    for idx, elem in enumerate(elements[:3]):  # Show first 3
                        self.debug_print_element(elem, f"Element #{idx + 1}")
                    
                    if len(elements) > 3:
                        print(f"\n   ... and {len(elements) - 3} more elements")
                else:
                    print("   No elements found with this selector")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"   [!] Error: {e}")
        
        print("\nExiting interactive mode...")
    
    def find_shadow_dom_element(self, shadow_host_selector, shadow_root_selector=None):
        """Find and access Shadow DOM elements."""
        try:
            # Find the shadow host element
            shadow_host = self.driver.find_element(By.CSS_SELECTOR, shadow_host_selector)
            
            # Access the shadow root
            shadow_root = shadow_host.shadow_root
            
            if shadow_root_selector:
                # Find elements inside shadow root
                return shadow_root.find_elements(By.CSS_SELECTOR, shadow_root_selector)
            else:
                return shadow_root
        except Exception as e:
            if self.debug_mode:
                print(f"   [!] Shadow DOM access failed: {e}")
            return None
    
    def extract_from_shadow_dom(self, shadow_host_selector):
        """Extract images and text from Shadow DOM."""
        images = []
        text = ""
        
        try:
            shadow_host = self.driver.find_element(By.CSS_SELECTOR, shadow_host_selector)
            shadow_root = shadow_host.shadow_root
            
            if self.debug_mode:
                print(f"   [+] Found Shadow DOM host: {shadow_host.tag_name}")
                print(f"   [+] Shadow root accessible: {shadow_root is not None}")
            
            # Extract text
            try:
                text = shadow_root.text
            except:
                pass
            
            # Extract images
            try:
                img_elements = shadow_root.find_elements(By.CSS_SELECTOR, "img")
                if self.debug_mode:
                    print(f"   [+] Found {len(img_elements)} images in Shadow DOM")
                
                for img in img_elements:
                    src = img.get_attribute("src")
                    if src and src.strip() and src != "image" and "alicdn.com" in src:
                        clean_src = clean_image_url(src)
                        if clean_src:
                            images.append(clean_src)
            except Exception as e:
                if self.debug_mode:
                    print(f"   [!] Error extracting images from Shadow DOM: {e}")
            
            return text, images
        except Exception as e:
            if self.debug_mode:
                print(f"   [!] Shadow DOM extraction failed: {e}")
            return "", []

    def _check_and_handle_captcha(self) -> bool:
        """
        Check for CAPTCHA and pause if detected. Returns True if CAPTCHA was found and handled.
        
        Detects AliExpress CAPTCHA by checking for:
        - J_MIDDLEWARE_FRAME_WIDGET class (main CAPTCHA overlay)
        - baxia-dialog-content ID (alternative CAPTCHA dialog)
        """
        captcha_selectors = [
            ".J_MIDDLEWARE_FRAME_WIDGET",  # Main AliExpress CAPTCHA overlay
            "#baxia-dialog-content",        # Alternative CAPTCHA dialog
            "div[class*='MIDDLEWARE_FRAME']",  # Partial class match
        ]
        
        captcha_found = False
        for selector in captcha_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and len(elements) > 0:
                    # Check if the element is actually visible
                    for el in elements:
                        if el.is_displayed():
                            captcha_found = True
                            break
                if captcha_found:
                    break
            except Exception:
                continue
        
        if captcha_found:
            if not self.silent_mode:
                print("\n" + "="*60)
                print("⚠️  CAPTCHA DETECTED! Scraping paused.")
                print("="*60)
                print("   Please solve the CAPTCHA in the browser.")
            
            if getattr(self, "resume_event", None):
                print("   Click 'Resume' button in UI after solving...")
                self.resume_event.clear()
                self.resume_event.wait()
            else:
                input("   Press ENTER after solving CAPTCHA...")
            
            if not self.silent_mode:
                print("✅ Resuming scraping...")
            
            # Wait a moment for page to stabilize after CAPTCHA
            random_wait(getattr(config, 'WAIT_PAGE_LOAD', (1.0, 2.0)))
            return True
        
        return False

    def _extract_sku_combinations(self):
        """
        Extract all SKU combinations by finding all SKU rows (properties) and their options,
        then generate all possible combinations.
        
        Returns:
            List of SKU combination dicts with 'name', 'image_url', 'options', and 'elements'
        """
        sku_combinations = []
        
        try:
            # Find all SKU rows (properties) - each row represents a different property
            sku_rows = self.driver.find_elements(By.CSS_SELECTOR, "div[data-sku-row]")
            
            if not sku_rows:
                if self.debug_mode:
                    print("   ⚠️  No SKU rows found")
                return []
            
            if self.detailed_mode or self.debug_mode:
                print(f"   🔍 Found {len(sku_rows)} SKU property row(s)")
            
            # Extract property information and options for each row
            sku_properties = []
            for row_idx, row in enumerate(sku_rows):
                try:
                    # Get property name (title) - e.g., "Color Temperature:", "Color:"
                    # The title is in a parent container, not directly in the row
                    property_name = ""
                    try:
                        # Find the property container (parent of the row)
                        property_container = row.find_element(By.XPATH, "./ancestor::div[contains(@class, 'sku-item--property')]")
                        # Get the title element
                        title_elem = property_container.find_element(By.CSS_SELECTOR, ".sku-item--title--Z0HLO87, .sku-item--title")
                        # Get the first span (property name), not nested spans (selected value)
                        title_spans = title_elem.find_elements(By.TAG_NAME, "span")
                        if title_spans:
                            # First span contains the property name (e.g., "Color Temperature:&nbsp;2PS")
                            # We need to extract just "Color Temperature" without the nested span content
                            first_span = title_spans[0]
                            # Get text content, but exclude nested span text
                            property_name = self.driver.execute_script("""
                                var span = arguments[0];
                                var text = span.childNodes[0] ? span.childNodes[0].textContent : span.textContent;
                                return text ? text.trim() : '';
                            """, first_span)
                            if not property_name:
                                # Fallback: get all text and remove nested content
                                property_name = first_span.text.strip()
                            # Clean up: remove "&nbsp;", ":", and any trailing content
                            property_name = property_name.replace("&nbsp;", " ").replace(":", "").strip()
                            # Remove any trailing numbers or selected values
                            property_name = re.sub(r'\s+\d+.*$', '', property_name).strip()
                    except:
                        try:
                            # Alternative: try to find title in row's parent
                            parent = row.find_element(By.XPATH, "./ancestor::div[contains(@class, 'sku-item--property')]")
                            title_elem = parent.find_element(By.CSS_SELECTOR, ".sku-item--title")
                            # Get text but exclude nested spans
                            property_name = title_elem.text.strip()
                            # Remove nested content (selected values)
                            property_name = re.sub(r':\s*\S+.*$', '', property_name).replace(":", "").strip()
                        except:
                            property_name = f"Property {row_idx + 1}"
                    
                    # Get all options in this row
                    # Options might be in the row itself or in a nested container
                    options = []
                    option_elements = row.find_elements(By.CSS_SELECTOR, "div[data-sku-col]")
                    
                    # If no elements found in row, try finding in parent container
                    if not option_elements:
                        try:
                            property_container = row.find_element(By.XPATH, "./ancestor::div[contains(@class, 'sku-item--property')]")
                            option_elements = property_container.find_elements(By.CSS_SELECTOR, "div[data-sku-col]")
                        except:
                            pass
                    
                    for opt_elem in option_elements:
                        try:
                            # Get option name
                            opt_name = opt_elem.get_attribute("title")
                            if not opt_name or not opt_name.strip():
                                # Try image alt text
                                try:
                                    img = opt_elem.find_element(By.TAG_NAME, "img")
                                    opt_name = img.get_attribute("alt")
                                except:
                                    # Try span text
                                    try:
                                        span = opt_elem.find_element(By.TAG_NAME, "span")
                                        opt_name = span.text.strip()
                                    except:
                                        opt_name = opt_elem.text.strip()
                            
                            # Get image URL if available
                            opt_image_url = ""
                            try:
                                img = opt_elem.find_element(By.TAG_NAME, "img")
                                opt_image_url = clean_image_url(img.get_attribute("src"))
                            except:
                                pass
                            
                            if opt_name and opt_name.strip():
                                options.append({
                                    "name": opt_name.strip(),
                                    "image_url": opt_image_url,
                                    "element": opt_elem
                                })
                        except Exception as e:
                            if self.debug_mode:
                                print(f"      [!] Error extracting option: {e}")
                            continue
                    
                    if options:
                        sku_properties.append({
                            "property_name": property_name,
                            "options": options
                        })
                        if self.detailed_mode or self.debug_mode:
                            print(f"      [{row_idx + 1}] {property_name}: {len(options)} option(s)")
                            for opt in options[:3]:  # Show first 3
                                print(f"         - {opt['name']}")
                            if len(options) > 3:
                                print(f"         ... and {len(options) - 3} more")
                
                except Exception as e:
                    if self.debug_mode:
                        print(f"      [!] Error processing SKU row {row_idx + 1}: {e}")
                    continue
            
            # Generate all combinations using itertools.product
            if not sku_properties:
                if self.debug_mode:
                    print("   ⚠️  No SKU properties found")
                return []
            
            # Generate all combinations
            all_option_lists = [prop["options"] for prop in sku_properties]
            all_combinations = list(itertools.product(*all_option_lists))
            
            if self.detailed_mode or self.debug_mode:
                print(f"   📦 Generated {len(all_combinations)} SKU combination(s)")
            
            # Create SKU combination data
            for combo_idx, combination in enumerate(all_combinations):
                # Build combination name (e.g., "2PS, For Original Xenon")
                combo_parts = []
                combo_images = []
                combo_elements = []
                
                for prop_idx, option in enumerate(combination):
                    combo_parts.append(option["name"])
                    if option["image_url"]:
                        combo_images.append(option["image_url"])
                    combo_elements.append(option["element"])
                
                combo_name = ", ".join(combo_parts)
                # Use first available image, or empty string
                combo_image_url = combo_images[0] if combo_images else ""
                
                sku_combinations.append({
                    "name": combo_name,
                    "image_url": combo_image_url,
                    "options": combo_parts,  # List of option names
                    "elements": combo_elements  # List of elements to click
                })
            
        except Exception as e:
            if not self.silent_mode:
                print(f"   [!] Error extracting SKU combinations: {e}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()
        
        return sku_combinations

    def _extract_sku_prices(self, sku_combinations):
        """
        Iterate through all SKU combinations, click each combination, and extract prices.
        
        Args:
            sku_combinations: List of SKU combination dicts with 'name', 'image_url', 'options', and 'elements'
            
        Returns:
            List of SKU dicts with added 'current_price' and 'history_price' fields
        """
        if not sku_combinations:
            return []
        
        sku_data_with_prices = []
        
        try:
            # Get the default/initial price first
            default_current_price = "N/A"
            default_original_price = "N/A"
            try:
                current_price_el = self.driver.find_element(By.CSS_SELECTOR, config.PRODUCT_PRICE_CURRENT_SELECTOR)
                default_current_price = current_price_el.text.replace("US $", "").strip()
            except:
                pass
            
            try:
                orig_price_el = self.driver.find_element(By.CSS_SELECTOR, config.PRODUCT_PRICE_ORIGINAL_SELECTOR)
                default_original_price = orig_price_el.text.replace("US $", "").strip()
            except:
                pass
            
            if self.detailed_mode or self.debug_mode:
                print(f"   📊 Extracting prices for {len(sku_combinations)} SKU combination(s)...")
                print(f"   💰 Default price: {default_current_price}")
            
            # Scroll to SKU section to ensure visibility
            try:
                first_row = self.driver.find_elements(By.CSS_SELECTOR, "div[data-sku-row]")
                if first_row:
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", first_row[0])
                    random_wait(getattr(config, 'WAIT_ELEMENT_LOAD', (0.5, 1.0)))
            except:
                pass
            
            # Iterate through each SKU combination and get its price
            for idx, combo in enumerate(sku_combinations):
                combo_name = combo.get("name", "")
                combo_image_url = combo.get("image_url", "")
                combo_elements = combo.get("elements", [])
                
                # Initialize with default price
                current_price = default_current_price
                original_price = default_original_price
                
                if combo_elements:
                    try:
                        # Click all elements in the combination to select it
                        # Scroll to first element
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", combo_elements[0])
                        random_wait(getattr(config, 'WAIT_BETWEEN_ACTIONS', (0.2, 0.5)))
                        
                        # Click each element in the combination
                        for elem_idx, element in enumerate(combo_elements):
                            try:
                                # Check if already selected
                                is_selected = False
                                try:
                                    element_class = element.get_attribute("class") or ""
                                    if "selected" in element_class.lower() or "active" in element_class.lower():
                                        is_selected = True
                                except:
                                    pass
                                
                                if not is_selected:
                                    # Scroll element into view
                                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                                    random_wait(getattr(config, 'WAIT_BETWEEN_ACTIONS', (0.1, 0.3)))
                                    
                                    # Click the element
                                    self.driver.execute_script("arguments[0].click();", element)
                                    if self.detailed_mode or self.debug_mode:
                                        opt_name = combo.get("options", [])[elem_idx] if elem_idx < len(combo.get("options", [])) else "option"
                                        print(f"         Clicked: {opt_name}")
                                    
                                    # Small delay between clicks
                                    random_wait(getattr(config, 'WAIT_BETWEEN_ACTIONS', (0.2, 0.4)))
                            except Exception as click_e:
                                if self.debug_mode:
                                    print(f"         [!] Error clicking element {elem_idx + 1}: {click_e}")
                        
                        # Wait for price to update after selecting the combination
                        random_wait(getattr(config, 'WAIT_ELEMENT_LOAD', (0.5, 1.0)))
                        
                        # Wait for price to change (up to 3 seconds)
                        max_wait_time = 3.0
                        wait_interval = 0.2
                        waited = 0.0
                        previous_price = default_current_price
                        
                        while waited < max_wait_time:
                            try:
                                new_price_el = self.driver.find_element(By.CSS_SELECTOR, config.PRODUCT_PRICE_CURRENT_SELECTOR)
                                new_price_text = new_price_el.text.replace("US $", "").strip()
                                if new_price_text != previous_price:
                                    current_price = new_price_text
                                    previous_price = new_price_text
                                    time.sleep(0.3)
                                    break
                            except:
                                pass
                            time.sleep(wait_interval)
                            waited += wait_interval
                        
                        # Extract current price (final check)
                        try:
                            current_price_el = self.driver.find_element(By.CSS_SELECTOR, config.PRODUCT_PRICE_CURRENT_SELECTOR)
                            current_price = current_price_el.text.replace("US $", "").strip()
                        except:
                            pass
                        
                        # Extract history/original price
                        try:
                            orig_price_el = self.driver.find_element(By.CSS_SELECTOR, config.PRODUCT_PRICE_ORIGINAL_SELECTOR)
                            original_price = orig_price_el.text.replace("US $", "").strip()
                        except:
                            pass
                        
                        if self.detailed_mode or self.debug_mode:
                            if current_price != default_current_price:
                                print(f"      ✅ [{idx + 1}/{len(sku_combinations)}] {combo_name}: {current_price} (different from default {default_current_price})")
                            else:
                                print(f"      ✓ [{idx + 1}/{len(sku_combinations)}] {combo_name}: {current_price}")
                    
                    except Exception as e:
                        if self.debug_mode:
                            print(f"      [!] Error processing SKU combination {combo_name}: {e}")
                            import traceback
                            traceback.print_exc()
                else:
                    if self.debug_mode:
                        print(f"      [-] No elements found for combination: {combo_name}")
                
                # Add SKU with price information
                sku_with_price = {
                    "name": combo_name,
                    "image_url": combo_image_url,
                    "current_price": current_price,
                    "history_price": original_price
                }
                sku_data_with_prices.append(sku_with_price)
                
                # Small delay between combinations
                if idx < len(sku_combinations) - 1:
                    random_wait(getattr(config, 'WAIT_BETWEEN_ACTIONS', (0.3, 0.6)))
            
        except Exception as e:
            if not self.silent_mode:
                print(f"   [!] Error extracting SKU prices: {e}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()
            
            # Fallback: return SKUs with default prices
            for combo in sku_combinations:
                sku_with_price = {
                    "name": combo.get("name", ""),
                    "image_url": combo.get("image_url", ""),
                    "current_price": "N/A",
                    "history_price": "N/A"
                }
                sku_data_with_prices.append(sku_with_price)
        
        return sku_data_with_prices

    def scrape_product_details(self, url):
        # 1. Generate Unique ID (UUID) instead of Hash
        p_id = generate_id()

        if not self.silent_mode:
            print(f"\n--- SCRAPING: {p_id} ---")
            print(f"    URL: {url}")
        else:
            print(f"Scraping: {url}")
        self.driver.get(url)
        
        # Wait for page to load
        random_wait(getattr(config, 'WAIT_PAGE_LOAD', (1.0, 2.0)))

        # CAPTCHA Check - check immediately after page load
        self._check_and_handle_captcha()

        # IMPORTANT: Extract SKUs and prices FIRST, before any scrolling
        # Initialize data dict early for SKU extraction
        data = {
            'product_id': p_id,
            'title': None,  # Will be set later
            'url': url,
        }
        
        # Extract SKUs and prices at the very beginning
        sku_data = []
        try:
            if self.detailed_mode or self.debug_mode:
                print("   📦 Extracting SKUs and prices (at beginning, before scrolling)...")
            
            # Wait for page to render SKU elements
            random_wait(getattr(config, 'WAIT_ELEMENT_LOAD', (0.5, 1.0)))
            
            # Try to find SKU container/row first to scroll into view
            try:
                sku_rows = self.driver.find_elements(By.CSS_SELECTOR, "div[data-sku-row]")
                if not sku_rows:
                    sku_rows = self.driver.find_elements(By.CSS_SELECTOR, "div[class*='sku-item--skus']")
                
                if sku_rows:
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", sku_rows[0])
                    random_wait(getattr(config, 'WAIT_ELEMENT_LOAD', (0.5, 1.0)))
                    if self.detailed_mode or self.debug_mode:
                        print(f"   [+] Found {len(sku_rows)} SKU row(s), scrolled into view")
            except Exception as e:
                if self.debug_mode:
                    print(f"   [!] Could not find SKU rows container: {e}")
            
            # Wait for SKU elements to be present
            try:
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-sku-col]")))
            except:
                random_wait(getattr(config, 'WAIT_ELEMENT_LOAD', (0.5, 1.0)))
            
            # Extract SKU combinations (handles multiple properties/rows)
            sku_combinations = self._extract_sku_combinations()
            
            if sku_combinations:
                if self.detailed_mode or self.debug_mode:
                    print(f"   🔍 Found {len(sku_combinations)} SKU combination(s), extracting prices...")
                # Extract prices for each combination
                sku_data = self._extract_sku_prices(sku_combinations)
            else:
                # Fallback: try old method (single property)
                if self.detailed_mode or self.debug_mode:
                    print("   ⚠️  No SKU combinations found, trying fallback method...")
                
                sku_containers = self.driver.find_elements(By.CSS_SELECTOR, "div[data-sku-col]")
                if sku_containers:
                    for idx, container in enumerate(sku_containers):
                        try:
                            sku_name = container.get_attribute("title")
                            sku_image_url = ""
                            
                            try:
                                img_el = container.find_element(By.TAG_NAME, "img")
                                if img_el:
                                    if not sku_name or not sku_name.strip():
                                        sku_name = img_el.get_attribute("alt")
                                    sku_src = clean_image_url(img_el.get_attribute("src"))
                                    if sku_src:
                                        sku_image_url = sku_src
                            except:
                                if not sku_name or not sku_name.strip():
                                    try:
                                        span = container.find_element(By.TAG_NAME, "span")
                                        sku_name = span.text.strip() if span else ""
                                    except:
                                        sku_name = container.text.strip()
                            
                            if sku_name and sku_name.strip():
                                sku_data.append({
                                    "name": sku_name.strip(),
                                    "image_url": sku_image_url,
                                    "current_price": "N/A",
                                    "history_price": "N/A"
                                })
                        except:
                            continue
                else:
                    # Last fallback: try image-based SKUs using old selector
                    try:
                        sku_imgs = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_SKU_SELECTOR)
                        for img_el in sku_imgs:
                            sku_name = img_el.get_attribute("alt")
                            sku_src = clean_image_url(img_el.get_attribute("src"))
                            if sku_name and sku_src:
                                sku_data.append({
                                    "name": sku_name,
                                    "image_url": sku_src,
                                    "current_price": "N/A",
                                    "history_price": "N/A"
                                })
                    except:
                        pass
            
            data['skus'] = sku_data
        except Exception as e:
            if not self.silent_mode:
                print(f"   [!] Error extracting SKUs: {e}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()
            data['skus'] = []

        # 2. SCROLL & EXPAND DESCRIPTION
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
        random_wait(getattr(config, 'WAIT_SCROLL', (0.3, 0.8)))
        
        # Check for CAPTCHA after scroll (can appear after any action)
        self._check_and_handle_captcha()

        # Try to find and click "View More" button
        try:
            # First check if button exists without waiting
            view_more_btn = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_DESC_VIEW_MORE_BTN)
            if view_more_btn:
                if self.detailed_mode or self.debug_mode:
                    print("   [+] Found 'View More' button, scrolling to it...")
                # Scroll the button into view
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", view_more_btn[0])
                random_wait(getattr(config, 'WAIT_SCROLL', (0.3, 0.8)))
                
                # Wait for button to be clickable
                clickable_btn = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, config.PRODUCT_DESC_VIEW_MORE_BTN))
                )
                if self.detailed_mode or self.debug_mode:
                    print("   [+] Clicking 'View More' button...")
                self.driver.execute_script("arguments[0].click();", clickable_btn)
                random_wait(getattr(config, 'WAIT_PAGE_LOAD', (1.0, 2.0)))  # Wait for content to load
                
                # Wait for SEO description to appear
                try:
                    self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, config.PRODUCT_SEO_DESCRIPTION))
                    )
                    if self.detailed_mode or self.debug_mode:
                        print("   [+] SEO description loaded after clicking 'View More'")
                except:
                    if self.detailed_mode or self.debug_mode:
                        print("   [-] SEO description not found after clicking (may already be visible)")
            else:
                if self.detailed_mode or self.debug_mode:
                    print("   [-] No 'View More' button found (content might be short or already expanded).")
        except Exception as e:
            if self.detailed_mode or self.debug_mode:
                print(f"   [!] Error with 'View More' button: {e}")

        # Scroll further down to ensure images lazy load
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 1.5);")
        random_wait(getattr(config, 'WAIT_PAGE_LOAD', (1.0, 2.0)))
        
        # Scroll to description container to trigger lazy loading of images
        try:
            desc_container = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_DESCRIPTION_CONTAINER)
            if desc_container:
                # Scroll to description area
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'start'});", desc_container[0])
                random_wait(getattr(config, 'WAIT_ELEMENT_LOAD', (0.5, 1.0)))  # Wait for images to load
        except:
            pass
        
        # DEBUG: Interactive selector testing
        if self.debug_mode:
            response = input("\n🔍 Enter interactive selector testing mode? (y/n): ").strip().lower()
            if response == 'y':
                self.debug_interactive_selector()

        try:
            # --- A. TITLE ---
            try:
                title_el = self.wait.until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, config.PRODUCT_TITLE_SELECTOR)))
                data['title'] = title_el.text
            except:
                data['title'] = "Unknown"

            # --- B. PRICES ---
            try:
                current_price_el = self.driver.find_element(By.CSS_SELECTOR, config.PRODUCT_PRICE_CURRENT_SELECTOR)
                data['current_price'] = current_price_el.text.replace("US $", "").strip()
            except:
                data['current_price'] = "N/A"

            try:
                orig_price_el = self.driver.find_element(By.CSS_SELECTOR, config.PRODUCT_PRICE_ORIGINAL_SELECTOR)
                data['original_price'] = orig_price_el.text.replace("US $", "").strip()
            except:
                data['original_price'] = "N/A"

            # --- C. GALLERY ---
            gallery_urls = []
            try:
                imgs = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_GALLERY_SELECTOR)
                for img in imgs:
                    raw_src = img.get_attribute("src")
                    clean_src = clean_image_url(raw_src)
                    if clean_src and clean_src not in gallery_urls:
                        gallery_urls.append(clean_src)
                data['gallery_images'] = gallery_urls
            except Exception as e:
                data['gallery_images'] = []

            # --- D. SKUS ---
            # SKUs were already extracted at the beginning, so data['skus'] should already be set
            # If not set (fallback case), try to extract again here
            if 'skus' not in data or not data.get('skus'):
                sku_data = []
                try:
                    sku_imgs = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_SKU_SELECTOR)
                    for img_el in sku_imgs:
                        sku_name = img_el.get_attribute("alt")
                        sku_src = clean_image_url(img_el.get_attribute("src"))
                        if sku_name and sku_src:
                            sku_data.append({"name": sku_name, "image_url": sku_src})
                    data['skus'] = sku_data
                except:
                    data['skus'] = []

            # --- E. DESCRIPTION (Text & Images) ---
            desc_text_parts = []
            desc_img_urls = []

            try:
                # 1. Rich Text Container (Main Description)
                if self.debug_mode:
                    print("\n" + "="*60)
                    print("🔍 DEBUG: Looking for description container")
                    print("="*60)
                    self.debug_find_and_print(config.PRODUCT_DESCRIPTION_CONTAINER, "Description Container")
                    
                    # Check for Shadow DOM
                    print("\n🔍 DEBUG: Checking for Shadow DOM...")
                    shadow_host_selector = getattr(config, 'PRODUCT_DESCRIPTION_SHADOW_HOST', '#product-description > div[data-spm-anchor-id]')
                    self.debug_check_shadow_dom(shadow_host_selector)
                    self.debug_check_shadow_dom(config.PRODUCT_DESCRIPTION_CONTAINER)
                
                # First, try to find Shadow DOM
                # The Shadow DOM is inside a nested div within #product-description
                shadow_dom_found = False
                try:
                    # Find the product-description container first
                    product_desc = self.driver.find_element(By.CSS_SELECTOR, config.PRODUCT_DESCRIPTION_CONTAINER)
                    
                    # Find the nested div that contains the Shadow DOM
                    # This is the div with data-spm-anchor-id inside #product-description
                    shadow_host_selector = getattr(config, 'PRODUCT_DESCRIPTION_SHADOW_HOST', '#product-description > div[data-spm-anchor-id]')
                    
                    try:
                        shadow_host = product_desc.find_element(By.CSS_SELECTOR, "#product-description > div:nth-child(1)")
                    except:
                        # Try finding it directly
                        try:
                            shadow_host = self.driver.find_element(By.CSS_SELECTOR, shadow_host_selector)
                        except:
                            shadow_host = None
                    
                    if shadow_host:
                        if self.debug_mode:
                            print(f"\n🔍 DEBUG: Found potential Shadow DOM host: {shadow_host.tag_name}")
                            self.debug_print_element(shadow_host, "Shadow DOM Host")
                        
                        # Try to access shadow root
                        try:
                            shadow_root = shadow_host.shadow_root
                            if shadow_root:
                                shadow_dom_found = True
                                if self.detailed_mode or self.debug_mode:
                                    print("   [+] Shadow DOM detected! Extracting from Shadow DOM...")
                                
                                if self.debug_mode:
                                    # Check what's inside shadow root
                                    shadow_content = self.driver.execute_script("""
                                        var host = arguments[0];
                                        var root = host.shadowRoot;
                                        if (root) {
                                            var richtext = root.querySelector('.product-description');
                                            return {
                                                hasContent: root.innerHTML.length > 0,
                                                hasRichtext: richtext !== null,
                                                imgCount: root.querySelectorAll('img').length,
                                                richtextImgCount: richtext ? richtext.querySelectorAll('img').length : 0,
                                                textLength: root.textContent ? root.textContent.length : 0
                                            };
                                        }
                                        return null;
                                    """, shadow_host)
                                    print(f"   [DEBUG] Shadow root content: {shadow_content}")
                                
                                # Find the richtext element inside Shadow DOM
                                richtext_selector = getattr(config, 'PRODUCT_DESCRIPTION_RICHTEXT', '.product-description')
                                try:
                                    shadow_richtext = shadow_root.find_element(By.CSS_SELECTOR, richtext_selector)
                                    
                                    # Extract text from Shadow DOM richtext
                                    try:
                                        shadow_text = shadow_richtext.text
                                        if shadow_text and shadow_text.strip():
                                            desc_text_parts.append(shadow_text)
                                            if self.detailed_mode or self.debug_mode:
                                                print(f"   [+] Extracted {len(shadow_text)} chars of text from Shadow DOM")
                                    except Exception as e:
                                        if self.debug_mode:
                                            print(f"   [!] Error extracting text from Shadow DOM: {e}")
                                    
                                    # Extract images from Shadow DOM richtext
                                    try:
                                        shadow_imgs = shadow_richtext.find_elements(By.CSS_SELECTOR, "img")
                                        if self.detailed_mode or self.debug_mode:
                                            print(f"   [+] Found {len(shadow_imgs)} images in Shadow DOM richtext")
                                        
                                        for idx, img in enumerate(shadow_imgs):
                                            try:
                                                src = img.get_attribute("src")
                                                if not src or src.strip() == "":
                                                    src = img.get_attribute("data-src")
                                                
                                                if src and src.strip() and src != "image" and "alicdn.com" in src:
                                                    clean_src = clean_image_url(src)
                                                    if clean_src and clean_src not in desc_img_urls:
                                                        desc_img_urls.append(clean_src)
                                                        if self.detailed_mode or self.debug_mode:
                                                            print(f"      [+] Extracted image {idx + 1}: {clean_src[:60]}...")
                                            except Exception as img_e:
                                                if self.debug_mode:
                                                    print(f"      [!] Error extracting image {idx + 1}: {img_e}")
                                                continue
                                    except Exception as e:
                                        if self.debug_mode:
                                            print(f"   [!] Error finding images in Shadow DOM richtext: {e}")
                                        
                                        # Fallback: try finding images directly in shadow root
                                        try:
                                            shadow_imgs = shadow_root.find_elements(By.CSS_SELECTOR, "img.detail-desc-decorate-image, img[slate-data-type='image']")
                                            if self.detailed_mode or self.debug_mode:
                                                print(f"   [+] Fallback: Found {len(shadow_imgs)} images in Shadow DOM")
                                            for idx, img in enumerate(shadow_imgs):
                                                try:
                                                    src = img.get_attribute("src")
                                                    if src and src.strip() and src != "image" and "alicdn.com" in src:
                                                        clean_src = clean_image_url(src)
                                                        if clean_src and clean_src not in desc_img_urls:
                                                            desc_img_urls.append(clean_src)
                                                            if self.detailed_mode or self.debug_mode:
                                                                print(f"      [+] Extracted image {idx + 1}: {clean_src[:60]}...")
                                                except:
                                                    continue
                                        except:
                                            pass
                                except Exception as e:
                                    if self.debug_mode:
                                        print(f"   [!] Richtext element not found in Shadow DOM: {e}")
                        except Exception as e:
                            if self.debug_mode:
                                print(f"   [!] Cannot access shadow root: {e}")
                                import traceback
                                traceback.print_exc()
                    else:
                        if self.debug_mode:
                            print("   [-] Shadow DOM host div not found")
                except Exception as e:
                    if self.debug_mode:
                        print(f"   [-] Shadow DOM detection failed: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Fallback to regular DOM if Shadow DOM not found or failed
                if not shadow_dom_found:
                    rich_text_container = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_DESCRIPTION_CONTAINER)
                    if rich_text_container:
                        container = rich_text_container[0]
                        
                        if self.debug_mode:
                            self.debug_print_element(container, "Description Container (Regular DOM)")
                            self.debug_save_html(f"{p_id}_description_container.html", container)
                        
                        container_text = container.text
                        if container_text and container_text.strip():
                            desc_text_parts.append(container_text)
                        
                        # Try to find richtext element inside container
                        richtext_elem = None
                        try:
                            richtext_elem = container.find_element(By.CSS_SELECTOR, ".product-description")
                            if self.debug_mode:
                                self.debug_print_element(richtext_elem, "Richtext Element Found")
                        except:
                            try:
                                richtext_elem = self.driver.find_element(By.CSS_SELECTOR, ".product-description")
                            except:
                                pass
                        
                        # Use richtext element if found, otherwise use container
                        search_container = richtext_elem if richtext_elem else container
                        
                        # Scroll to trigger lazy loading
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'start'});", search_container)
                        random_wait(getattr(config, 'WAIT_ELEMENT_LOAD', (0.5, 1.0)))
                        
                        # Extract Images from Rich Text (Regular DOM)
                        imgs = search_container.find_elements(By.TAG_NAME, "img")
                        if self.detailed_mode or self.debug_mode:
                            print(f"   [+] Found {len(imgs)} image elements in description (Regular DOM)")
                        
                        for idx, img in enumerate(imgs):
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", img)
                                random_wait(getattr(config, 'WAIT_BETWEEN_ACTIONS', (0.2, 0.5)))
                                
                                src = img.get_attribute("src")
                                if not src or src.strip() == "":
                                    src = img.get_attribute("data-src")
                                if not src or src.strip() == "":
                                    src = img.get_attribute("data-lazy-src")
                                
                                if src and src.strip() and src != "image" and "alicdn.com" in src:
                                    clean_src = clean_image_url(src)
                                    if clean_src and clean_src not in desc_img_urls:
                                        desc_img_urls.append(clean_src)
                                        if self.detailed_mode or self.debug_mode:
                                            print(f"      [+] Extracted image {idx + 1}: {clean_src[:60]}...")
                            except Exception as img_e:
                                if self.debug_mode:
                                    print(f"      [!] Error extracting image {idx + 1}: {img_e}")
                                continue

                # 2. SEO Description (Hidden/Expanded text)
                seo_desc_container = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_SEO_DESCRIPTION)
                if seo_desc_container:
                    seo_text = seo_desc_container[0].text
                    if seo_text and seo_text.strip():
                        desc_text_parts.append(seo_text)
                        if self.detailed_mode or self.debug_mode:
                            print("   [+] Extracted SEO description text")

                data['description_text'] = "\n\n".join(desc_text_parts)
                data['description_images'] = desc_img_urls

            except Exception as e:
                print(f"   [!] Description parse error: {e}")
                import traceback
                traceback.print_exc()
                data['description_text'] = ""
                data['description_images'] = []

            # --- F. SELLPOINTS (Seller Points) ---
            sellpoints = []
            try:
                sellpoints_container = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_SELLPOINTS_SELECTOR)
                if sellpoints_container:
                    # Find all <li> elements inside the sellpoints container
                    list_items = sellpoints_container[0].find_elements(By.TAG_NAME, "li")
                    if self.detailed_mode or self.debug_mode:
                        print(f"   [+] Found {len(list_items)} sellpoint(s)")
                    
                    for idx, li in enumerate(list_items):
                        try:
                            # Get text from <pre> tag inside <li>
                            pre_elem = li.find_element(By.TAG_NAME, "pre")
                            sellpoint_text = pre_elem.text.strip()
                            if sellpoint_text:
                                sellpoints.append(sellpoint_text)
                                if self.debug_mode:
                                    print(f"      [+] Sellpoint {idx + 1}: {sellpoint_text[:60]}...")
                        except:
                            # Fallback: get text directly from <li> if no <pre> tag
                            try:
                                sellpoint_text = li.text.strip()
                                if sellpoint_text:
                                    sellpoints.append(sellpoint_text)
                            except:
                                continue
                    
                    data['sellpoints'] = sellpoints
                    if self.detailed_mode or self.debug_mode:
                        print(f"   [+] Extracted {len(sellpoints)} sellpoint(s)")
                else:
                    data['sellpoints'] = []
            except Exception as e:
                if self.debug_mode:
                    print(f"   [!] Error extracting sellpoints: {e}")
                    import traceback
                    traceback.print_exc()
                data['sellpoints'] = []

            # Add remaining fields in desired order
            data['current_price'] = data.get('current_price', 'N/A')
            data['original_price'] = data.get('original_price', 'N/A')
            data['gallery_images'] = data.get('gallery_images', [])
            data['skus'] = data.get('skus', [])
            data['description_text'] = data.get('description_text', '')
            data['description_images'] = data.get('description_images', [])
            data['sellpoints'] = data.get('sellpoints', [])
            data['status'] = 'scraped'
            data['timestamp'] = str(int(time.time()))

            # --- LOGGING ---
            if self.detailed_mode or self.debug_mode:
                print(f"   Title: {data.get('title')[:30]}...")
                print(f"   Price: {data.get('current_price')}")
                print(f"   Desc Text Length: {len(data.get('description_text', ''))} chars")
                print(f"   Desc Images Found: {len(data.get('description_images', []))}")
                print(f"   Sellpoints Found: {len(data.get('sellpoints', []))}")

            # --- SEARCH AMAZON FOR COMPETITOR PRICES ---
            amazon_prices = {}
            enable_amazon_search = getattr(config, 'ENABLE_AMAZON_PRICE_SEARCH', True)
            max_amazon_results = getattr(config, 'AMAZON_PRICE_SEARCH_MAX_RESULTS', 10)
            
            if enable_amazon_search:
                try:
                    product_title = data.get('title', '')
                    if product_title:
                        if not self.silent_mode:
                            print(f"   🔍 Searching Amazon for: {product_title[:50]}...")
                        amazon_prices = search_amazon_prices_with_driver(self.driver, product_title, max_results=max_amazon_results)
                        if amazon_prices and not self.silent_mode:
                            print(f"   ✅ Found {len(amazon_prices)} Amazon results")
                            for title, price_info in list(amazon_prices.items())[:3]:
                                price = price_info.get("price", price_info) if isinstance(price_info, dict) else price_info
                                print(f"      - {price}: {title[:40]}...")
                except Exception as e:
                    if not self.silent_mode:
                        print(f"   [!] Amazon price search error: {e}")
            data["amazon_competitor_prices"] = amazon_prices

            # --- CALL API GATEWAY FOR SUGGESTED CONTENT ---
            try:
                input_text = f"{data.get('title','')}\n" + "\n".join(data.get('sellpoints', [])) + "\n" + data.get('description_text', '')
                
                # Build payload with pricing information
                payload = {
                    "input_text": input_text,
                    "aliexpress_price": data.get('current_price', ''),
                    "amazon_competitor_prices": amazon_prices
                }
                
                # --- DEBUG: Print pricing info being sent to API ---
                if self.detailed_mode or self.debug_mode:
                    print("\n" + "=" * 100)
                    print("📊 PRICING DATA FOR API GATEWAY:")
                    print("=" * 100)
                    print(f"📦 AliExpress Price: {data.get('current_price', 'N/A')}")
                    print(f"\n🛒 Amazon Competitor Prices ({len(amazon_prices)} results):")
                    print("-" * 100)
                    if amazon_prices:
                        for idx, (title, price_info) in enumerate(amazon_prices.items(), 1):
                            price = price_info.get("price", price_info) if isinstance(price_info, dict) else price_info
                            print(f"{idx:2}. [{price:>12}] {title}")
                    else:
                        print("   (No Amazon results found)")
                    print("-" * 100)
                    print("\n📤 Full payload JSON:")
                    print(json.dumps({
                        "aliexpress_price": data.get('current_price', ''),
                        "amazon_competitor_prices": amazon_prices
                    }, indent=2, ensure_ascii=False))
                    print("=" * 100 + "\n")
                
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
                        # API returns result_structured with title, bullet_point, description
                        suggested = raw.get("result_structured", raw)
                        if not self.silent_mode:
                            print("✅ Suggested content received.")
                data["suggested_title"] = suggested.get("title", "")
                data["suggested_seller_point"] = suggested.get("bullet_point", "")
                data["suggested_description"] = suggested.get("description", "")
                
                # Calculate price fields locally (API may return N/A)
                price_stats = calculate_amazon_price_stats(amazon_prices, data.get('current_price', ''))
                data["amazon_avg_price"] = price_stats["amazon_avg_price"]
                data["amazon_min_price"] = price_stats["amazon_min_price"]
                data["amazon_min_price_product"] = price_stats["amazon_min_price_product"]
                data["amazon_min_price_product_url"] = price_stats["amazon_min_price_product_url"]
                data["ali_express_rec_price"] = price_stats["ali_express_rec_price"]
                
                if not self.silent_mode:
                    print(f"   💰 Amazon Avg: {data['amazon_avg_price']}, Min: {data['amazon_min_price']}")
            except Exception as e:
                if not self.silent_mode:
                    print(f"⚠️ Suggested content API error: {e}")
                data["suggested_title"] = ""
                data["suggested_seller_point"] = ""
                data["suggested_description"] = ""
                # Still calculate price stats even if API fails
                price_stats = calculate_amazon_price_stats(amazon_prices, data.get('current_price', ''))
                data["amazon_avg_price"] = price_stats["amazon_avg_price"]
                data["amazon_min_price"] = price_stats["amazon_min_price"]
                data["amazon_min_price_product"] = price_stats["amazon_min_price_product"]
                data["amazon_min_price_product_url"] = price_stats["amazon_min_price_product_url"]
                data["ali_express_rec_price"] = price_stats["ali_express_rec_price"]

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
                    sku_remote = {
                        "name": sku.get("name", ""),
                        "image_url_remote": sku.get("image_url", ""),
                        "image_url": sku.get("image_url", ""),
                    }
                    # Preserve price fields
                    if "current_price" in sku:
                        sku_remote["current_price"] = sku.get("current_price", "")
                    if "history_price" in sku:
                        sku_remote["history_price"] = sku.get("history_price", "")
                    elif "original_price" in sku:  # Handle old field name
                        sku_remote["history_price"] = sku.get("original_price", "")
                    skus_remote_list.append(sku_remote)
                # We'll merge remote into skus later
                
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
                    # Preserve price fields if they exist
                    if "current_price" in sku:
                        merged["current_price"] = sku.get("current_price", "")
                    if "history_price" in sku:
                        merged["history_price"] = sku.get("history_price", "")
                    elif "original_price" in sku:  # Handle old field name for backward compatibility
                        merged["history_price"] = sku.get("original_price", "")
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
            else:
                print(f"Error: {e}")
    

    def scrape_search_results(self):

        # WAITS FOR MANUAL NAVIGATION (UNCHANGED)
        print("\n\n#####################################################")
        print("ACTION REQUIRED:")
        print("1. Navigate to the AliExpress Search Results page.")
        print("2. Solve any CAPTCHA/Login prompts.")
        if getattr(self, "resume_event", None):
            print("3. Click Resume in the UI when the results page is ready to be scraped...")
            self.resume_event.wait()
        else:
            input("3. Press ENTER in this console when the results page is ready to be scraped...")
        print("#####################################################\n")

        if not self.silent_mode:
            print("🔍 Starting scraping of current page...")

        # Scroll to ensure elements load
        self.driver.execute_script("window.scrollBy(0, 800);")
        random_wait(getattr(config, 'WAIT_PAGE_LOAD', (1.0, 2.0)))
        
        # Check for CAPTCHA after scroll
        self._check_and_handle_captcha()

        links_found = []
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, config.SEARCH_ITEM_SELECTOR)

            for el in elements:
                raw_href = el.get_attribute("href")
                if raw_href and "/item/" in raw_href:
                    links_found.append(clean_url(raw_href))
        except Exception as e:
            if not self.silent_mode:
                print(f"❌ Error finding elements: {e}")

        unique_links = list(set(links_found))

        if self.detailed_mode or self.debug_mode:
            print(f"✅ Found {len(unique_links)} unique item links on the page.")
        targets = unique_links[:config.MAX_PRODUCTS_TO_SCRAPE]
        if self.detailed_mode or self.debug_mode:
            print(f"🎯 Targeting the following {len(targets)} links:")
            for link in targets:
                print(f"   -> {link}")

        for idx, link in enumerate(targets):
            if not self.silent_mode:
                print(f"\n📦 Processing product {idx + 1}/{len(targets)}...")
            
            self.scrape_product_details(link)

            # IMPROVEMENT: Add randomized delay between pages
            wait_range = getattr(config, 'WAIT_BETWEEN_PRODUCTS', (1.5, 3.0))
            delay = random.uniform(wait_range[0], wait_range[1])
            if self.detailed_mode or self.debug_mode:
                print(f"   (Paused for {delay:.2f}s)")
            time.sleep(delay)

if __name__ == "__main__":
    import sys
    # Allow override via command line, otherwise use config.MODE
    mode = None
    if "--debug" in sys.argv or "-d" in sys.argv:
        mode = "debug"
    elif "--silent" in sys.argv or "-s" in sys.argv:
        mode = "silent"
    elif "--detailed" in sys.argv:
        mode = "detailed"
    
    bot = AliExpressScraper(mode=mode)
    # Test Link
    # test_url = "https://www.aliexpress.com/item/1005009065657707.html"
    # bot.scrape_product_details(test_url)
    bot.scrape_search_results()