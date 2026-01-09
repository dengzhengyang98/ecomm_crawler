"""QThread for running scraper without freezing UI."""
import sys
from PySide6.QtCore import QThread, Signal
from scrapers.aliexpress import AliExpressScraper
from scrapers.amazon import AmazonScraper


class LoggingStdout:
    """Custom stdout that emits signals for log messages."""
    
    def __init__(self, log_signal, item_scraped_signal=None):
        self.log_signal = log_signal
        self.item_scraped_signal = item_scraped_signal
        self.buffer = []
    
    def write(self, text):
        """Write text and emit signal."""
        if text:
            # Accumulate text until newline
            self.buffer.append(text)
            if '\n' in text:
                full_text = ''.join(self.buffer).strip()
                if full_text:
                    self.log_signal.emit(full_text)
                    # Detect when a product is saved and emit item_scraped signal
                    if self.item_scraped_signal and ('Saved locally' in full_text or '💾' in full_text):
                        self.item_scraped_signal.emit()
                self.buffer = []
        return len(text)
    
    def flush(self):
        """Flush buffer."""
        if self.buffer:
            full_text = ''.join(self.buffer).strip()
            if full_text:
                self.log_signal.emit(full_text)
                if self.item_scraped_signal and ('Saved locally' in full_text or '💾' in full_text):
                    self.item_scraped_signal.emit()
            self.buffer = []


class ScraperThread(QThread):
    """Thread for running scraper operations."""
    
    log_message = Signal(str)  # Emits log messages
    finished_successfully = Signal()  # Emits when scraping completes
    error_occurred = Signal(str)  # Emits error messages
    item_scraped = Signal()  # Emits when a single item is scraped (to refresh list)
    
    def __init__(self, mode=None, resume_event=None, source="aliexpress", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.scraper = None
        self.target_url = None
        self.scrape_type = "search"  # "search" or "single"
        self.original_stdout = None
        self.resume_event = resume_event
        self.source = source  # "aliexpress" or "amazon"
    
    def set_target_url(self, url: str):
        """Set the target URL for single product scraping."""
        self.target_url = url
        self.scrape_type = "single" if url else "search"
    
    def set_source(self, source: str):
        """Set the scraper source (aliexpress or amazon)."""
        self.source = source.lower()
    
    def run(self):
        """Run the scraper in this thread."""
        scraping_completed = False
        try:
            source_name = "Amazon" if self.source == "amazon" else "AliExpress"
            self.log_message.emit(f"🚀 Initializing {source_name} scraper...")
            
            # Redirect stdout to capture print statements
            self.original_stdout = sys.stdout
            sys.stdout = LoggingStdout(self.log_message, self.item_scraped)
            
            try:
                # Create appropriate scraper based on source
                if self.source == "amazon":
                    self.scraper = AmazonScraper(mode=self.mode, resume_event=self.resume_event)
                else:
                    self.scraper = AliExpressScraper(mode=self.mode, resume_event=self.resume_event)
                
                if self.scrape_type == "single" and self.target_url:
                    self.log_message.emit(f"📦 Scraping single product: {self.target_url}")
                    self.scraper.scrape_product_details(self.target_url)
                else:
                    self.log_message.emit(f"🔍 Starting {source_name} search results scraping...")
                    self.scraper.scrape_search_results()
                
                scraping_completed = True
                self.log_message.emit("✅ Scraping completed successfully!")
                
            finally:
                # Restore stdout
                if self.original_stdout:
                    sys.stdout = self.original_stdout
                # Close browser
                if self.scraper and hasattr(self.scraper, 'driver'):
                    try:
                        self.scraper.driver.quit()
                        self.log_message.emit("🔒 Browser closed.")
                    except Exception:
                        pass
            
            # Emit finished signal AFTER cleanup to ensure UI gets updated
            if scraping_completed:
                self.finished_successfully.emit()
        
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            try:
                self.log_message.emit(error_msg)
                self.error_occurred.emit(str(e))
            except Exception:
                print(f"Failed to emit error signal: {e}")
            # Restore stdout on error
            if self.original_stdout:
                sys.stdout = self.original_stdout
            # Ensure browser is closed on error
            if self.scraper and hasattr(self.scraper, 'driver'):
                try:
                    self.scraper.driver.quit()
                except Exception:
                    pass
    
    def stop(self):
        """Stop the scraper (close browser)."""
        if self.scraper and hasattr(self.scraper, 'driver'):
            try:
                self.scraper.driver.quit()
                self.log_message.emit("🛑 Scraper stopped.")
            except Exception:
                pass

