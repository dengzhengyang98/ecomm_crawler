"""SKU gallery widget displaying SKUs as images with names."""
from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QGridLayout, QPushButton, QLineEdit, QHBoxLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage, QImageReader
import os
import requests


class SKUThumbnail(QWidget):
    """Single SKU thumbnail with image and name label."""
    
    image_clicked = Signal(str)  # Emits image URL when clicked
    delete_clicked = Signal(str)  # Emits SKU name when delete clicked
    price_changed = Signal(str, str, str)  # Emits (sku_name, current_price, history_price) when prices change
    
    def __init__(self, sku_name: str, image_url: str, current_price: str = "", history_price: str = "", parent=None):
        super().__init__(parent)
        self.sku_name = sku_name
        self.image_url = image_url
        self.current_price = current_price
        self.history_price = history_price
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)  # Increased spacing to prevent overlap
        
        # Container for image and delete button
        image_container = QWidget()
        image_container.setFixedSize(100, 100)
        image_container_layout = QVBoxLayout(image_container)
        image_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Image label
        self.image_label = QLabel()
        self.image_label.setFixedSize(100, 100)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("""
            QLabel {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
            }
        """)
        self.image_label.setCursor(Qt.PointingHandCursor)
        self.image_label.mousePressEvent = self._on_image_clicked
        
        # Load thumbnail
        self._load_thumbnail()
        
        # Delete button (overlay on top-right, parented to image label)
        self.delete_btn = QPushButton("✕", self.image_label)
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.move(72, 2)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4444;
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #cc0000;
            }
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.sku_name))
        self.delete_btn.raise_()
        
        image_container_layout.addWidget(self.image_label)
        layout.addWidget(image_container)
        
        # Name label - format SKU name (replace commas with dashes)
        # Replace ", " with " - " and "," with " -" to handle various comma formats
        formatted_sku_name = sku_name if sku_name else ""
        if formatted_sku_name:
            formatted_sku_name = formatted_sku_name.replace(", ", " - ").replace(",", " -")
        name_label = QLabel(formatted_sku_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setMaximumWidth(100)
        name_label.setMaximumHeight(40)  # Limit height to prevent overlap
        name_label.setStyleSheet("font-size: 10px; color: #333333; font-weight: 500; padding: 2px;")
        layout.addWidget(name_label)
        
        # Single editable final price field
        self.current_price_input = QLineEdit()
        self.current_price_input.setPlaceholderText("Price")
        # Use current_price as the final price, fallback to history_price if current_price is empty
        final_price = current_price if current_price and current_price != "N/A" else (history_price if history_price and history_price != "N/A" else "")
        self.current_price_input.setText(final_price)
        self.current_price_input.setMaximumWidth(100)
        self.current_price_input.setMaximumHeight(24)
        self.current_price_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 3px;
                border: 1px solid #27ae60;
                border-radius: 3px;
                background-color: #f0fff4;
            }
            QLineEdit:focus {
                border: 1px solid #27ae60;
                background-color: white;
            }
        """)
        self.current_price_input.textChanged.connect(self._on_price_changed)
        layout.addWidget(self.current_price_input)
    
    def _load_thumbnail(self):
        """Load thumbnail image."""
        pixmap = self._load_image_from_url(self.image_url)
        if pixmap and (not pixmap.isNull()):
            scaled = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(scaled)
        else:
            self.image_label.setPixmap(QPixmap())  # clear pixmap
            self.image_label.setText("No\nImage")
    
    def _load_image_from_url(self, url: str) -> Optional[QPixmap]:
        """Load image from URL or local path (relative or absolute)."""
        try:
            if url:
                from ui.main_window import IMAGES_DIR  # lazy import to avoid cycles
                basename = os.path.basename(url)
                candidates = [url, os.path.abspath(url), os.path.join(IMAGES_DIR, basename)]
                for path in candidates:
                    if path and os.path.exists(path):
                        reader = QImageReader(path)
                        reader.setAutoTransform(True)
                        img = reader.read()
                        if not img.isNull():
                            pm = QPixmap.fromImage(img)
                            if pm and (not pm.isNull()):
                                return pm
                # As last resort, walk IMAGES_DIR to find by basename
                for root, _, files in os.walk(IMAGES_DIR):
                    if basename in files:
                        candidate = os.path.join(root, basename)
                        reader = QImageReader(candidate)
                        reader.setAutoTransform(True)
                        img = reader.read()
                        if not img.isNull():
                            pm = QPixmap.fromImage(img)
                            if pm and (not pm.isNull()):
                                return pm
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
            }
            response = requests.get(url, timeout=10, headers=headers)
            if response.status_code == 200:
                image = QImage()
                image.loadFromData(response.content)
                pm = QPixmap.fromImage(image)
                if not pm.isNull():
                    return pm
        except Exception:
            pass
        return None
    
    def _on_image_clicked(self, event):
        """Handle image click."""
        self.image_clicked.emit(self.image_url)
    
    def _on_price_changed(self):
        """Handle price field changes."""
        final_price = self.current_price_input.text().strip()
        self.current_price = final_price
        # Keep history_price for backward compatibility, but use final_price as current
        self.price_changed.emit(self.sku_name, final_price, self.history_price)
    
    def get_prices(self):
        """Get current price values."""
        final_price = self.current_price_input.text().strip()
        return {
            "current_price": final_price,
            "history_price": self.history_price  # Keep original history_price for reference
        }


class SKUGallery(QWidget):
    """SKU gallery widget displaying SKUs as images with names."""
    
    skus_changed = Signal(list)  # Emits when SKUs list changes
    
    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self.skus: List[Dict[str, str]] = []
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        if label:
            label_widget = QLabel(f"<b>{label}</b>")
            layout.addWidget(label_widget)
        
        # Grid layout for SKUs
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(8)
        
        grid_widget = QWidget()
        grid_widget.setLayout(self.grid_layout)
        
        layout.addWidget(grid_widget)
        
        # "No SKUs" label
        self.no_skus_label = QLabel("暂无规格")
        self.no_skus_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.no_skus_label)
        self.no_skus_label.hide()
    
    def set_skus(self, skus: List[Dict[str, str]]):
        """Set the list of SKUs."""
        self.skus = skus.copy() if skus else []
        self._update_display()
    
    def get_skus(self) -> List[Dict[str, str]]:
        """Get the current list of SKUs with updated prices from UI."""
        # Get prices from thumbnail widgets
        skus_with_prices = []
        for idx in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(idx)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, SKUThumbnail):
                    sku_name = widget.sku_name
                    image_url = widget.image_url
                    prices = widget.get_prices()
                    # Find matching SKU in self.skus to preserve other fields
                    matching_sku = next((s for s in self.skus if s.get('name') == sku_name), {})
                    sku_dict = {
                        "name": sku_name,
                        "image_url": image_url,
                        "image_url_remote": matching_sku.get("image_url_remote", image_url),
                        "current_price": prices["current_price"],
                        "history_price": prices["history_price"]
                    }
                    skus_with_prices.append(sku_dict)
        return skus_with_prices if skus_with_prices else self.skus.copy()
    
    def _update_display(self):
        """Update the gallery display."""
        # Clear existing widgets
        widgets_to_delete = []
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # Clean up any threads in the widget (e.g., image loader threads)
                if hasattr(widget, '_cleanup_loader_thread'):
                    try:
                        widget._cleanup_loader_thread()
                    except Exception:
                        pass
                widgets_to_delete.append(widget)
        
        # Delete widgets
        for widget in widgets_to_delete:
            widget.setParent(None)
            widget.deleteLater()
        
        if not self.skus:
            self.no_skus_label.show()
            return
        
        self.no_skus_label.hide()
        
        # Add SKU thumbnails in grid (4 columns)
        num_cols = 4
        for idx, sku in enumerate(self.skus):
            row = idx // num_cols
            col = idx % num_cols
            
            sku_name = sku.get('name', '')
            image_url = sku.get('image_url', '')
            # Safely get price fields (may not exist in older cached data)
            # Use current_price as final price, fallback to history_price if needed
            current_price = sku.get('current_price', '') or ''
            if not current_price:
                # Fallback to history_price if current_price is empty
                current_price = sku.get('history_price', '') or sku.get('original_price', '') or ''
            # Support both history_price (new) and original_price (old) for backward compatibility
            history_price = sku.get('history_price', '') or sku.get('original_price', '') or ''
            
            # Show SKU even if no image (text-based SKUs)
            if sku_name:
                try:
                    thumbnail = SKUThumbnail(
                        sku_name, 
                        image_url or "", 
                        current_price=current_price,
                        history_price=history_price
                    )
                    if image_url:  # Only connect if there's an image to click
                        thumbnail.image_clicked.connect(self._on_image_clicked)
                    thumbnail.delete_clicked.connect(self._on_delete_clicked)
                    thumbnail.price_changed.connect(self._on_price_changed)
                    
                    self.grid_layout.addWidget(thumbnail, row, col)
                except Exception as e:
                    # Handle any errors gracefully (e.g., missing price fields in old data)
                    print(f"Warning: Error creating SKU thumbnail for {sku_name}: {e}")
                    continue
    
    def _on_image_clicked(self, url: str):
        """Handle image click - show enlarged dialog."""
        from ui.components.image_gallery import ImageEnlargeDialog
        dialog = ImageEnlargeDialog(url, self)
        dialog.exec()
    
    def _on_delete_clicked(self, sku_name: str):
        """Handle delete button click."""
        self.skus = [sku for sku in self.skus if sku.get('name') != sku_name]
        self._update_display()
        self.skus_changed.emit(self.get_skus())
    
    def _on_price_changed(self, sku_name: str, current_price: str, history_price: str):
        """Handle price change from thumbnail."""
        # Update the SKU in self.skus
        for sku in self.skus:
            if sku.get('name') == sku_name:
                sku['current_price'] = current_price
                sku['history_price'] = history_price
                break
        # Emit change signal
        self.skus_changed.emit(self.get_skus())

