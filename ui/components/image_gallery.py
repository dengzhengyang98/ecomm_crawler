"""Image gallery widget with click-to-enlarge functionality."""
import os
from typing import List, Optional, Dict
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QDialog, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QMimeData, QThread, QObject
from PySide6.QtGui import QPixmap, QImage, QImageReader, QDrag
import requests
from io import BytesIO

# Global cache for path lookups to avoid repeated directory walks
_path_cache: Dict[str, str] = {}
_images_dir_scanned = False


def _scan_images_dir_once():
    """Scan IMAGES_DIR once and cache all file paths."""
    global _images_dir_scanned, _path_cache
    if _images_dir_scanned:
        return
    
    try:
        from ui.main_window import IMAGES_DIR
        if os.path.exists(IMAGES_DIR):
            for root, _, files in os.walk(IMAGES_DIR):
                for f in files:
                    _path_cache[f] = os.path.join(root, f)
        _images_dir_scanned = True
    except Exception:
        pass


def _get_cached_path(url: str) -> Optional[str]:
    """Get cached path for a URL/filename."""
    if not url:
        return None
    
    # Try direct paths first (fast)
    if os.path.exists(url):
        return url
    
    abs_path = os.path.abspath(url)
    if os.path.exists(abs_path):
        return abs_path
    
    # Use cache for basename lookup
    _scan_images_dir_once()
    basename = os.path.basename(url)
    if basename in _path_cache:
        return _path_cache[basename]
    
    return None


class ImageLoader(QObject):
    """Worker object for loading images in background."""
    image_loaded = Signal(str, QPixmap)  # url, pixmap
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
    
    def run(self):
        """Load image and emit signal."""
        pixmap = self._load_image()
        self.image_loaded.emit(self.url, pixmap if pixmap else QPixmap())
    
    def _load_image(self) -> Optional[QPixmap]:
        """Load image from cached path or URL."""
        try:
            # Try cached local path first
            local_path = _get_cached_path(self.url)
            if local_path:
                reader = QImageReader(local_path)
                reader.setAutoTransform(True)
                img = reader.read()
                if not img.isNull():
                    return QPixmap.fromImage(img)
            
            # Fall back to network request
            if self.url and self.url.startswith(('http://', 'https://')):
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(self.url, timeout=5, headers=headers)
                if response.status_code == 200:
                    image = QImage()
                    image.loadFromData(response.content)
                    if not image.isNull():
                        return QPixmap.fromImage(image)
        except Exception:
            pass
        return None


class ImageEnlargeDialog(QDialog):
    """Dialog to show enlarged image."""
    
    def __init__(self, image_url: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("图片预览")
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Close button
        close_btn = QPushButton("✕ 关闭")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4444;
                color: white;
                border: none;
                border-radius: 15px;
                padding: 8px 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #cc0000;
            }
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        
        # Scroll area for image
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignCenter)
        
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setScaledContents(True)  # scale to fit
        
        # Load image
        pixmap = self._load_image_from_url(image_url)
        if pixmap and (not pixmap.isNull()):
            # Scale to fit within max dialog size
            max_w, max_h = 1200, 900
            scaled = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(scaled)
            self.resize(max(600, scaled.width() + 80), max(400, scaled.height() + 120))
        else:
            self.resize(800, 600)
            image_label.setText("Failed to load image")
            image_label.setAlignment(Qt.AlignCenter)
        
        scroll.setWidget(image_label)
        layout.addWidget(scroll)
    
    def _load_image_from_url(self, url: str) -> Optional[QPixmap]:
        """Load image from URL or local path (using cached lookup)."""
        try:
            # Try cached local path first (fast)
            local_path = _get_cached_path(url)
            if local_path:
                pm = QPixmap(local_path)
                if pm and (not pm.isNull()):
                    return pm
            
            # Fall back to network request for remote URLs
            if url and url.startswith(('http://', 'https://')):
                headers = {"User-Agent": "Mozilla/5.0"}
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


