"""Main entry point for AliExpress Product Manager."""
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    """Launch the application."""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("AliExpress Product Manager")
    app.setOrganizationName("EComm Crawler")
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

