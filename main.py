"""Main entry point for E-Commerce Product Manager (AliExpress & Amazon)."""
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt, QTimer

from ui.main_window import MainWindow
from ui.login_dialog import LoginDialog
from auth.service import get_auth_service, AccessRevokedError

try:
    from config import settings as config
except ImportError:
    config = None


class Application:
    """
    Main application class that handles authentication and session management.
    """
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.main_window = None
        self.session_timer = None
        self.auth_service = get_auth_service()
        
        self._setup_app()
    
    def _setup_app(self):
        """Configure application properties and styling."""
        # Set application properties
        self.app.setApplicationName("电商产品管理器")
        self.app.setOrganizationName("电商爬虫")
        
        # Force light mode - don't follow system dark mode
        self.app.setStyle("Fusion")
        
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
        
        self.app.setPalette(light_palette)
    
    def _show_login_dialog(self) -> bool:
        """
        Show the login dialog and wait for authentication.
        
        Returns:
            True if login succeeded, False otherwise
        """
        login_dialog = LoginDialog()
        result = login_dialog.exec()
        
        # QDialog.Accepted means login was successful
        return result == LoginDialog.Accepted
    
    def _start_session_validation_timer(self):
        """
        Start a timer to validate the session every 5 minutes.
        If validation fails, show a message and exit the app.
        """
        # Get interval from config (default: 5 minutes = 300,000 ms)
        interval_ms = getattr(config, 'SESSION_VALIDATION_INTERVAL_MS', 300000) if config else 300000
        
        self.session_timer = QTimer()
        self.session_timer.timeout.connect(self._validate_session)
        self.session_timer.start(interval_ms)
    
    def _validate_session(self):
        """
        Validate the current session.
        If validation fails due to explicit revocation, show message and exit.
        For other failures (network issues, etc.), just log and continue.
        """
        try:
            is_valid = self.auth_service.validate_session()
            
            if not is_valid:
                # Try to refresh the tokens
                try:
                    self.auth_service.refresh_tokens()
                    # After refresh, validate again
                    is_valid = self.auth_service.validate_session()
                except AccessRevokedError:
                    # Only exit on explicit revocation
                    self._handle_access_revoked()
                    return
                except Exception as e:
                    # Network issues, token errors, etc. - don't exit
                    print(f"Token refresh failed (will retry): {e}")
                    return
            
            # Only handle revocation on explicit AccessRevokedError, not on general validation failure
            # Transient failures should not cause app exit
                
        except AccessRevokedError:
            self._handle_access_revoked()
        except Exception as e:
            # Log the error but don't exit for transient network issues
            print(f"Session validation error: {e}")
    
    def _handle_access_revoked(self):
        """Handle access revocation by showing a message and exiting."""
        # Stop the timer
        if self.session_timer:
            self.session_timer.stop()
        
        # Show message box
        QMessageBox.critical(
            self.main_window,
            "访问已撤销",
            "Your access has been revoked. 您的访问权限已被撤销。\n\n应用程序将立即退出。",
            QMessageBox.Ok
        )
        
        # Logout and exit
        self.auth_service.logout()
        self.app.quit()
        sys.exit(1)
    
    def run(self) -> int:
        """
        Run the application.
        
        Returns:
            Exit code
        """
        # Show login dialog first
        if not self._show_login_dialog():
            # User cancelled or login failed
            return 0
        
        # Create and show main window after successful login
        self.main_window = MainWindow()
        self.main_window.show()
        
        # Start session validation timer
        self._start_session_validation_timer()
        
        # Connect to aboutToQuit to ensure cleanup
        self.app.aboutToQuit.connect(self._cleanup_on_exit)
        
        # Run event loop
        return self.app.exec()
    
    def _cleanup_on_exit(self):
        """Clean up resources when application is about to quit."""
        print("DEBUG: Application about to quit, cleaning up threads...")
        if self.main_window:
            # Clean up all image loader threads first
            if hasattr(self.main_window, '_cleanup_all_image_loader_threads'):
                try:
                    self.main_window._cleanup_all_image_loader_threads()
                except Exception as e:
                    print(f"DEBUG: Error cleaning up image loader threads: {e}")
            
            # Ensure scraper thread is cleaned up
            if hasattr(self.main_window, 'scraper_thread') and self.main_window.scraper_thread:
                thread = self.main_window.scraper_thread
                if thread.isRunning():
                    print(f"DEBUG: Scraper thread is still running, cleaning up...")
                    try:
                        thread.stop()
                        if not thread.wait(2000):  # Wait 2 seconds
                            print("DEBUG: Scraper thread didn't stop, terminating...")
                            thread.terminate()
                            thread.wait(1000)
                    except Exception as e:
                        print(f"DEBUG: Error cleaning up scraper thread: {e}")
        
        # Process events to allow cleanup to complete
        try:
            from PySide6.QtCore import QCoreApplication
            app = QCoreApplication.instance()
            if app:
                print("DEBUG: Processing events to allow thread cleanup...")
                app.processEvents()
                # Give threads a moment to finish
                import time
                time.sleep(0.1)
                app.processEvents()
        except Exception as e:
            print(f"DEBUG: Error processing events: {e}")
        
        print("DEBUG: Thread cleanup complete.")


def main():
    """Launch the application."""
    application = Application()
    sys.exit(application.run())


if __name__ == "__main__":
    main()

