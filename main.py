"""Main entry point for E-Commerce Product Manager (AliExpress & Amazon)."""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
from ui.main_window import MainWindow


def main():
    """Launch the application."""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("电商产品管理器")
    app.setOrganizationName("电商爬虫")
    
    # Force light mode - don't follow system dark mode
    app.setStyle("Fusion")
    
    # Create a light palette
    light_palette = QPalette()
    light_palette.setColor(QPalette.Window, QColor(240, 240, 240))
    light_palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
    light_palette.setColor(QPalette.Base, QColor(255, 255, 255))
    light_palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
    light_palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
    light_palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    light_palette.setColor(QPalette.Text, QColor(0, 0, 0))
    light_palette.setColor(QPalette.Button, QColor(240, 240, 240))
    light_palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
    light_palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    light_palette.setColor(QPalette.Link, QColor(0, 100, 200))
    light_palette.setColor(QPalette.Highlight, QColor(0, 120, 215))
    light_palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    
    app.setPalette(light_palette)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

