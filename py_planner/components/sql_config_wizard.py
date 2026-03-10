from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFrame, QMessageBox, QGridLayout)
from PyQt6.QtCore import Qt, pyqtSlot
import json
import os

class SQLConfigWizard(QDialog):
    def __init__(self, data_file, current_settings=None, parent=None, is_floor_view=False):
        super().__init__(parent)
        self.data_file = data_file
        self.settings = current_settings or {}
        self.sql_config = self.settings.get("sqlConfig", {})
        self.is_floor_view = is_floor_view
        
        self.setWindowTitle("PrintFlow Engine - First Time Setup")
        self.setFixedSize(450, 550)
        self.init_ui()
        self.center_on_screen()

    def center_on_screen(self):
        screen = self.screen().availableGeometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2)

    def init_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #0f172a; }
            QLabel { color: #94a3b8; font-weight: bold; font-size: 11px; }
            QLineEdit {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                color: #f1f5f9;
                padding: 10px;
                font-size: 13px;
            }
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
            #Title { color: #38bdf8; font-size: 20px; font-weight: 900; }
            #Subtitle { color: #64748b; font-size: 11px; font-weight: bold; margin-bottom: 10px; }
            #TestBtn { background-color: #1e293b; border: 1px solid #10b981; color: #10b981; }
            #TestBtn:hover { background-color: #064e3b; }
        """)
        if self.is_floor_view:
            self.setWindowTitle("API CONNECTION CONFIGURATION")
            title_text = "CONNECT TO MAIN PLANNER API"
            subtitle_text = "Enter the Listening IP of the Main Planner workstation"
        else:
            self.setWindowTitle("SQL SERVER INITIALIZATION")
            title_text = "CONNECT TO SQL SERVER"
            subtitle_text = "Enter the direct SQL Server connection details"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(15)
        
        title = QLabel(title_text)
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #38bdf8;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel(subtitle_text)
        subtitle.setStyleSheet("color: #94a3b8; margin-bottom: 20px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        
        layout.addSpacing(10)
        
        form = QGridLayout()
        form.setSpacing(10)
        
        if self.is_floor_view:
            form.addWidget(QLabel("MAIN APP IP / LISTENING IP"), 0, 0)
            self.server_in = QLineEdit(self.sql_config.get("server", ""))
            self.server_in.setPlaceholderText("e.g., 192.168.1.100")
            form.addWidget(self.server_in, 0, 1)
            
            form.addWidget(QLabel("API SERVER PORT"), 1, 0)
            self.port_in = QLineEdit(str(self.sql_config.get("port", "8000")))
            self.port_in.setPlaceholderText("Default: 8000")
            form.addWidget(self.port_in, 1, 1)
            
            # Dummy fields to avoid crashing in handlers
            self.db_in = QLineEdit("API_MODE")
            self.user_in = QLineEdit("")
            self.pass_in = QLineEdit("")
        else:
            form.addWidget(QLabel("SQL SERVER ADDRESS"), 0, 0)
            self.server_in = QLineEdit(self.sql_config.get("server", ""))
            self.server_in.setPlaceholderText("e.g., SERVER_NAME or IP")
            form.addWidget(self.server_in, 0, 1)
            
            form.addWidget(QLabel("SQL PORT"), 1, 0)
            self.port_in = QLineEdit(str(self.sql_config.get("port", "1433")))
            self.port_in.setPlaceholderText("Default: 1433")
            form.addWidget(self.port_in, 1, 1)

            form.addWidget(QLabel("DATABASE NAME"), 2, 0)
            self.db_in = QLineEdit(self.sql_config.get("database", ""))
            self.db_in.setPlaceholderText("e.g., PrintFlow_DB")
            form.addWidget(self.db_in, 2, 1)
            
            form.addWidget(QLabel("USER ID (e.g. awol_reporting)"), 3, 0)
            self.user_in = QLineEdit(self.sql_config.get("user", ""))
            self.user_in.setPlaceholderText("SQL Username")
            form.addWidget(self.user_in, 3, 1)
            
            form.addWidget(QLabel("PASSWORD"), 4, 0)
            self.pass_in = QLineEdit(self.sql_config.get("password", ""))
            self.pass_in.setPlaceholderText("••••••••")
            self.pass_in.setEchoMode(QLineEdit.EchoMode.Password)
            form.addWidget(self.pass_in, 4, 1)
        
        layout.addLayout(form)
        
        layout.addSpacing(20)
        
        self.test_btn = QPushButton("TEST CONNECTION")
        self.test_btn.setObjectName("TestBtn")
        self.test_btn.clicked.connect(self.handle_test)
        layout.addWidget(self.test_btn)
        
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        local_btn = QPushButton("USE LOCAL ONLY (OFFLINE)")
        local_btn.setStyleSheet("background-color: #334155; color: white; padding: 12px; font-weight: 800;")
        local_btn.clicked.connect(self.handle_local_only)
        
        save_btn = QPushButton("SAVE & PROCEED")
        save_btn.clicked.connect(self.handle_save)
        
        btn_layout.addWidget(local_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def handle_local_only(self):
        # Explicitly set sqlConfig to empty or marked as offline
        if "appSettings" not in self.settings: self.settings["appSettings"] = {}
        self.settings["appSettings"]["sqlConfig"] = {"offline": True}
        self.settings["appSettings"]["sqlServer"] = None
        
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save local preference: {str(e)}")

    def handle_test(self):
        config = {
            "server": self.server_in.text().strip(),
            "port": self.port_in.text().strip() or "1433",
            "database": self.db_in.text().strip(),
            "user": self.user_in.text().strip(),
            "password": self.pass_in.text().strip()
        }
        
        self.test_btn.setEnabled(False)
        self.test_btn.setText("TESTING... PLEASE WAIT")

        import threading
        def run_async_test():
            try:
                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                if self.is_floor_view:
                    from floor_view.api import api_service
                    api_config = {"apiUrl": config["server"], "apiToken": ""}
                    if ":" not in api_config["apiUrl"] and config["port"]:
                        api_config["apiUrl"] = f"http://{config['server']}:{config['port']}"
                    elif "://" not in api_config["apiUrl"]:
                        api_config["apiUrl"] = f"http://{config['server']}"

                    success, msg = api_service.test_api_connection(api_config)
                    title, body = ("API Connection", f"SUCCESS! Connected to {api_config['apiUrl']}.") if success else ("API Connection", f"FAILED: {msg}")
                else:
                    from floor_view.api import sql_service
                    success, msg = sql_service.test_connection(config)
                    title, body = ("SQL Connection", "SUCCESS! SQL connection established.") if success else ("SQL Connection", f"FAILED: {msg}")
                
                QMetaObject.invokeMethod(self, "_on_test_finished", Qt.ConnectionType.QueuedConnection,
                                       Q_ARG(str, title), Q_ARG(str, body), Q_ARG(bool, success))
            except Exception as e:
                from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(self, "_on_test_finished", Qt.ConnectionType.QueuedConnection,
                                       Q_ARG(str, "System Error"), Q_ARG(str, str(e)), Q_ARG(bool, False))

        # Watchdog
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(15000, lambda: self.test_btn.setEnabled(True))
        QTimer.singleShot(15000, lambda: self.test_btn.setText("TEST CONNECTION"))

        threading.Thread(target=run_async_test, daemon=True).start()

    @pyqtSlot(str, str, bool)
    def _on_test_finished(self, title, body, success):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("TEST CONNECTION")
        if success: QMessageBox.information(self, title, body)
        else: QMessageBox.warning(self, title, body)

    def handle_save(self):
        config = {
            "server": self.server_in.text().strip(),
            "port": self.port_in.text().strip() or "1433",
            "database": self.db_in.text().strip(),
            "user": self.user_in.text().strip(),
            "password": self.pass_in.text().strip()
        }
        
        if self.is_floor_view:
            if not config["server"]:
                QMessageBox.warning(self, "Setup Error", "Main App IP is required.")
                return
        else:
            if not config["server"] or not config["database"]:
                QMessageBox.warning(self, "Setup Error", "Please provide SQL Server Address and Database Name.")
                return
            
        # Update settings
        if "appSettings" not in self.settings: self.settings["appSettings"] = {}
        
        if self.is_floor_view:
            self.settings["appSettings"]["apiConfig"] = config
        else:
            self.settings["appSettings"]["sqlConfig"] = config
            self.settings["appSettings"]["sqlServer"] = config["server"] # Backward compatibility duplicate
            
            # DEFAULT INITIALIZATION: Enable sync and export flags by default on new setups
            # This ensures individual row saves (granular_save) work without a trip to Settings.
            self.settings["appSettings"]["sqlExportEnabled"] = True
            self.settings["appSettings"]["sqlLiveSyncEnabled"] = True
            
            # Also update structured keys in the sqlConfig object itself
            config["export_enabled"] = True
            config["live_sync_enabled"] = True
            config["sync_source"] = "sql"
        
        # Save to file
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save configuration: {str(e)}")