class ImageThumbnail(QWidget):
    """Single image thumbnail with delete button."""
    
    image_clicked = Signal(str)  # Emits image URL when clicked
    delete_clicked = Signal(str)  # Emits image URL when delete clicked
    
    def __init__(self, image_url: str, parent=None):
        super().__init__(parent)
        self.image_url = image_url
        self._drag_start_pos: Optional[QPoint] = None
        self._dragged = False
        self._loader_thread: Optional[QThread] = None
        self._loader: Optional[ImageLoader] = None
        self._destroyed = False  # Flag to track if widget is being destroyed
        
        # Use a fixed-size container
        self.setFixedSize(100, 100)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Image label (fills the space)
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
        self.image_label.setText("...")  # Placeholder while loading
        
        # Load thumbnail (fast, synchronous for local files)
        self._load_thumbnail_fast()
        
        # Delete button (overlay on top-right, parented to image label for reliable placement)
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
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.image_url))
        self.delete_btn.raise_()  # Ensure button is on top
        
        layout.addWidget(self.image_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_start_pos is not None:
            if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < 8:
                return
            # start drag
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self.image_url)
            drag.setMimeData(mime)
            drag.exec(Qt.MoveAction)
            self._dragged = True
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # If it was a click (no drag), emit image_clicked
        if event.button() == Qt.LeftButton and not self._dragged:
            self.image_clicked.emit(self.image_url)
        super().mouseReleaseEvent(event)
    
    def _load_thumbnail_fast(self):
        """Load thumbnail image using cached path lookup (fast), fallback to async network load."""
        local_path = _get_cached_path(self.image_url)
        if local_path:
            try:
                reader = QImageReader(local_path)
                reader.setAutoTransform(True)
                img = reader.read()
                if not img.isNull():
                    pixmap = QPixmap.fromImage(img)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.image_label.setPixmap(scaled)
                        return
            except Exception:
                pass
        
        # If local path not found, try to load from remote URL asynchronously
        if self.image_url and self.image_url.startswith(('http://', 'https://')):
            self.image_label.setText("⏳")  # Loading indicator
            self._load_thumbnail_async()
        else:
            self.image_label.setText("🖼️")
    
    def _load_thumbnail_async(self):
        """Load thumbnail from remote URL in background thread."""
        if self._destroyed:
            return
        
        # Clean up any existing thread first
        if self._loader_thread is not None:
            self._cleanup_loader_thread()
            
        self._loader_thread = QThread()
        self._loader_thread.setObjectName(f"ImageLoader-{id(self)}")  # For debugging
        self._loader = ImageLoader(self.image_url)
        self._loader.moveToThread(self._loader_thread)
        
        self._loader_thread.started.connect(self._loader.run)
        self._loader.image_loaded.connect(self._on_thumbnail_loaded)
        self._loader.image_loaded.connect(self._loader_thread.quit)
        # Connect finished to cleanup
        self._loader_thread.finished.connect(self._on_loader_thread_finished)
        # Don't use deleteLater on finished - we'll handle cleanup ourselves
        
        self._loader_thread.start()
    
    def _on_loader_thread_finished(self):
        """Handle loader thread finished signal."""
        # Mark thread as finished, but don't delete yet - let cleanup handle it
        # This is just to ensure we know the thread finished
        pass
    
    def _on_thumbnail_loaded(self, url: str, pixmap: QPixmap):
        """Handle async thumbnail load completion."""
        if self._destroyed:
            return
        try:
            if url == self.image_url and not pixmap.isNull():
                scaled = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled)
            elif pixmap.isNull():
                self.image_label.setText("🖼️")  # Failed to load
        except RuntimeError:
            pass  # Widget was deleted
    
    def _cleanup_loader_thread(self):
        """Clean up the loader thread properly."""
        if self._loader_thread is not None:
            thread = self._loader_thread
            loader = self._loader
            try:
                if thread.isRunning():
                    # Disconnect signals first to prevent issues
                    try:
                        if loader:
                            loader.image_loaded.disconnect()
                        thread.started.disconnect()
                        thread.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    
                    # Quit the thread
                    thread.quit()
                    # Wait for thread to finish (longer timeout for network requests)
                    if not thread.wait(1000):  # 1 second timeout
                        # Thread didn't finish, terminate it
                        thread.terminate()
                        thread.wait(500)  # Wait for termination
            except Exception as e:
                print(f"Warning: Error cleaning up loader thread: {e}")
            finally:
                try:
                    if loader:
                        loader.deleteLater()
                except Exception:
                    pass
                try:
                    if thread:
                        thread.deleteLater()
                except Exception:
                    pass
                self._loader_thread = None
                self._loader = None
    
    def deleteLater(self):
        """Override deleteLater to properly clean up threads."""
        self._destroyed = True
        self._cleanup_loader_thread()
        super().deleteLater()
    
    def __del__(self):
        """Destructor to ensure thread cleanup."""
        self._destroyed = True
        self._cleanup_loader_thread()
    
    def _on_image_clicked(self, event):
        """Handle image click."""
        self.image_clicked.emit(self.image_url)


