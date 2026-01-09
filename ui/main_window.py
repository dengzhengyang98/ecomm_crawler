"""Main window for E-Commerce Product Manager (AliExpress & Amazon)."""
import csv
import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QRadioButton, QButtonGroup, QScrollArea,
    QFormLayout, QGroupBox, QMessageBox, QSplitter, QFrame, QSizePolicy,
    QFileDialog, QComboBox
)
from PySide6.QtCore import Qt, Signal, QTimer, QUrl
from PySide6.QtGui import QFont, QDesktopServices

try:
    import boto3
    from boto3.dynamodb.types import TypeDeserializer
    from botocore.exceptions import BotoCoreError, NoCredentialsError
except Exception:
    boto3 = None
    TypeDeserializer = None
    BotoCoreError = Exception
    NoCredentialsError = Exception

try:
    from config import settings as config
except Exception:
    class DummyConfig:
        AWS_REGION = "us-west-2"
        DYNAMODB_TABLE = "AliExpressProducts"
    config = DummyConfig()

from ui.components.image_gallery import ImageGallery
from ui.components.scraper_thread import ScraperThread
from ui.components.sku_gallery import SKUGallery
from ui.components.collapsible_section import CollapsibleSection

# Local cache paths
CACHE_DIR = os.path.join(os.getcwd(), "cache")
PRODUCTS_DIR = os.path.join(CACHE_DIR, "products")
IMAGES_DIR = os.path.join(CACHE_DIR, "images")


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("电商产品管理器")
        self.setMinimumSize(1200, 800)
        
        # Data storage
        self.items: List[Dict[str, Any]] = []
        self.filtered_items: List[Dict[str, Any]] = []
        self.selected_index = 0
        self.table = None
        
        # Scraper thread
        self.scraper_thread: Optional[ScraperThread] = None
        self.scraper_resume_event: Optional[threading.Event] = None
        
        # Initialize UI
        self._init_ui()
        
        # Do NOT auto-load cache; user will load from cache or scrape
        # QTimer.singleShot(0, self._load_data)
    
    def _init_ui(self):
        """Initialize the UI."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title row with export button
        title_row = QHBoxLayout()
        title_label = QLabel("电商产品管理器")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_row.addWidget(title_label)
        title_row.addStretch()
        
        # Export button
        self.export_btn = QPushButton("导出 CSV")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.export_btn.clicked.connect(self._on_export_csv)
        title_row.addWidget(self.export_btn)
        
        main_layout.addLayout(title_row)
        
        # Warning label (for DynamoDB status)
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: #ff8800; padding: 5px;")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        main_layout.addWidget(self.warning_label)
        
        # Scraper section
        scraper_group = QGroupBox("爬虫设置")
        scraper_layout = QHBoxLayout()
        
        # Source selection (AliExpress or Amazon)
        scraper_layout.addWidget(QLabel("来源:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["AliExpress", "Amazon"])
        self.source_combo.setCurrentIndex(0)
        self.source_combo.setMinimumWidth(120)
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        scraper_layout.addWidget(self.source_combo)
        
        scraper_layout.addSpacing(20)
        
        self.scraper_url_input = QLineEdit()
        self.scraper_url_input.setPlaceholderText("输入产品URL（可选，留空则爬取搜索结果页）")
        scraper_layout.addWidget(QLabel("目标URL:"))
        scraper_layout.addWidget(self.scraper_url_input, stretch=1)
        
        # Resume button
        self.resume_btn = QPushButton("继续")
        self.resume_btn.setEnabled(False)
        self.resume_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffa500;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.resume_btn.clicked.connect(self._on_resume_scraper)
        scraper_layout.addWidget(self.resume_btn)
        
        # Stop button
        self.stop_scraper_btn = QPushButton("停止")
        self.stop_scraper_btn.setEnabled(False)
        self.stop_scraper_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.stop_scraper_btn.clicked.connect(self._on_stop_scraper)
        scraper_layout.addWidget(self.stop_scraper_btn)
        
        self.run_scraper_btn = QPushButton("开始爬取")
        self.run_scraper_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.run_scraper_btn.clicked.connect(self._on_run_scraper)
        scraper_layout.addWidget(self.run_scraper_btn)
        
        scraper_group.setLayout(scraper_layout)
        main_layout.addWidget(scraper_group)
        
        # Logs area (no title, half height)
        logs_group = QGroupBox()
        logs_group.setTitle("")
        logs_layout = QVBoxLayout()
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setMaximumHeight(75)  # Half the original height
        self.logs_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: monospace;")
        logs_layout.addWidget(self.logs_text)
        logs_group.setLayout(logs_layout)
        main_layout.addWidget(logs_group)
        
        # Filter and cache controls
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("按URL筛选:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("按URL筛选（如：aliexpress.com 或 amazon.com）")
        self.filter_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_input, stretch=1)
        
        self.load_cache_btn = QPushButton("加载缓存")
        self.load_cache_btn.clicked.connect(self._on_load_cache)
        filter_layout.addWidget(self.load_cache_btn)
        
        self.clean_cache_btn = QPushButton("清空缓存")
        self.clean_cache_btn.clicked.connect(self._on_clean_cache)
        filter_layout.addWidget(self.clean_cache_btn)
        
        main_layout.addLayout(filter_layout)
        
        # Main content area (splitter)
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - Product list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_title = QLabel("产品列表")
        left_title_font = QFont()
        left_title_font.setPointSize(12)
        left_title_font.setBold(True)
        left_title.setFont(left_title_font)
        left_layout.addWidget(left_title)
        
        # Radio button group for product selection
        self.product_button_group = QButtonGroup()
        self.product_radio_widget = QWidget()
        self.product_radio_layout = QVBoxLayout(self.product_radio_widget)
        self.product_radio_layout.setAlignment(Qt.AlignTop)
        
        scroll_area_left = QScrollArea()
        scroll_area_left.setWidget(self.product_radio_widget)
        scroll_area_left.setWidgetResizable(True)
        scroll_area_left.setMinimumWidth(300)
        left_layout.addWidget(scroll_area_left)
        
        splitter.addWidget(left_panel)
        
        # Right panel - Product details
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        right_title = QLabel("详情")
        right_title_font = QFont()
        right_title_font.setPointSize(12)
        right_title_font.setBold(True)
        right_title.setFont(right_title_font)
        right_layout.addWidget(right_title)
        
        # Scroll area for details
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setAlignment(Qt.AlignTop)
        
        # Form for editing product
        form_group = QGroupBox("编辑产品")
        form_layout = QFormLayout()
        
        self.title_input = QLineEdit()
        # Make title input very long to span the frame
        self.title_input.setMinimumWidth(900)
        self.title_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form_layout.addRow("产品标题:", self.title_input)
        
        # Suggested title right under product title (editable)
        self.suggested_title_value = QLineEdit()
        self.suggested_title_value.setMinimumWidth(900)
        self.suggested_title_value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.suggested_title_value.setStyleSheet("background-color: #f5f5dc;")
        self.suggested_title_value.setPlaceholderText("AI建议标题（可编辑）")
        form_layout.addRow("建议标题:", self.suggested_title_value)
        
        # Price row 1: AliExpress prices
        price_layout1 = QHBoxLayout()
        self.current_price_input = QLineEdit()
        self.original_price_input = QLineEdit()
        self.current_price_input.setMaximumWidth(100)
        self.original_price_input.setMaximumWidth(100)
        price_layout1.addWidget(QLabel("速卖通现价:"))
        price_layout1.addWidget(self.current_price_input)
        price_layout1.addWidget(QLabel("速卖通原价:"))
        price_layout1.addWidget(self.original_price_input)
        price_layout1.addStretch()
        form_layout.addRow(price_layout1)
        
        # Price row 2: Amazon prices from API
        price_layout2 = QHBoxLayout()
        self.amazon_avg_price_label = QLabel("")
        self.amazon_avg_price_label.setStyleSheet("color: #0066cc; font-weight: bold;")
        self.amazon_min_price_label = QLabel("")
        self.amazon_min_price_label.setStyleSheet("color: #228B22; font-weight: bold;")
        price_layout2.addWidget(QLabel("亚马逊平均价格:"))
        price_layout2.addWidget(self.amazon_avg_price_label)
        price_layout2.addSpacing(20)
        price_layout2.addWidget(QLabel("亚马逊最低价格:"))
        price_layout2.addWidget(self.amazon_min_price_label)
        price_layout2.addStretch()
        form_layout.addRow(price_layout2)
        
        # Price row 3: Amazon min price product (clickable)
        self.amazon_min_price_product_label = QLabel("")
        self.amazon_min_price_product_label.setWordWrap(True)
        self.amazon_min_price_product_label.setStyleSheet("""
            QLabel {
                color: #0066cc;
                font-style: italic;
                text-decoration: underline;
            }
            QLabel:hover {
                color: #004499;
            }
        """)
        self.amazon_min_price_product_label.setCursor(Qt.PointingHandCursor)
        self.amazon_min_price_product_label.setOpenExternalLinks(False)
        self.amazon_min_price_product_label.mousePressEvent = lambda e: self._open_amazon_min_price_product_url()
        self._amazon_min_price_product_url = ""  # Store URL for click handler
        form_layout.addRow("亚马逊最低价产品:", self.amazon_min_price_product_label)
        
        # Price row 4: Recommended and Final price
        price_layout3 = QHBoxLayout()
        self.ali_rec_price_label = QLabel("")
        self.ali_rec_price_label.setStyleSheet("color: #FF8C00; font-weight: bold;")
        self.final_price_input = QLineEdit()
        self.final_price_input.setMaximumWidth(100)
        self.final_price_input.setStyleSheet("background-color: #FFFACD; font-weight: bold;")
        price_layout3.addWidget(QLabel("速卖通建议价格:"))
        price_layout3.addWidget(self.ali_rec_price_label)
        price_layout3.addSpacing(20)
        price_layout3.addWidget(QLabel("最终价格:"))
        price_layout3.addWidget(self.final_price_input)
        price_layout3.addStretch()
        form_layout.addRow(price_layout3)
        
        self.url_input = QLineEdit()
        self.url_input.setReadOnly(True)
        self.url_input.setMinimumWidth(900)
        self.url_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.url_input.setStyleSheet("""
            QLineEdit {
                background-color: #f0f0f0;
                color: #0066cc;
                text-decoration: underline;
            }
        """)
        self.url_input.setCursor(Qt.PointingHandCursor)
        # Make URL clickable to open browser
        self.url_input.mousePressEvent = lambda e: self._open_url_in_browser()
        form_layout.addRow("链接:", self.url_input)

        # SKU section - display as gallery with images and names
        sku_label = QLabel("规格/SKU:")
        form_layout.addRow(sku_label)
        
        form_group.setLayout(form_layout)
        details_layout.addWidget(form_group)
        
        # SKU Gallery (outside form group)
        self.sku_gallery = SKUGallery("")
        self.sku_gallery.skus_changed.connect(self._on_skus_changed)
        details_layout.addWidget(self.sku_gallery)
        
        # Seller point section (collapsible, collapsed by default)
        self.sellpoint_section = CollapsibleSection("卖点（原始）", collapsed=True)
        self.sellpoint_text = QTextEdit()
        self.sellpoint_text.setPlaceholderText("每行一个卖点")
        self.sellpoint_text.setMinimumWidth(880)
        self.sellpoint_text.setMinimumHeight(150)
        self.sellpoint_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.sellpoint_section.add_widget(self.sellpoint_text)
        details_layout.addWidget(self.sellpoint_section)

        # Suggested seller point (always visible)
        suggested_sp_group = QGroupBox("建议卖点")
        suggested_sp_layout = QVBoxLayout()
        self.suggested_seller_point = QTextEdit()
        self.suggested_seller_point.setReadOnly(True)
        self.suggested_seller_point.setMinimumWidth(880)
        self.suggested_seller_point.setMinimumHeight(150)
        self.suggested_seller_point.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        suggested_sp_layout.addWidget(self.suggested_seller_point)
        suggested_sp_group.setLayout(suggested_sp_layout)
        details_layout.addWidget(suggested_sp_group)
        
        # Description text section (collapsible, collapsed by default)
        self.desc_section = CollapsibleSection("描述文本（原始）", collapsed=True)
        self.desc_text = QTextEdit()
        self.desc_text.setPlaceholderText("产品描述")
        self.desc_text.setMinimumWidth(880)
        self.desc_text.setMinimumHeight(180)
        self.desc_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.desc_section.add_widget(self.desc_text)
        details_layout.addWidget(self.desc_section)

        # Suggested description (always visible)
        suggested_desc_group = QGroupBox("建议描述")
        suggested_desc_layout = QVBoxLayout()
        self.suggested_desc_text = QTextEdit()
        self.suggested_desc_text.setReadOnly(True)
        self.suggested_desc_text.setMinimumWidth(880)
        self.suggested_desc_text.setMinimumHeight(180)
        self.suggested_desc_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        suggested_desc_layout.addWidget(self.suggested_desc_text)
        suggested_desc_group.setLayout(suggested_desc_layout)
        details_layout.addWidget(suggested_desc_group)
        
        # Gallery images (Recommended - Processed) - always visible
        self.gallery_recommended = ImageGallery("产品图片（推荐 - 已处理）")
        self.gallery_recommended.urls_changed.connect(self._on_gallery_recommended_changed)
        details_layout.addWidget(self.gallery_recommended)
        
        # Gallery images (Original) - COMMENTED OUT (hidden)
        # self.gallery_section = CollapsibleSection("产品图片（原始）", collapsed=True)
        # self.gallery_gallery = ImageGallery("")
        # self.gallery_gallery.urls_changed.connect(self._on_gallery_urls_changed)
        # self.gallery_section.add_widget(self.gallery_gallery)
        # details_layout.addWidget(self.gallery_section)
        self.gallery_gallery = None  # Placeholder to prevent attribute errors
        
        # Description images (Recommended - Processed) - always visible
        self.desc_recommended = ImageGallery("描述图片（推荐 - 已处理）")
        self.desc_recommended.urls_changed.connect(self._on_desc_recommended_changed)
        details_layout.addWidget(self.desc_recommended)
        
        # Description images (Original) - COMMENTED OUT (hidden)
        # self.desc_images_section = CollapsibleSection("描述图片（原始）", collapsed=True)
        # self.desc_gallery = ImageGallery("")
        # self.desc_gallery.urls_changed.connect(self._on_desc_urls_changed)
        # self.desc_images_section.add_widget(self.desc_gallery)
        # details_layout.addWidget(self.desc_images_section)
        self.desc_gallery = None  # Placeholder to prevent attribute errors
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("保存")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.save_btn.clicked.connect(self._on_save_clicked)
        button_layout.addWidget(self.save_btn)
        
        self.delete_btn = QPushButton("删除")
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        button_layout.addWidget(self.delete_btn)
        
        details_layout.addLayout(button_layout)
        
        # Status label
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #888; font-style: italic; padding: 5px;")
        details_layout.addWidget(self.status_label)
        
        details_scroll.setWidget(details_widget)
        right_layout.addWidget(details_scroll, stretch=1)  # Add scroll area to right panel layout
        
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        
        main_layout.addWidget(splitter, stretch=1)
    
    def _get_table(self):
        """Get DynamoDB table or return None (used only on save/delete)."""
        if not boto3:
            return None, "boto3 is not installed."
        try:
            # Try to use Cognito Identity Pool credentials if authenticated
            from auth.service import get_dynamodb_resource
            dynamodb = get_dynamodb_resource()
            if not dynamodb:
                return None, "DynamoDB resource unavailable. Please ensure you are authenticated."
            table = dynamodb.Table(config.DYNAMODB_TABLE)
            table.load()
            return table, None
        except (BotoCoreError, NoCredentialsError) as exc:
            return None, f"DynamoDB unavailable ({exc})."
        except Exception as exc:
            return None, f"DynamoDB init error ({exc})."
    
    # Cache helpers
    def _ensure_cache(self):
        os.makedirs(PRODUCTS_DIR, exist_ok=True)
        os.makedirs(IMAGES_DIR, exist_ok=True)
    
    def _load_cache_items(self) -> List[Dict[str, Any]]:
        """Load all cached products from disk."""
        self._ensure_cache()
        items: List[Dict[str, Any]] = []
        for fname in os.listdir(PRODUCTS_DIR):
            if fname.endswith(".json"):
                fpath = os.path.join(PRODUCTS_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        items.append(data)
                except Exception:
                    continue
        return items
    
    def _save_cache_item(self, item: Dict[str, Any]):
        """Save a single product to cache."""
        self._ensure_cache()
        pid = item.get("product_id") or item.get("id") or "unknown"
        fpath = os.path.join(PRODUCTS_DIR, f"{pid}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
    
    def _delete_cache_item(self, product_id: str):
        self._ensure_cache()
        fpath = os.path.join(PRODUCTS_DIR, f"{product_id}.json")
        if os.path.exists(fpath):
            os.remove(fpath)
    
    def _deserialize_dynamodb_value(self, value: Dict[str, Any]) -> Any:
        """Simple DynamoDB deserializer for common types."""
        if "S" in value:
            return value["S"]
        elif "N" in value:
            try:
                num_str = value["N"]
                if "." in num_str:
                    return float(num_str)
                return int(num_str)
            except ValueError:
                return value["N"]
        elif "L" in value:
            return [self._deserialize_dynamodb_value(item) for item in value["L"]]
        elif "M" in value:
            return {k: self._deserialize_dynamodb_value(v) for k, v in value["M"].items()}
        elif "BOOL" in value:
            return value["BOOL"]
        elif "NULL" in value:
            return None
        else:
            # Unknown type, return as-is
            return value
    
    def _load_sample_from_schema(self) -> List[Dict[str, Any]]:
        """Load sample data from schema.txt."""
        # Try multiple paths
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "..", "schema.txt"),
            os.path.join(os.getcwd(), "schema.txt"),
            "schema.txt"
        ]
        
        sample_path = None
        for path in possible_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                sample_path = abs_path
                break
        
        if not sample_path:
            print("Warning: schema.txt not found in any of the expected locations")
            return []
        
        try:
            with open(sample_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            
            # Try to deserialize if TypeDeserializer is available (preferred method)
            if TypeDeserializer:
                try:
                    deser = TypeDeserializer()
                    parsed = {k: deser.deserialize(v) for k, v in raw.items()}
                    return [parsed]
                except Exception as e:
                    print(f"Warning: Failed to deserialize with TypeDeserializer: {e}, trying fallback")
            
            # Fallback: manual deserialization for DynamoDB format
            if isinstance(raw, dict):
                # Check if it's DynamoDB format (has type keys like "S", "N", "L", etc.)
                if any(key in raw for key in ["S", "N", "L", "M", "BOOL", "NULL"]):
                    # It's a single DynamoDB item
                    parsed = {k: self._deserialize_dynamodb_value(v) for k, v in raw.items()}
                    return [parsed]
                else:
                    # Already in normal format
                    return [raw]
            elif isinstance(raw, list):
                # List of items - deserialize each if needed
                result = []
                for item in raw:
                    if isinstance(item, dict) and any(key in item for key in ["S", "N", "L", "M", "BOOL", "NULL"]):
                        parsed = {k: self._deserialize_dynamodb_value(v) for k, v in item.items()}
                        result.append(parsed)
                    else:
                        result.append(item)
                return result
            else:
                print(f"Warning: Unexpected schema.txt format: {type(raw)}")
                return []
        except Exception as e:
            print(f"Error loading schema.txt: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _normalize_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize item structure."""
        # Keep remote/original URLs if present for later DDB save
        gallery_remote = item.get("gallery_images_remote", item.get("gallery_images", []))
        desc_remote = item.get("description_images_remote", item.get("description_images", []))
        skus_remote = item.get("skus", [])
        suggested_title = item.get("suggested_title", "")
        suggested_seller_point = item.get("suggested_seller_point", "")
        suggested_description = item.get("suggested_description", "")
        
        def to_abs(url: str) -> str:
            if not url:
                return url
            if os.path.exists(url):
                return os.path.abspath(url)
            abs_path = os.path.abspath(url)
            if os.path.exists(abs_path):
                return abs_path
            # fallback: check images cache by basename, walk dirs
            basename = os.path.basename(url)
            candidate = os.path.join(IMAGES_DIR, basename)
            if os.path.exists(candidate):
                return os.path.abspath(candidate)
            for root, _, files in os.walk(IMAGES_DIR):
                if basename in files:
                    return os.path.abspath(os.path.join(root, basename))
            return url
        
        gallery_local = [to_abs(u) for u in item.get("gallery_images", []) or []]
        desc_local = [to_abs(u) for u in item.get("description_images", []) or []]
        skus_local = []
        for sku in item.get("skus", []) or []:
            sku_dict = {
                "name": sku.get("name", ""),
                "image_url": to_abs(sku.get("image_url", "")),
                "image_url_remote": sku.get("image_url_remote", sku.get("image_url", "")),
            }
            # Preserve price fields if they exist (for SKU-specific prices)
            if "current_price" in sku:
                sku_dict["current_price"] = sku.get("current_price", "")
            # Support both history_price (new) and original_price (old) for backward compatibility
            if "history_price" in sku:
                sku_dict["history_price"] = sku.get("history_price", "")
            elif "original_price" in sku:
                sku_dict["history_price"] = sku.get("original_price", "")  # Convert old field name
            skus_local.append(sku_dict)
        return {
            "product_id": item.get("product_id", ""),
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "current_price": item.get("current_price", ""),
            "original_price": item.get("original_price", ""),
            "final_price": item.get("final_price", ""),
            "gallery_images": gallery_local,
            "gallery_images_remote": gallery_remote or [],
            "gallery_images_recommended": item.get("gallery_images_recommended", []) or [],
            "skus": skus_local,
            "sellpoints": item.get("sellpoints", []) or [],
            "description_text": item.get("description_text", ""),
            "description_images": desc_local,
            "description_images_remote": desc_remote or [],
            "description_images_recommended": item.get("description_images_recommended", []) or [],
            "main_image_path": item.get("main_image_path", ""),
            "status": item.get("status", ""),
            "timestamp": item.get("timestamp", ""),
            "suggested_title": suggested_title,
            "suggested_seller_point": suggested_seller_point,
            "suggested_description": suggested_description,
            "source": item.get("source", "aliexpress"),
            # New price fields from API
            "amazon_avg_price": item.get("amazon_avg_price", ""),
            "amazon_min_price": item.get("amazon_min_price", ""),
            "amazon_min_price_product": item.get("amazon_min_price_product", ""),
            "amazon_min_price_product_url": item.get("amazon_min_price_product_url", ""),
            "ali_express_rec_price": item.get("ali_express_rec_price", ""),
            # DynamoDB upload status (stored locally)
            "uploaded_to_ddb": item.get("uploaded_to_ddb", False),
        }
    
    def _format_timestamp(self, ts: str) -> str:
        """Format timestamp."""
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ts or ""
    
    def _parse_lines(self, text: str) -> List[str]:
        """Parse lines from text."""
        return [line.strip() for line in text.splitlines() if line.strip()]
    
    def _parse_price(self, price_str: str) -> float:
        """Parse price string to float. Returns 0 if invalid."""
        if not price_str:
            return 0.0
        try:
            # Remove currency symbols and commas
            cleaned = price_str.replace("$", "").replace(",", "").replace("¥", "").strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0
    
    def _calculate_final_price(self, ali_rec_price: str, amazon_min_price: str) -> str:
        """
        Calculate final price based on rules:
        - discount = 0.95 (from config)
        - if ali_rec_price < amazon_min_price * discount → use ali_rec_price
        - else if ali_rec_price < amazon_min_price → use ali_rec_price
        - else (ali_rec_price >= amazon_min_price) → leave blank
        """
        discount = getattr(config, 'PRICE_DISCOUNT', 0.95)
        
        ali_price = self._parse_price(ali_rec_price)
        amazon_price = self._parse_price(amazon_min_price)
        
        # If either price is invalid/zero, return blank
        if ali_price <= 0 or amazon_price <= 0:
            return ""
        
        # Apply price rules
        if ali_price < amazon_price * discount:
            return ali_rec_price
        elif ali_price < amazon_price:
            return ali_rec_price
        else:
            # ali_price >= amazon_price, leave blank
            return ""
    
    def _parse_skus(self, text: str) -> List[Dict[str, str]]:
        """Parse SKUs from text."""
        skus: List[Dict[str, str]] = []
        for line in text.splitlines():
            if "|" in line:
                name, url = line.split("|", 1)
                name = name.strip()
                url = url.strip()
                if name and url:
                    skus.append({"name": name, "image_url": url})
        return skus
    
    def _skus_to_lines(self, skus: List[Dict[str, str]]) -> str:
        """Convert SKUs to text lines."""
        return "\n".join(f"{sku.get('name','')} | {sku.get('image_url','')}" for sku in skus if sku)
    
    def _load_data(self):
        """Load data from local cache only (DDB is written on save)."""
        self.items = self._load_cache_items()
        if not self.items:
            self.warning_label.setText("No data available. Run scraper to populate products.")
            self.warning_label.show()
        else:
            self.warning_label.hide()
        
        self.items = [self._normalize_item(item) for item in self.items]
        self.items = sorted(self.items, key=lambda x: x.get("timestamp", ""), reverse=True)
        
        print(f"Total cached items: {len(self.items)}")
        self._apply_filter()
    
    def _refresh_list_preserve_selection(self, current_product_id: str):
        """Refresh list but keep current selection if possible."""
        # Load new data
        self.items = self._load_cache_items()
        if not self.items:
            self.warning_label.setText("No data available. Run scraper to populate products.")
            self.warning_label.show()
        else:
            self.warning_label.hide()
        
        self.items = [self._normalize_item(item) for item in self.items]
        self.items = sorted(self.items, key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Apply filter
        filter_text = self.filter_input.text().strip()
        if filter_text:
            self.filtered_items = [i for i in self.items if filter_text in i.get("url", "")]
        else:
            self.filtered_items = self.items
        
        # Try to restore selection to the same product
        new_index = 0
        if current_product_id:
            for idx, item in enumerate(self.filtered_items):
                if item.get("product_id", "") == current_product_id:
                    new_index = idx
                    break
        
        self.selected_index = new_index
        self._update_product_list()
        # Don't update details - user may be editing
    
    def _on_load_cache(self):
        """Load cached products on demand."""
        self._load_data()
    
    def _on_clean_cache(self):
        """Clean cache folder (products and images)."""
        try:
            if os.path.exists(PRODUCTS_DIR):
                for fname in os.listdir(PRODUCTS_DIR):
                    if fname.endswith(".json"):
                        os.remove(os.path.join(PRODUCTS_DIR, fname))
            if os.path.exists(IMAGES_DIR):
                import shutil
                shutil.rmtree(IMAGES_DIR, ignore_errors=True)
                os.makedirs(IMAGES_DIR, exist_ok=True)
            self.items = []
            self.filtered_items = []
            self._apply_filter()
            QMessageBox.information(self, "缓存", "缓存已清空。")
        except Exception as exc:
            QMessageBox.critical(self, "缓存", f"清空缓存失败: {exc}")
    
    def _apply_filter(self):
        """Apply URL filter."""
        filter_text = self.filter_input.text().strip()
        if filter_text:
            self.filtered_items = [i for i in self.items if filter_text in i.get("url", "")]
        else:
            self.filtered_items = self.items
        
        self._update_product_list()
        if self.filtered_items:
            self.selected_index = 0
            self._update_product_details()
        else:
            self._clear_product_details()
    
    def _on_filter_changed(self):
        """Handle filter text change."""
        self._apply_filter()
    
    def _update_product_list(self):
        """Update the product list radio buttons."""
        try:
            # Clear existing buttons
            buttons_to_delete = list(self.product_button_group.buttons())
            for button in buttons_to_delete:
                try:
                    self.product_button_group.removeButton(button)
                    self.product_radio_layout.removeWidget(button)
                    button.setParent(None)
                    button.deleteLater()
                except RuntimeError:
                    # Widget already deleted, skip
                    pass
            
            if not self.filtered_items:
                no_items_label = QLabel("未找到符合筛选条件的产品。")
                no_items_label.setStyleSheet("color: #ff8800; padding: 10px;")
                self.product_radio_layout.addWidget(no_items_label)
                return
            
            # Create radio buttons for each product
            for idx, item in enumerate(self.filtered_items):
                title = item.get('title', '(untitled)')[:50]
                price = item.get('current_price', '')
                # Add checkmark for products uploaded to DDB
                uploaded_mark = "✅ " if item.get('uploaded_to_ddb', False) else ""
                label_text = f"{uploaded_mark}{title} — {price}"
                
                radio = QRadioButton(label_text)
                is_selected = (idx == self.selected_index)
                radio.setChecked(is_selected)
                # Use a closure to capture idx properly
                def make_handler(i):
                    return lambda checked: self._on_product_selected(i) if checked else None
                radio.toggled.connect(make_handler(idx))
                self.product_button_group.addButton(radio, idx)
                self.product_radio_layout.addWidget(radio)
            
            # Ensure product details are updated after creating the list
            # (toggled signal doesn't fire when setChecked is called, so we manually update)
            if self.filtered_items and self.selected_index < len(self.filtered_items):
                # Use QTimer to ensure UI is ready before updating
                QTimer.singleShot(0, self._update_product_details)
        except RuntimeError as e:
            # Widget was deleted, ignore
            if "already deleted" not in str(e):
                raise
    
    def _on_product_selected(self, index: int):
        """Handle product selection."""
        self.selected_index = index
        self._update_product_details()
    
    def _update_product_details(self):
        """Update product details form."""
        if not self.filtered_items or self.selected_index >= len(self.filtered_items):
            self._clear_product_details()
            return
        
        # Safety check - ensure widgets still exist
        if not hasattr(self, 'title_input') or self.title_input is None:
            return
        
        item = self.filtered_items[self.selected_index]
        
        try:
            self.title_input.setText(item.get("title", ""))
            self.current_price_input.setText(item.get("current_price", ""))
            self.original_price_input.setText(item.get("original_price", ""))
            self.url_input.setText(item.get("url", ""))
            
            # Set new price fields from API
            amazon_avg_price = item.get("amazon_avg_price", "")
            amazon_min_price = item.get("amazon_min_price", "")
            amazon_min_price_product = item.get("amazon_min_price_product", "")
            amazon_min_price_product_url = item.get("amazon_min_price_product_url", "")
            ali_express_rec_price = item.get("ali_express_rec_price", "")
            
            self.amazon_avg_price_label.setText(amazon_avg_price if amazon_avg_price else "N/A")
            self.amazon_min_price_label.setText(amazon_min_price if amazon_min_price else "N/A")
            self.amazon_min_price_product_label.setText(amazon_min_price_product if amazon_min_price_product else "N/A")
            self._amazon_min_price_product_url = amazon_min_price_product_url  # Store URL for click handler
            self.ali_rec_price_label.setText(ali_express_rec_price if ali_express_rec_price else "N/A")
            
            # Calculate and set final price
            final_price = item.get("final_price", "")
            if not final_price:
                final_price = self._calculate_final_price(ali_express_rec_price, amazon_min_price)
            self.final_price_input.setText(final_price)
            self.sku_gallery.set_skus(item.get("skus", []))
            self.sellpoint_text.setPlainText("\n".join(item.get("sellpoints", [])))
            self.desc_text.setPlainText(item.get("description_text", ""))
            self.suggested_title_value.setText(item.get("suggested_title", ""))
            self.suggested_seller_point.setPlainText(item.get("suggested_seller_point", ""))
            self.suggested_desc_text.setPlainText(item.get("suggested_description", ""))
            
            # Keep remote mapping in-memory for save
            self.current_gallery_remote = item.get("gallery_images_remote", item.get("gallery_images", []))
            self.current_desc_remote = item.get("description_images_remote", item.get("description_images", []))
            self.current_sku_remote = {sku.get("name", ""): sku.get("image_url_remote", sku.get("image_url", "")) for sku in item.get("skus", [])}
            
            # Ensure local paths are absolute for thumbnail loading
            def to_abs(url: str) -> str:
                if not url:
                    return url
                if os.path.exists(url):
                    return os.path.abspath(url)
                abs_path = os.path.abspath(url)
                if os.path.exists(abs_path):
                    return abs_path
                return url
            
            gallery_local = [to_abs(u) for u in item.get("gallery_images", []) or []]
            desc_local = [to_abs(u) for u in item.get("description_images", []) or []]
            skus_local = []
            for sku in item.get("skus", []) or []:
                sku_dict = {
                    "name": sku.get("name", ""),
                    "image_url": to_abs(sku.get("image_url", "")),
                    "image_url_remote": sku.get("image_url_remote", sku.get("image_url", "")),
                }
                # Preserve price fields
                if "current_price" in sku:
                    sku_dict["current_price"] = sku.get("current_price", "")
                if "history_price" in sku:
                    sku_dict["history_price"] = sku.get("history_price", "")
                elif "original_price" in sku:  # Backward compatibility
                    sku_dict["history_price"] = sku.get("original_price", "")
                skus_local.append(sku_dict)
            
            # Original galleries are commented out - only set if they exist
            if self.gallery_gallery:
                self.gallery_gallery.set_urls(gallery_local)
            if self.desc_gallery:
                self.desc_gallery.set_urls(desc_local)
            self.sku_gallery.set_skus(skus_local)
            
            # Set recommended images (processed URLs from CloudFront)
            gallery_recommended = item.get("gallery_images_recommended", []) or []
            desc_recommended = item.get("description_images_recommended", []) or []
            self.gallery_recommended.set_urls(gallery_recommended)
            self.desc_recommended.set_urls(desc_recommended)
            
            # Update status
            timestamp = item.get("timestamp", "")
            if timestamp:
                formatted_time = self._format_timestamp(timestamp)
                self.status_label.setText(
                    f"Export all is intentionally disabled in this prototype. "
                    f"Last updated: {formatted_time}"
                )
            else:
                self.status_label.setText("Export all is intentionally disabled in this prototype.")
        except RuntimeError as e:
            # Widget was deleted, ignore
            if "already deleted" not in str(e):
                raise
    
    def _clear_product_details(self):
        """Clear product details form."""
        try:
            if hasattr(self, 'title_input') and self.title_input is not None:
                self.title_input.clear()
                self.current_price_input.clear()
                self.original_price_input.clear()
                self.final_price_input.clear()
                self.url_input.clear()
                self.sku_gallery.set_skus([])
                self.sellpoint_text.clear()
                self.desc_text.clear()
                # Original galleries are commented out - only clear if they exist
                if self.gallery_gallery:
                    self.gallery_gallery.set_urls([])
                if self.desc_gallery:
                    self.desc_gallery.set_urls([])
                self.gallery_recommended.set_urls([])
                self.desc_recommended.set_urls([])
                self.status_label.clear()
                # Clear new price labels
                self.amazon_avg_price_label.setText("")
                self.amazon_min_price_label.setText("")
                self.amazon_min_price_product_label.setText("")
                self.ali_rec_price_label.setText("")
        except RuntimeError as e:
            # Widget was deleted, ignore
            if "already deleted" not in str(e):
                raise
    
    def _on_gallery_urls_changed(self, urls: List[str]):
        """Handle gallery URLs change."""
        pass  # URLs are stored in gallery widget
    
    def _on_desc_urls_changed(self, urls: List[str]):
        """Handle description URLs change."""
        pass  # URLs are stored in gallery widget
    
    def _on_gallery_recommended_changed(self, urls: List[str]):
        """Handle recommended gallery URLs change."""
        pass  # URLs are stored in gallery widget
    
    def _on_desc_recommended_changed(self, urls: List[str]):
        """Handle recommended description URLs change."""
        pass  # URLs are stored in gallery widget
    
    def _on_skus_changed(self, skus: List[Dict[str, str]]):
        """Handle SKUs change."""
        pass  # SKUs are stored in SKU gallery widget
    
    def _open_url_in_browser(self):
        """Open the URL in the default browser."""
        url = self.url_input.text().strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))
    
    def _open_amazon_min_price_product_url(self):
        """Open the Amazon min price product URL in the default browser."""
        if self._amazon_min_price_product_url:
            QDesktopServices.openUrl(QUrl(self._amazon_min_price_product_url))
    
    def _on_export_csv(self):
        """Export all products to CSV file."""
        if not self.items:
            self.status_label.setText("No products to export.")
            return
        
        # Ask user for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Products to CSV",
            os.path.join(os.path.expanduser("~"), "products_export.csv"),
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            return  # User cancelled
        
        try:
            # Collect all unique keys from all items
            all_keys = set()
            for item in self.items:
                all_keys.update(item.keys())
            
            # Define column order (important fields first)
            priority_keys = [
                "id", "title", "suggested_title", "url", "current_price", "original_price",
                "suggest_price", "sellpoints", "suggested_seller_point", "description_text",
                "suggested_description", "gallery_images", "gallery_images_remote",
                "description_images", "description_images_remote", "skus", "status", "timestamp"
            ]
            # Add priority keys first, then remaining keys alphabetically
            columns = [k for k in priority_keys if k in all_keys]
            remaining = sorted(all_keys - set(columns))
            columns.extend(remaining)
            
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                
                for item in self.items:
                    row = []
                    for col in columns:
                        value = item.get(col, "")
                        # Handle list values - join with " | "
                        if isinstance(value, list):
                            # For SKUs, extract relevant info
                            if col == "skus":
                                sku_strs = []
                                for sku in value:
                                    if isinstance(sku, dict):
                                        name = sku.get("name", "")
                                        img = sku.get("image_url_remote", sku.get("image_url", ""))
                                        sku_strs.append(f"{name}:{img}")
                                    else:
                                        sku_strs.append(str(sku))
                                value = " | ".join(sku_strs)
                            else:
                                value = " | ".join(str(v) for v in value)
                        elif isinstance(value, dict):
                            value = json.dumps(value, ensure_ascii=False)
                        else:
                            value = str(value) if value is not None else ""
                        row.append(value)
                    writer.writerow(row)
            
            self.status_label.setText(f"Exported {len(self.items)} products to {file_path}")
        except Exception as e:
            self.status_label.setText(f"Export failed: {e}")
    
    def _on_save_clicked(self):
        """Handle save button click."""
        try:
            if not self.filtered_items or self.selected_index >= len(self.filtered_items):
                self.status_label.setText("No product selected.")
                return
            
            selected_item = self.filtered_items[self.selected_index]
            
            # Build mapping for gallery/desc to preserve original URLs by normalized key
            def norm(url: str) -> str:
                if not url:
                    return url
                if os.path.exists(url):
                    return os.path.abspath(url)
                abs_path = os.path.abspath(url)
                return abs_path if os.path.exists(abs_path) else url
            
            gallery_map = {}
            for idx, local in enumerate(selected_item.get("gallery_images", [])):
                key = norm(local)
                remote_list = selected_item.get("gallery_images_remote", [])
                remote = remote_list[idx] if idx < len(remote_list) else local
                gallery_map[key] = remote
            
            desc_map = {}
            for idx, local in enumerate(selected_item.get("description_images", [])):
                key = norm(local)
                remote_list = selected_item.get("description_images_remote", [])
                remote = remote_list[idx] if idx < len(remote_list) else local
                desc_map[key] = remote
            
            sku_map = {}
            for sku in selected_item.get("skus", []):
                name = sku.get("name", "")
                remote = sku.get("image_url_remote", sku.get("image_url", ""))
                sku_map[name] = remote
            
            # Current UI values (normalized) - use selected_item values if galleries are hidden
            gallery_local = [norm(u) for u in (self.gallery_gallery.get_urls() if self.gallery_gallery else selected_item.get("gallery_images", []))]
            desc_local = [norm(u) for u in (self.desc_gallery.get_urls() if self.desc_gallery else selected_item.get("description_images", []))]
            skus_current = []
            for sku in self.sku_gallery.get_skus():
                sku_dict = {
                    "name": sku.get("name", ""),
                    "image_url": norm(sku.get("image_url", "")),
                    "image_url_remote": sku.get("image_url_remote", sku.get("image_url", "")),
                }
                # Preserve price fields
                if "current_price" in sku:
                    sku_dict["current_price"] = sku.get("current_price", "")
                if "history_price" in sku:
                    sku_dict["history_price"] = sku.get("history_price", "")
                skus_current.append(sku_dict)
            
            # Rebuild remote lists aligned to current local lists
            gallery_remote = [gallery_map.get(url, url) for url in gallery_local]
            desc_remote = [desc_map.get(url, url) for url in desc_local]
            skus_remote = []
            for sku in skus_current:
                name = sku.get("name", "")
                image_url = sku.get("image_url", "")
                remote = sku_map.get(name, image_url)
                sku_remote_dict = {
                    "name": name,
                    "image_url": image_url,
                    "image_url_remote": remote,
                }
                # Preserve price fields
                if "current_price" in sku:
                    sku_remote_dict["current_price"] = sku.get("current_price", "")
                if "history_price" in sku:
                    sku_remote_dict["history_price"] = sku.get("history_price", "")
                skus_remote.append(sku_remote_dict)
            
            updated = self._normalize_item(selected_item)
            updated.update({
                "title": self.title_input.text().strip(),
                "current_price": self.current_price_input.text().strip(),
                "original_price": self.original_price_input.text().strip() or selected_item.get("original_price", ""),
                "final_price": self.final_price_input.text().strip(),
                "gallery_images": gallery_local,
                "gallery_images_remote": gallery_remote,
                "gallery_images_recommended": self.gallery_recommended.get_urls(),
                "skus": skus_remote,
                "sellpoints": self._parse_lines(self.sellpoint_text.toPlainText()),
                "description_text": self.desc_text.toPlainText(),
                "description_images": desc_local,
                "description_images_remote": desc_remote,
                "description_images_recommended": self.desc_recommended.get_urls(),
                "suggested_title": self.suggested_title_value.text().strip(),
                "suggested_seller_point": selected_item.get("suggested_seller_point", ""),
                "suggested_description": selected_item.get("suggested_description", ""),
                # Preserve price fields from API
                "amazon_avg_price": selected_item.get("amazon_avg_price", ""),
                "amazon_min_price": selected_item.get("amazon_min_price", ""),
                "amazon_min_price_product": selected_item.get("amazon_min_price_product", ""),
                "amazon_min_price_product_url": selected_item.get("amazon_min_price_product_url", ""),
                "ali_express_rec_price": selected_item.get("ali_express_rec_price", ""),
            })
            
            # Save locally first
            self._save_cache_item(updated)
            
            # Push to DynamoDB using ordered schema that follows UI layout
            table, warning = self._get_table()
            if table:
                # Create ordered DynamoDB item following UI layout
                ddb_item = {
                    # 1. Basic info (top of UI)
                    "product_id": updated.get("product_id", ""),
                    "title": updated.get("title", ""),
                    "suggested_title": updated.get("suggested_title", ""),
                    "url": updated.get("url", ""),
                    
                    # 2. Prices (price section)
                    "current_price": updated.get("current_price", ""),
                    "original_price": updated.get("original_price", ""),
                    "amazon_avg_price": updated.get("amazon_avg_price", ""),
                    "amazon_min_price": updated.get("amazon_min_price", ""),
                    "amazon_min_price_product": updated.get("amazon_min_price_product", ""),
                    "amazon_min_price_product_url": updated.get("amazon_min_price_product_url", ""),
                    "ali_express_rec_price": updated.get("ali_express_rec_price", ""),
                    "final_price": updated.get("final_price", ""),
                    
                    # 3. SKUs
                    "skus": [
                        {"name": sku.get("name", ""), "image_url": sku.get("image_url_remote", sku.get("image_url", ""))}
                        for sku in updated.get("skus", [])
                    ],
                    
                    # 4. Sellpoints (original and suggested)
                    "sellpoints": updated.get("sellpoints", []),
                    "suggested_seller_point": updated.get("suggested_seller_point", ""),
                    
                    # 5. Description (original and suggested)
                    "description_text": updated.get("description_text", ""),
                    "suggested_description": updated.get("suggested_description", ""),
                    
                    # 6. Images
                    "gallery_images": updated.get("gallery_images_remote", updated.get("gallery_images", [])),
                    "gallery_images_recommended": updated.get("gallery_images_recommended", []),
                    "description_images": updated.get("description_images_remote", updated.get("description_images", [])),
                    "description_images_recommended": updated.get("description_images_recommended", []),
                    
                    # 7. Metadata
                    "source": updated.get("source", "aliexpress"),
                    "status": updated.get("status", ""),
                    "timestamp": updated.get("timestamp", ""),
                }
                table.put_item(Item=ddb_item)
                
                # Mark as uploaded to DynamoDB and re-save locally
                updated["uploaded_to_ddb"] = True
                self._save_cache_item(updated)
                self.status_label.setText("✅ 已保存到本地和DynamoDB")
            elif warning:
                print(warning)
                self.status_label.setText("已保存到本地（DynamoDB不可用）")
            # Reload data
            QTimer.singleShot(500, self._load_data)
        except RuntimeError as e:
            # Widget was deleted, show error
            if "already deleted" in str(e):
                self.status_label.setText("Widget was deleted. Please refresh the application.")
            else:
                raise
        except Exception as exc:
            self.status_label.setText(f"Failed to save: {exc}")
    
    def _on_delete_clicked(self):
        """Handle delete button click."""
        if not self.filtered_items or self.selected_index >= len(self.filtered_items):
            QMessageBox.warning(self, "错误", "未选择产品。")
            return
        
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除此产品吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            selected_item = self.filtered_items[self.selected_index]
            product_id = selected_item.get("product_id", "")
            
            try:
                # Delete from cache first
                self._delete_cache_item(product_id)
                if self.table:
                    self.table.delete_item(Key={"product_id": product_id})
                self.status_label.setText("Deleted locally; DynamoDB deleted if available.")
                # Reload data
                QTimer.singleShot(500, self._load_data)
            except Exception as exc:
                self.status_label.setText(f"Failed to delete: {exc}")
    
    def _on_source_changed(self, source: str):
        """Handle source selection change."""
        if source == "Amazon":
            self.scraper_url_input.setPlaceholderText("输入亚马逊产品URL（如：https://www.amazon.com/dp/...）")
        else:
            self.scraper_url_input.setPlaceholderText("输入速卖通产品URL（可选，留空则爬取搜索结果页）")
    
    def _on_run_scraper(self):
        """Handle run scraper button click."""
        if self.scraper_thread and self.scraper_thread.isRunning():
            QMessageBox.warning(self, "警告", "爬虫正在运行中！")
            return
        
        # Get target URL and source
        target_url = self.scraper_url_input.text().strip()
        source = self.source_combo.currentText().lower()  # "aliexpress" or "amazon"
        
        # Create resume event and start scraper thread
        import threading
        self.scraper_resume_event = threading.Event()
        self.scraper_thread = ScraperThread(
            mode=getattr(config, 'MODE', 'detailed'),
            resume_event=self.scraper_resume_event,
            source=source
        )
        if target_url:
            self.scraper_thread.set_target_url(target_url)
        
        # Connect signals
        self.scraper_thread.log_message.connect(self._on_scraper_log)
        self.scraper_thread.finished_successfully.connect(self._on_scraper_finished)
        self.scraper_thread.error_occurred.connect(self._on_scraper_error)
        self.scraper_thread.item_scraped.connect(self._on_item_scraped)
        # Also connect to the built-in finished signal to ensure cleanup happens
        self.scraper_thread.finished.connect(self._on_scraper_thread_finished)
        
        # Disable button while running
        self.run_scraper_btn.setEnabled(False)
        self.run_scraper_btn.setText("Running...")
        self.resume_btn.setEnabled(True)
        self.stop_scraper_btn.setEnabled(True)
        
        # Clear logs
        self.logs_text.clear()
        
        # Start thread
        self.scraper_thread.start()
    
    def _on_stop_scraper(self):
        """Stop the scraper immediately - kill browser and don't store current item."""
        if self.scraper_thread and self.scraper_thread.isRunning():
            self.logs_text.append("🛑 Stopping scraper...")
            
            # Stop the scraper (this kills the browser)
            self.scraper_thread.stop()
            
            # Set resume event to unblock any waiting
            if self.scraper_resume_event:
                self.scraper_resume_event.set()
            
            # Terminate the thread if it doesn't stop gracefully
            if not self.scraper_thread.wait(2000):  # Wait 2 seconds
                self.scraper_thread.terminate()
                self.scraper_thread.wait(1000)
            
            # Reset UI state
            self.run_scraper_btn.setEnabled(True)
            self.run_scraper_btn.setText("开始爬取")
            self.resume_btn.setEnabled(False)
            self.stop_scraper_btn.setEnabled(False)
            
            self.logs_text.append("🛑 Scraper stopped. Ongoing item was not saved.")

    def _on_resume_scraper(self):
        """Resume scraper waiting step."""
        if self.scraper_resume_event:
            self.scraper_resume_event.set()
    
    def _on_scraper_log(self, message: str):
        """Handle scraper log message."""
        try:
            if hasattr(self, 'logs_text') and self.logs_text is not None:
                self.logs_text.append(message)
                # Auto-scroll to bottom
                scrollbar = self.logs_text.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(scrollbar.maximum())
        except RuntimeError as e:
            # Widget was deleted, ignore
            if "already deleted" not in str(e):
                raise
    
    def _on_scraper_finished(self):
        """Handle scraper completion (custom signal from ScraperThread)."""
        try:
            self.run_scraper_btn.setEnabled(True)
            self.run_scraper_btn.setText("开始爬取")
            self.resume_btn.setEnabled(False)
            self.stop_scraper_btn.setEnabled(False)
            # Final refresh
            QTimer.singleShot(500, self._load_data)
        except RuntimeError as e:
            # Widget was deleted, ignore
            if "already deleted" not in str(e):
                print(f"Error in _on_scraper_finished: {e}")
        except Exception as e:
            print(f"Unexpected error in _on_scraper_finished: {e}")
    
    def _on_scraper_thread_finished(self):
        """Handle QThread finished signal - ensure UI is reset even if other signals fail."""
        try:
            # Ensure buttons are in correct state even if other handlers failed
            if hasattr(self, 'run_scraper_btn') and self.run_scraper_btn:
                if not self.run_scraper_btn.isEnabled():
                    self.run_scraper_btn.setEnabled(True)
                    self.run_scraper_btn.setText("开始爬取")
            if hasattr(self, 'resume_btn') and self.resume_btn:
                self.resume_btn.setEnabled(False)
            if hasattr(self, 'stop_scraper_btn') and self.stop_scraper_btn:
                self.stop_scraper_btn.setEnabled(False)
        except RuntimeError:
            pass  # Widget was deleted
        except Exception as e:
            print(f"Error in _on_scraper_thread_finished: {e}")
    
    def _on_item_scraped(self):
        """Handle single item scraped - refresh product list without changing selection."""
        # Remember current selection before refresh
        current_product_id = None
        if self.filtered_items and self.selected_index < len(self.filtered_items):
            current_product_id = self.filtered_items[self.selected_index].get("product_id", "")
        
        # Refresh product list from cache
        QTimer.singleShot(100, lambda: self._refresh_list_preserve_selection(current_product_id))
    
    def _on_scraper_error(self, error: str):
        """Handle scraper error."""
        self.run_scraper_btn.setEnabled(True)
        self.run_scraper_btn.setText("开始爬取")
        self.resume_btn.setEnabled(False)
        self.stop_scraper_btn.setEnabled(False)
        QMessageBox.critical(self, "错误", f"爬虫错误: {error}")
    
    def closeEvent(self, event):
        """Handle window close event."""
        if self.scraper_thread and self.scraper_thread.isRunning():
            reply = QMessageBox.question(
                self, "爬虫运行中",
                "爬虫正在运行中，确定要停止并退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Stop the scraper
                self.scraper_thread.stop()
                if self.scraper_resume_event:
                    self.scraper_resume_event.set()
                
                # Wait for thread to finish gracefully
                if not self.scraper_thread.wait(3000):  # Wait up to 3 seconds
                    # If still running, terminate it
                    self.scraper_thread.terminate()
                    self.scraper_thread.wait(1000)  # Wait for termination
                
                # Disconnect all signals to prevent issues during cleanup
                try:
                    self.scraper_thread.log_message.disconnect()
                    self.scraper_thread.finished_successfully.disconnect()
                    self.scraper_thread.error_occurred.disconnect()
                    self.scraper_thread.item_scraped.disconnect()
                    self.scraper_thread.finished.disconnect()
                except (RuntimeError, TypeError):
                    pass  # Signals may already be disconnected
            else:
                event.ignore()
                return
        
        # Ensure thread is cleaned up even if not running
        if self.scraper_thread:
            try:
                if self.scraper_thread.isRunning():
                    self.scraper_thread.terminate()
                    self.scraper_thread.wait(1000)
                # Disconnect signals
                try:
                    self.scraper_thread.log_message.disconnect()
                    self.scraper_thread.finished_successfully.disconnect()
                    self.scraper_thread.error_occurred.disconnect()
                    self.scraper_thread.item_scraped.disconnect()
                    self.scraper_thread.finished.disconnect()
                except (RuntimeError, TypeError):
                    pass
            except Exception:
                pass
        
        # Clean up all image loader threads from galleries
        self._cleanup_all_image_loader_threads()
        
        event.accept()
    
    def _cleanup_all_image_loader_threads(self):
        """Clean up all image loader threads from gallery widgets."""
        import sys
        from PySide6.QtCore import QThread
        
        # Find all ImageGallery widgets and clean up their threads
        def cleanup_widget_threads(widget, depth=0):
            """Recursively clean up threads in widget and its children."""
            if widget is None:
                return
            indent = "  " * depth
            # Clean up this widget's threads if it has any
            if hasattr(widget, '_cleanup_loader_thread'):
                try:
                    thread = getattr(widget, '_loader_thread', None)
                    if thread and thread.isRunning():
                        print(f"{indent}Cleaning up thread in {type(widget).__name__} (objectName: {widget.objectName()})")
                    widget._cleanup_loader_thread()
                except Exception as e:
                    print(f"{indent}Error cleaning up thread in {type(widget).__name__}: {e}")
            # Recursively clean up children
            if hasattr(widget, 'children'):
                for child in widget.children():
                    if isinstance(child, QWidget):
                        cleanup_widget_threads(child, depth + 1)
            # Also check layout items
            if hasattr(widget, 'layout') and widget.layout():
                for i in range(widget.layout().count()):
                    item = widget.layout().itemAt(i)
                    if item and item.widget():
                        cleanup_widget_threads(item.widget(), depth + 1)
        
        print("DEBUG: Starting cleanup of all image loader threads...")
        try:
            cleanup_widget_threads(self.centralWidget())
        except Exception as e:
            print(f"DEBUG: Error in cleanup_widget_threads: {e}")
        
        # Also check for any remaining QThread instances
        try:
            from PySide6.QtCore import QCoreApplication
            app = QCoreApplication.instance()
            if app:
                # Process events to allow threads to finish
                app.processEvents()
        except Exception:
            pass
        
        print("DEBUG: Finished cleanup of all image loader threads.")

