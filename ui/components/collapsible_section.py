"""Collapsible section widget for hiding/showing content."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal


class CollapsibleSection(QWidget):
    """A collapsible section with a header that can expand/collapse content."""
    
    collapsed_changed = Signal(bool)  # Emits True when collapsed, False when expanded
    
    def __init__(self, title: str, parent=None, collapsed: bool = True):
        super().__init__(parent)
        self._collapsed = collapsed
        self._title = title
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header button
        self.header = QPushButton()
        self.header.setCheckable(True)
        self.header.setChecked(not collapsed)
        self.header.clicked.connect(self._toggle)
        self._update_header_text()
        self.header.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 8px 12px;
                background-color: #e8e8e8;
                border: 1px solid #cccccc;
                border-radius: 4px;
                font-weight: bold;
                font-size: 13px;
                color: #333333;
            }
            QPushButton:hover {
                background-color: #d8d8d8;
            }
            QPushButton:checked {
                background-color: #d0d0d0;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
        """)
        layout.addWidget(self.header)
        
        # Content container
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #cccccc;
                border-top: none;
                border-bottom-left-radius: 4px;
                border-bottom-right-radius: 4px;
                background-color: #fafafa;
            }
        """)
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_frame.setVisible(not collapsed)
        layout.addWidget(self.content_frame)
    
    def _update_header_text(self):
        """Update header text with arrow indicator."""
        arrow = "▼" if not self._collapsed else "▶"
        self.header.setText(f"{arrow}  {self._title}")
    
    def _toggle(self):
        """Toggle collapsed state."""
        self._collapsed = not self._collapsed
        self.content_frame.setVisible(not self._collapsed)
        self.header.setChecked(not self._collapsed)
        self._update_header_text()
        self.collapsed_changed.emit(self._collapsed)
    
    def set_collapsed(self, collapsed: bool):
        """Set the collapsed state."""
        if self._collapsed != collapsed:
            self._toggle()
    
    def is_collapsed(self) -> bool:
        """Return True if section is collapsed."""
        return self._collapsed
    
    def add_widget(self, widget: QWidget):
        """Add a widget to the content area."""
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout):
        """Add a layout to the content area."""
        self.content_layout.addLayout(layout)
    
    def set_content_widget(self, widget: QWidget):
        """Replace all content with a single widget."""
        # Clear existing content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self.content_layout.addWidget(widget)

