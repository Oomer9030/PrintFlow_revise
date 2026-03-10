from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QFrame)
from PyQt6.QtCore import Qt
import sys

class LoginDialog(QDialog):
    def __init__(self, users_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PrintFlow Login Gateway")
        self.users_data = users_data or []
        self.authorized_user = None
        
        # Extract unique departments (roles)
        self.departments = sorted(list(set(u.get("role", "Viewer") for u in self.users_data)))
        if "Pre-Press Dep." not in self.departments:
            self.departments.append("Pre-Press Dep.")
        self.departments = sorted(self.departments)
            
        self.init_ui()
        if not parent:
            self.center_on_screen()

    def center_on_screen(self):
        screen = self.screen().availableGeometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2)

    def init_ui(self):
        self.setFixedSize(400, 520)
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; }
            QLabel { color: #94a3b8; font-weight: bold; font-size: 11px; }
            QLineEdit, QComboBox {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #f1f5f9;
                padding: 10px;
                font-size: 13px;
            }
            QComboBox::drop-down { border: none; }
            QPushButton {
                background-color: #38bdf8;
                color: #0f172a;
                border: none;
                border-radius: 6px;
                padding: 12px;
                font-weight: 800;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #7dd3fc; }
            #Title { color: #38bdf8; font-size: 22px; font-weight: 900; }
            #Error { color: #f43f5e; font-size: 11px; font-weight: bold; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)
        
        title = QLabel("PRINTFLOW PRO")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("SECURE PRODUCTION ACCESS")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        
        layout.addSpacing(15)
        
        # 1. Department Selection
        layout.addWidget(QLabel("SELECT DEPARTMENT"))
        self.dept_combo = QComboBox()
        self.dept_combo.addItems(self.departments)
        self.dept_combo.currentTextChanged.connect(self.update_user_list)
        layout.addWidget(self.dept_combo)
        
        # 2. Name Selection
        layout.addWidget(QLabel("SELECT USER IDENTITY"))
        self.user_combo = QComboBox()
        layout.addWidget(self.user_combo)
        
        # 3. Password Input
        layout.addWidget(QLabel("ACCESS KEY (PASSWORD)"))
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setPlaceholderText("••••••••")
        self.pass_input.returnPressed.connect(self.handle_login)
        layout.addWidget(self.pass_input)
        
        self.error_label = QLabel("")
        self.error_label.setObjectName("Error")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_label)
        
        layout.addStretch()
        
        login_btn = QPushButton("AUTHORIZE ACCESS")
        login_btn.clicked.connect(self.handle_login)
        layout.addWidget(login_btn)

        # Initialize user list based on first department
        self.update_user_list(self.dept_combo.currentText())

    def update_user_list(self, department):
        """Filters the user name list based on selected department."""
        self.user_combo.clear()
        filtered_users = [u["name"] for u in self.users_data if u.get("role") == department]
        if not filtered_users:
            # Fallback if no users in that role
            filtered_users = ["No users in this dept"]
        self.user_combo.addItems(filtered_users)

    def handle_login(self):
        dept = self.dept_combo.currentText()
        user_name = self.user_combo.currentText()
        password = self.pass_input.text()
        
        target_user = next((u for u in self.users_data if u["name"] == user_name and u.get("role") == dept), None)
        
        if target_user and target_user.get("password") == password:
            self.authorized_user = target_user
            self.accept()
        else:
            self.error_label.setText("INVALID ACCESS KEY. ACCESS DENIED.")
            self.pass_input.clear()
            self.pass_input.setFocus()
