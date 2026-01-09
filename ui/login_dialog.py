"""
Login Dialog for AWS Cognito Authentication.
Includes password change dialog for NEW_PASSWORD_REQUIRED challenge.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame, QCheckBox, QWidget,
    QStackedWidget, QGraphicsDropShadowEffect, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QFontDatabase

from auth_service import (
    get_auth_service, AuthenticationError, AccessRevokedError,
    NewPasswordRequiredError, InvalidPasswordError
)


def create_chinese_font(point_size: int, bold: bool = False) -> QFont:
    """Create a font that properly renders Chinese characters on macOS."""
    # Try macOS Chinese fonts in order of preference
    font_families = ["PingFang SC", "Heiti SC", "Hiragino Sans GB", "STHeiti"]
    
    font = QFont()
    for family in font_families:
        font.setFamily(family)
        if QFontDatabase.hasFamily(family):
            break
    
    font.setPointSize(point_size)
    if bold:
        font.setBold(True)
    return font


class LoginDialog(QDialog):
    """
    Login dialog for user authentication.
    
    Shows a login form and handles authentication via AWS Cognito.
    Includes handling for NEW_PASSWORD_REQUIRED challenge.
    """
    
    login_successful = Signal(str)  # Emits username on successful login
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录 - 电商产品管理器")
        self.setFixedSize(480, 560)
        self.setModal(True)
        
        # Keep close button but handle it properly
        # User can close = exit app
        
        # Auth state
        self._pending_session = None
        self._pending_username = None
        
        # Auth service
        self.auth_service = get_auth_service()
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the UI with stacked pages for login and password change."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Background
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
            }
        """)
        
        # Stacked widget for login/password change views
        self.stacked = QStackedWidget()
        
        # Create login page
        login_page = self._create_login_page()
        self.stacked.addWidget(login_page)
        
        # Create password change page
        password_page = self._create_password_change_page()
        self.stacked.addWidget(password_page)
        
        main_layout.addWidget(self.stacked)
    
    def _create_login_page(self) -> QWidget:
        """Create the login page widget."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        
        # Card container
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 16px;
            }
        """)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 10)
        card.setGraphicsEffect(shadow)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)
        
        # Icon/Logo
        icon_label = QLabel("🛒")
        icon_font = QFont()
        icon_font.setPointSize(42)
        icon_label.setFont(icon_font)
        icon_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel("电商产品管理器")
        title_label.setFont(create_chinese_font(22, bold=True))
        title_label.setStyleSheet("color: #1a1a2e;")
        title_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title_label)
        
        card_layout.addSpacing(5)
        
        # Subtitle
        subtitle_label = QLabel("请登录您的账户")
        subtitle_label.setFont(create_chinese_font(14))
        subtitle_label.setStyleSheet("color: #666666;")
        subtitle_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle_label)
        
        card_layout.addSpacing(20)
        
        # Username field
        username_container = QVBoxLayout()
        username_container.setSpacing(8)
        
        username_label = QLabel("用户名")
        username_label.setFont(create_chinese_font(14, bold=True))
        username_label.setStyleSheet("color: #333;")
        username_container.addWidget(username_label)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入用户名或邮箱")
        self.username_input.setMinimumHeight(48)
        self.username_input.setFont(create_chinese_font(14))
        self.username_input.setStyleSheet("""
            QLineEdit {
                padding: 12px 16px;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                background-color: #fafafa;
                color: #333;
            }
            QLineEdit:focus {
                border-color: #667eea;
                background-color: white;
            }
        """)
        username_container.addWidget(self.username_input)
        card_layout.addLayout(username_container)
        
        # Password field
        password_container = QVBoxLayout()
        password_container.setSpacing(8)
        
        password_label = QLabel("密码")
        password_label.setFont(create_chinese_font(14, bold=True))
        password_label.setStyleSheet("color: #333;")
        password_container.addWidget(password_label)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(48)
        self.password_input.setFont(create_chinese_font(14))
        self.password_input.setStyleSheet("""
            QLineEdit {
                padding: 12px 16px;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                background-color: #fafafa;
                color: #333;
            }
            QLineEdit:focus {
                border-color: #667eea;
                background-color: white;
            }
        """)
        self.password_input.returnPressed.connect(self._on_login_clicked)
        password_container.addWidget(self.password_input)
        card_layout.addLayout(password_container)
        
        card_layout.addSpacing(10)
        
        # Login button
        self.login_btn = QPushButton("登 录")
        self.login_btn.setMinimumHeight(52)
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setFont(create_chinese_font(16, bold=True))
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a6fd6, stop:1 #6a4190);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4e5fc2, stop:1 #5e377e);
            }
            QPushButton:disabled {
                background: #cccccc;
            }
        """)
        self.login_btn.clicked.connect(self._on_login_clicked)
        card_layout.addWidget(self.login_btn)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setFont(create_chinese_font(13))
        self.status_label.setStyleSheet("""
            color: #e74c3c;
            padding: 10px;
            background-color: #ffeaea;
            border-radius: 8px;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        card_layout.addWidget(self.status_label)
        
        card_layout.addStretch()
        
        layout.addStretch()
        layout.addWidget(card)
        layout.addStretch()
        
        return page
    
    def _create_password_change_page(self) -> QWidget:
        """Create the password change page widget."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)
        
        # Card container
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 16px;
            }
        """)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 10)
        card.setGraphicsEffect(shadow)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)
        
        # Icon
        icon_label = QLabel("🔐")
        icon_font = QFont()
        icon_font.setPointSize(42)
        icon_label.setFont(icon_font)
        icon_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(icon_label)
        
        # Title
        title_label = QLabel("设置新密码")
        title_label.setFont(create_chinese_font(22, bold=True))
        title_label.setStyleSheet("color: #1a1a2e;")
        title_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title_label)
        
        card_layout.addSpacing(5)
        
        # Subtitle
        subtitle_label = QLabel("您需要设置一个新密码才能继续")
        subtitle_label.setFont(create_chinese_font(14))
        subtitle_label.setStyleSheet("color: #666666;")
        subtitle_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(subtitle_label)
        
        card_layout.addSpacing(10)
        
        # Password requirements hint
        hint_label = QLabel("密码要求: 至少8个字符, 包含大小写字母和数字")
        hint_label.setFont(create_chinese_font(12))
        hint_label.setStyleSheet("""
            color: #555;
            padding: 12px;
            background-color: #f0f4ff;
            border-radius: 8px;
        """)
        hint_label.setWordWrap(True)
        hint_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(hint_label)
        
        # New password field
        new_pw_container = QVBoxLayout()
        new_pw_container.setSpacing(8)
        
        new_pw_label = QLabel("新密码")
        new_pw_label.setFont(create_chinese_font(14, bold=True))
        new_pw_label.setStyleSheet("color: #333;")
        new_pw_container.addWidget(new_pw_label)
        
        self.new_password_input = QLineEdit()
        self.new_password_input.setPlaceholderText("请输入新密码")
        self.new_password_input.setEchoMode(QLineEdit.Password)
        self.new_password_input.setMinimumHeight(48)
        self.new_password_input.setFont(create_chinese_font(14))
        self.new_password_input.setStyleSheet("""
            QLineEdit {
                padding: 12px 16px;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                background-color: #fafafa;
                color: #333;
            }
            QLineEdit:focus {
                border-color: #667eea;
                background-color: white;
            }
        """)
        self.new_password_input.textChanged.connect(self._validate_password_strength)
        new_pw_container.addWidget(self.new_password_input)
        card_layout.addLayout(new_pw_container)
        
        # Confirm password field
        confirm_pw_container = QVBoxLayout()
        confirm_pw_container.setSpacing(8)
        
        confirm_pw_label = QLabel("确认密码")
        confirm_pw_label.setFont(create_chinese_font(14, bold=True))
        confirm_pw_label.setStyleSheet("color: #333;")
        confirm_pw_container.addWidget(confirm_pw_label)
        
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("请再次输入新密码")
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        self.confirm_password_input.setMinimumHeight(48)
        self.confirm_password_input.setFont(create_chinese_font(14))
        self.confirm_password_input.setStyleSheet("""
            QLineEdit {
                padding: 12px 16px;
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                background-color: #fafafa;
                color: #333;
            }
            QLineEdit:focus {
                border-color: #667eea;
                background-color: white;
            }
        """)
        self.confirm_password_input.returnPressed.connect(self._on_change_password_clicked)
        confirm_pw_container.addWidget(self.confirm_password_input)
        card_layout.addLayout(confirm_pw_container)
        
        # Password strength indicator
        self.strength_label = QLabel("")
        self.strength_label.setFont(create_chinese_font(13))
        self.strength_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.strength_label)
        
        card_layout.addSpacing(5)
        
        # Change password button
        self.change_pw_btn = QPushButton("确认修改")
        self.change_pw_btn.setMinimumHeight(52)
        self.change_pw_btn.setCursor(Qt.PointingHandCursor)
        self.change_pw_btn.setFont(create_chinese_font(16, bold=True))
        self.change_pw_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #11998e, stop:1 #38ef7d);
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0f8a80, stop:1 #32d970);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0d7b72, stop:1 #2cc463);
            }
            QPushButton:disabled {
                background: #cccccc;
            }
        """)
        self.change_pw_btn.clicked.connect(self._on_change_password_clicked)
        card_layout.addWidget(self.change_pw_btn)
        
        # Back button
        back_btn = QPushButton("← 返回登录")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setFont(create_chinese_font(14))
        back_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #667eea;
                border: none;
                padding: 10px;
            }
            QPushButton:hover {
                color: #5a6fd6;
            }
        """)
        back_btn.clicked.connect(self._go_back_to_login)
        card_layout.addWidget(back_btn)
        
        # Status label for password change
        self.pw_status_label = QLabel("")
        self.pw_status_label.setFont(create_chinese_font(13))
        self.pw_status_label.setStyleSheet("""
            color: #e74c3c;
            padding: 10px;
            background-color: #ffeaea;
            border-radius: 8px;
        """)
        self.pw_status_label.setAlignment(Qt.AlignCenter)
        self.pw_status_label.setWordWrap(True)
        self.pw_status_label.hide()
        card_layout.addWidget(self.pw_status_label)
        
        card_layout.addStretch()
        
        layout.addStretch()
        layout.addWidget(card)
        layout.addStretch()
        
        return page
    
    def _validate_password_strength(self, password: str):
        """Validate and display password strength."""
        if not password:
            self.strength_label.setText("")
            return
        
        issues = []
        if len(password) < 8:
            issues.append("至少8个字符")
        if not any(c.isupper() for c in password):
            issues.append("需要大写字母")
        if not any(c.islower() for c in password):
            issues.append("需要小写字母")
        if not any(c.isdigit() for c in password):
            issues.append("需要数字")
        
        if not issues:
            self.strength_label.setText("✅ 密码强度符合要求")
            self.strength_label.setStyleSheet("color: #27ae60;")
        else:
            self.strength_label.setText("❌ " + "、".join(issues))
            self.strength_label.setStyleSheet("color: #e74c3c;")
    
    def _show_status(self, label: QLabel, message: str, is_error: bool = True):
        """Show status message."""
        if is_error:
            label.setStyleSheet("""
                color: #e74c3c;
                padding: 10px;
                background-color: #ffeaea;
                border-radius: 8px;
            """)
        else:
            label.setStyleSheet("""
                color: #27ae60;
                padding: 10px;
                background-color: #eafff0;
                border-radius: 8px;
            """)
        label.setText(message)
        label.show()
    
    def _on_login_clicked(self):
        """Handle login button click."""
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        if not username:
            self._show_status(self.status_label, "请输入用户名")
            return
        
        if not password:
            self._show_status(self.status_label, "请输入密码")
            return
        
        # Disable button during login
        self.login_btn.setEnabled(False)
        self.login_btn.setText("登录中...")
        self.status_label.hide()
        
        try:
            # Attempt authentication
            result = self.auth_service.authenticate(username, password)
            
            # Login successful
            self.login_successful.emit(username)
            self.accept()
            
        except NewPasswordRequiredError as e:
            # Need to change password
            self._pending_session = e.session
            self._pending_username = e.username
            self.stacked.setCurrentIndex(1)  # Switch to password change page
            
        except AuthenticationError as e:
            self._show_status(self.status_label, str(e))
        except AccessRevokedError as e:
            self._show_status(self.status_label, str(e))
        except Exception as e:
            self._show_status(self.status_label, f"登录失败: {str(e)}")
        finally:
            self.login_btn.setEnabled(True)
            self.login_btn.setText("登 录")
    
    def _on_change_password_clicked(self):
        """Handle password change button click."""
        new_password = self.new_password_input.text()
        confirm_password = self.confirm_password_input.text()
        
        # Validate passwords match
        if new_password != confirm_password:
            self._show_status(self.pw_status_label, "两次输入的密码不一致")
            return
        
        # Validate password strength
        if len(new_password) < 8:
            self._show_status(self.pw_status_label, "密码长度至少8个字符")
            return
        
        if not any(c.isupper() for c in new_password):
            self._show_status(self.pw_status_label, "密码需要包含大写字母")
            return
        
        if not any(c.islower() for c in new_password):
            self._show_status(self.pw_status_label, "密码需要包含小写字母")
            return
        
        if not any(c.isdigit() for c in new_password):
            self._show_status(self.pw_status_label, "密码需要包含数字")
            return
        
        # Disable button during operation
        self.change_pw_btn.setEnabled(False)
        self.change_pw_btn.setText("设置中...")
        self.pw_status_label.hide()
        
        try:
            # Complete password change
            result = self.auth_service.complete_password_change(
                username=self._pending_username,
                new_password=new_password,
                session=self._pending_session
            )
            
            # Success!
            self._show_status(self.pw_status_label, "密码设置成功！", is_error=False)
            
            # Emit success and close
            self.login_successful.emit(self._pending_username)
            self.accept()
            
        except InvalidPasswordError as e:
            self._show_status(self.pw_status_label, str(e))
        except AuthenticationError as e:
            self._show_status(self.pw_status_label, str(e))
        except Exception as e:
            self._show_status(self.pw_status_label, f"设置密码失败: {str(e)}")
        finally:
            self.change_pw_btn.setEnabled(True)
            self.change_pw_btn.setText("确认修改")
    
    def _go_back_to_login(self):
        """Go back to login page."""
        self._pending_session = None
        self._pending_username = None
        self.new_password_input.clear()
        self.confirm_password_input.clear()
        self.pw_status_label.hide()
        self.strength_label.setText("")
        self.stacked.setCurrentIndex(0)
    
    def get_username(self) -> str:
        """Get the entered username."""
        return self.username_input.text().strip()
    
    def closeEvent(self, event):
        """Handle close event - exit app if not authenticated."""
        if not self.auth_service.is_authenticated():
            # User is closing without login - this will exit the app
            self.reject()
        event.accept()