class ImageGallery(QWidget):
    """Image gallery widget with thumbnails and enlarge functionality."""
    
    urls_changed = Signal(list)  # Emits when URLs list changes
    order_changed = Signal(list)  # Emits new order after drag/drop
    
    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self.image_urls: List[str] = []
        self._updating = False  # Flag to prevent updates during deletion
        self.setAcceptDrops(True)
        self._drag_start_pos: Optional[QPoint] = None
        self._drag_start_idx: Optional[int] = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        if label:
            label_widget = QLabel(f"<b>{label}</b>")
            layout.addWidget(label_widget)
        
        # Grid layout for thumbnails
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(8)
        
        grid_widget = QWidget()
        grid_widget.setLayout(self.grid_layout)
        
        layout.addWidget(grid_widget)
        
        # "No images" label
        self.no_images_label = QLabel("暂无图片")
        self.no_images_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.no_images_label)
        self.no_images_label.hide()
    
    def set_urls(self, urls: List[str]):
        """Set the list of image URLs."""
        self.image_urls = urls.copy()
        self._update_display()
    
    def get_urls(self) -> List[str]:
        """Get the current list of image URLs."""
        return self.image_urls.copy()

    def _on_reorder(self):
        self.order_changed.emit(self.image_urls)
        self.urls_changed.emit(self.image_urls)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasText():
            dragged_url = event.mimeData().text()
            pos = event.position().toPoint()
            target_idx = self._index_from_pos(pos)
            if dragged_url in self.image_urls and target_idx is not None:
                old_idx = self.image_urls.index(dragged_url)
                if old_idx != target_idx:
                    self.image_urls.insert(target_idx, self.image_urls.pop(old_idx))
                    self._update_display()
                    self._on_reorder()
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._drag_start_idx = self._index_from_pos(self._drag_start_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_start_pos:
            if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < 8:
                return
            if self._drag_start_idx is not None and 0 <= self._drag_start_idx < len(self.image_urls):
                url = self.image_urls[self._drag_start_idx]
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(url)
                drag.setMimeData(mime)
                drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)

    def _index_from_pos(self, pos: QPoint) -> Optional[int]:
        num_cols = 4
        thumb_w = 110
        thumb_h = 120
        col = pos.x() // thumb_w
        row = pos.y() // thumb_h
        idx = row * num_cols + col
        if 0 <= idx < len(self.image_urls):
            return idx
        return len(self.image_urls) - 1 if self.image_urls else None
    
    def _update_display(self):
        """Update the gallery display."""
        if self._updating:
            return
        
        self._updating = True
        
        try:
            # Disconnect and clear existing widgets
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
            
            # Delete widgets - ensure proper cleanup of loader threads first
            for widget in widgets_to_delete:
                # Clean up loader threads before deletion
                if hasattr(widget, '_cleanup_loader_thread'):
                    widget._cleanup_loader_thread()
                if hasattr(widget, '_destroyed'):
                    widget._destroyed = True
                widget.setParent(None)
                widget.deleteLater()
            
            if not self.image_urls:
                self.no_images_label.show()
                return
            
            self.no_images_label.hide()
            
            # Add thumbnails in grid (4 columns)
            num_cols = 4
            for idx, url in enumerate(self.image_urls):
                row = idx // num_cols
                col = idx % num_cols
                
                thumbnail = ImageThumbnail(url)
                thumbnail.image_clicked.connect(self._on_image_clicked)
                thumbnail.delete_clicked.connect(self._on_delete_clicked)
                
                self.grid_layout.addWidget(thumbnail, row, col)
        finally:
            self._updating = False
    
    def _on_image_clicked(self, url: str):
        """Handle image click - show enlarged dialog."""
        dialog = ImageEnlargeDialog(url, self)
        dialog.exec()
    
    def _on_delete_clicked(self, url: str):
        """Handle delete button click."""
        if url in self.image_urls:
            self.image_urls.remove(url)
            self._update_display()
            self.urls_changed.emit(self.image_urls)

