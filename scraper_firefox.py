import time
import hashlib
import os
import requests
import boto3
import random
import uuid  # Added for unique IDs
import re
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

# --- CONSTANTS ---
PROFILE_DIR = os.path.join(os.getcwd(), 'firefox_real_profile')
if not os.path.exists(PROFILE_DIR):
    os.makedirs(PROFILE_DIR)


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
    # For gallery images, remove suffixes like _main, _profile if they exist
    # Check if URL ends with _main.jpg, _profile.jpg, etc. and remove the suffix
    base_url = re.sub(r'_main\.(jpg|jpeg|png|webp)$', r'.\1', base_url, flags=re.IGNORECASE)
    base_url = re.sub(r'_profile\.(jpg|jpeg|png|webp)$', r'.\1', base_url, flags=re.IGNORECASE)
    # Handle protocol-relative URLs
    if base_url.startswith("//"):
        base_url = "https:" + base_url
    return base_url


def download_image(url, folder_path, filename):
    if not url: return None
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
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
class AliExpressScraper:
    def __init__(self, debug_mode=False):
        self.debug_mode = debug_mode
        try:
            self.dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
            self.table = self.dynamodb.Table(config.DYNAMODB_TABLE)
        except Exception as e:
            print(f"⚠️ Warning: DynamoDB connection failed ({e}). Running in local-only mode.")
            self.table = None

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
        service = Service(GeckoDriverManager().install())
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

    def scrape_product_details(self, url):
        # 1. Generate Unique ID (UUID) instead of Hash
        p_id = generate_id()

        print(f"\n--- SCRAPING: {p_id} ---")
        print(f"    URL: {url}")
        self.driver.get(url)

        # CAPTCHA Check
        if len(self.driver.find_elements(By.ID, "baxia-dialog-content")) > 0:
            print("⚠️ CAPTCHA detected. Pausing for manual fix...")
            input("Press ENTER after solving...")

        # 2. SCROLL & EXPAND DESCRIPTION
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
        time.sleep(1)

        # Try to find and click "View More" button
        try:
            # First check if button exists without waiting
            view_more_btn = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_DESC_VIEW_MORE_BTN)
            if view_more_btn:
                print("   [+] Found 'View More' button, scrolling to it...")
                # Scroll the button into view
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", view_more_btn[0])
                time.sleep(1)
                
                # Wait for button to be clickable
                clickable_btn = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, config.PRODUCT_DESC_VIEW_MORE_BTN))
                )
                print("   [+] Clicking 'View More' button...")
                self.driver.execute_script("arguments[0].click();", clickable_btn)
                time.sleep(3)  # Wait longer for content to load
                
                # Wait for SEO description to appear
                try:
                    self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, config.PRODUCT_SEO_DESCRIPTION))
                    )
                    print("   [+] SEO description loaded after clicking 'View More'")
                except:
                    print("   [-] SEO description not found after clicking (may already be visible)")
            else:
                print("   [-] No 'View More' button found (content might be short or already expanded).")
        except Exception as e:
            print(f"   [!] Error with 'View More' button: {e}")

        # Scroll further down to ensure images lazy load
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 1.5);")
        time.sleep(2)
        
        # Scroll to description container to trigger lazy loading of images
        try:
            desc_container = self.driver.find_elements(By.CSS_SELECTOR, config.PRODUCT_DESCRIPTION_CONTAINER)
            if desc_container:
                # Scroll to description area
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'start'});", desc_container[0])
                time.sleep(2)  # Wait for images to load
        except:
            pass
        
        # DEBUG: Interactive selector testing
        if self.debug_mode:
            response = input("\n🔍 Enter interactive selector testing mode? (y/n): ").strip().lower()
            if response == 'y':
                self.debug_interactive_selector()

        data = {
            'product_id': p_id,
            'url': url,
            'status': 'scraped',
            'timestamp': str(int(time.time()))
        }

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

                if gallery_urls:
                    data['main_image_path'] = download_image(gallery_urls[0], config.IMAGE_STORE_DIR,
                                                             f"{p_id}_main.jpg")
                data['gallery_images'] = gallery_urls
            except Exception as e:
                data['gallery_images'] = []

            # --- D. SKUS ---
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
                                            print(f"   [+] Extracted {len(shadow_text)} chars of text from Shadow DOM")
                                    except Exception as e:
                                        if self.debug_mode:
                                            print(f"   [!] Error extracting text from Shadow DOM: {e}")
                                    
                                    # Extract images from Shadow DOM richtext
                                    try:
                                        shadow_imgs = shadow_richtext.find_elements(By.CSS_SELECTOR, "img")
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
                                            print(f"   [+] Fallback: Found {len(shadow_imgs)} images in Shadow DOM")
                                            for idx, img in enumerate(shadow_imgs):
                                                try:
                                                    src = img.get_attribute("src")
                                                    if src and src.strip() and src != "image" and "alicdn.com" in src:
                                                        clean_src = clean_image_url(src)
                                                        if clean_src and clean_src not in desc_img_urls:
                                                            desc_img_urls.append(clean_src)
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
                        time.sleep(2)
                        
                        # Extract Images from Rich Text (Regular DOM)
                        imgs = search_container.find_elements(By.TAG_NAME, "img")
                        print(f"   [+] Found {len(imgs)} image elements in description (Regular DOM)")
                        
                        for idx, img in enumerate(imgs):
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", img)
                                time.sleep(0.3)
                                
                                src = img.get_attribute("src")
                                if not src or src.strip() == "":
                                    src = img.get_attribute("data-src")
                                if not src or src.strip() == "":
                                    src = img.get_attribute("data-lazy-src")
                                
                                if src and src.strip() and src != "image" and "alicdn.com" in src:
                                    clean_src = clean_image_url(src)
                                    if clean_src and clean_src not in desc_img_urls:
                                        desc_img_urls.append(clean_src)
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
                    print(f"   [+] Extracted {len(sellpoints)} sellpoint(s)")
                else:
                    data['sellpoints'] = []
            except Exception as e:
                if self.debug_mode:
                    print(f"   [!] Error extracting sellpoints: {e}")
                    import traceback
                    traceback.print_exc()
                data['sellpoints'] = []

            # --- LOGGING ---
            print(f"   Title: {data.get('title')[:30]}...")
            print(f"   Price: {data.get('current_price')}")
            print(f"   Desc Text Length: {len(data.get('description_text', ''))} chars")
            print(f"   Desc Images Found: {len(data.get('description_images', []))}")
            print(f"   Sellpoints Found: {len(data.get('sellpoints', []))}")

            # --- SAVE ---
            if self.table:
                self.table.put_item(Item=data)
                print("💾 Saved to DynamoDB.")
            else:
                print("💾 (Mock) Saved to DB.")

        except Exception as e:
            print(f"❌ Error scraping details: {e}")
    

    def scrape_search_results(self):

        # WAITS FOR MANUAL NAVIGATION (UNCHANGED)
        print("\n\n#####################################################")
        print("ACTION REQUIRED:")
        print("1. Navigate to the AliExpress Search Results page.")
        print("2. Solve any CAPTCHA/Login prompts.")
        input("3. Press ENTER in this console when the results page is ready to be scraped...")
        print("#####################################################\n")

        print("🔍 Starting scraping of current page...")

        # Scroll to ensure elements load
        self.driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(2)

        links_found = []
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, config.SEARCH_ITEM_SELECTOR)

            for el in elements:
                raw_href = el.get_attribute("href")
                if raw_href and "/item/" in raw_href:
                    links_found.append(clean_url(raw_href))
        except Exception as e:
            print(f"❌ DEBUG: Error finding elements: {e}")

        unique_links = list(set(links_found))

        print(f"✅ DEBUG: Found {len(unique_links)} unique item links on the page.")
        targets = unique_links[:config.MAX_PRODUCTS_TO_SCRAPE]
        print(f"🎯 DEBUG: Targeting the following {len(targets)} links:")
        for link in targets:
            print(f"   -> {link}")

        for link in targets:
            self.scrape_product_details(link)

            # IMPROVEMENT: Add randomized delay between pages
            delay = random.uniform(2, 5)
            print(f"   (Pausing for {delay:.2f} seconds to mimic human behavior...)")
            time.sleep(delay)

if __name__ == "__main__":
    import sys
    # Enable debug mode if --debug flag is passed
    debug_mode = "--debug" in sys.argv or "-d" in sys.argv
    bot = AliExpressScraper(debug_mode=debug_mode)
    # Test Link
    # test_url = "https://www.aliexpress.com/item/1005009065657707.html"
    # bot.scrape_product_details(test_url)
    bot.scrape_search_results()