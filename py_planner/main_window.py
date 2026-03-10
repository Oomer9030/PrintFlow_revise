import sys
import os
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QFrame, QPushButton, QLabel, QStackedWidget, QFileDialog, QMessageBox,
                             QAbstractItemView)
from PyQt6.QtCore import Qt, QTimer, QMetaObject, Q_ARG, pyqtSlot
import threading
from py_planner.utils.styles import QSS_STYLES
from py_planner.utils.planner_utils import load_planner_data, save_planner_data, PlannerLogic

from py_planner.components.planning_table import PlanningBoard
from py_planner.components.all_records import AllRecordsView
from py_planner.components.settings_view import SettingsView
from py_planner.components.about_view import AboutView
from py_planner.components.summary_report_view import SummaryReportView
from py_planner.components.login_dialog import LoginDialog
from py_planner.utils.pdf_generator import PDFGenerator
import shutil

class MainWindow(QMainWindow):
    def __init__(self, current_user=None, data_container=None):
        super().__init__()
        self.setWindowTitle("PrintFlow Pro - AI Production Planner")
        self.setMinimumSize(1280, 800)
        self.data_container = data_container
        
        # 1. Setup APPDATA path for writable data
        appdata_root = os.path.join(os.environ["APPDATA"], "ProductionPlanning")
        if not os.path.exists(appdata_root):
            os.makedirs(appdata_root, exist_ok=True)

        # 2. Handle default file template
        default_file_template = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_planning_100_jobs.json")
        default_file_appdata = os.path.join(appdata_root, "test_planning_100_jobs.json")
        
        # Copy template to APPDATA if it doesn't exist there
        if not os.path.exists(default_file_appdata) and os.path.exists(default_file_template):
            try:
                shutil.copy2(default_file_template, default_file_appdata)
            except Exception as e:
                print(f"Failed to copy template: {e}")

        # 3. Load initial settings from APPDATA version if possible
        load_path = default_file_appdata if os.path.exists(default_file_appdata) else default_file_template
        
        # PRIORITIZE IN-MEMORY DATA (e.g. Injected SQL Users from run_app.py)
        if self.data_container and self.data_container.get("current"):
            self.data = self.data_container["current"]
            self.data_file = load_path # Default to this as fallback path
            print(f"MAIN WINDOW: Resuming session with in-memory data (Users: {len(self.data.get('appSettings', {}).get('users', []))})")
        else:
            initial_data = load_planner_data(load_path)
            initial_settings = initial_data.get("appSettings", {})
            
            # 4. Resolve final data path
            saved_path = initial_settings.get("dataPath")
            if saved_path and os.path.exists(saved_path):
                self.data_file = saved_path
                self.data = load_planner_data(self.data_file)
            else:
                self.data_file = default_file_appdata
                self.data = initial_data
                if "appSettings" not in self.data: self.data["appSettings"] = {}
                self.data["appSettings"]["dataPath"] = self.data_file

            # Sync container if it exists
            if self.data_container: self.data_container["current"] = self.data

        # 4b. SQL-Primary Load Attempt
        sql_config = self.data.get("appSettings", {}).get("sqlConfig", {})
        if sql_config.get("server"):
            try:
                from floor_view.api import sql_service
                sql_data = sql_service.load_full_plan_from_sql(sql_config)
                if sql_data:
                    print("SQL PRIMARY: Successfully loaded plan from database.")
                    # IMPORTANT: Preserve the current active sql_config!
                    local_settings = json.loads(json.dumps(self.data.get("appSettings", {})))
                    
                    # IN-PLACE UPDATE to keep references in child views valid
                    self.data.clear()
                    self.data.update(sql_data)
                    
                    if "appSettings" not in self.data: self.data["appSettings"] = {}
                    
                    # Merge local settings carefully - keep the SQL config that brought us here
                    if not self.data.get("appSettings", {}).get("sqlConfig", {}).get("server"):
                         self.data["appSettings"]["sqlConfig"] = sql_config
                    
                    for k, v in local_settings.items():
                        if k == "sqlConfig" and not v: continue
                        self.data["appSettings"][k] = v
                else:
                    print("SQL PRIMARY: Database is empty or unreachable. Using local JSON.")
            except Exception as e:
                print(f"SQL PRIMARY ERROR: {e}")

        self.normalize_sql_config()

        self.logic = PlannerLogic(self.data.get("appSettings", {}))
        
        # 5. User Login Session (Now handled externally in run_app.py)
        self.current_user = current_user or {"name": "Anonymous", "role": "Guest"}
        self.is_logging_out = False
        
        # Sync container again after normalization
        if self.data_container: self.data_container["current"] = self.data

        self.init_ui()
        self.setStyleSheet(QSS_STYLES)
        
        # 6. Performance: Debounce Timer for SQL Sync
        self.sql_sync_timer = QTimer()
        self.sql_sync_timer.setSingleShot(True)
        self.sql_sync_timer.timeout.connect(self._run_background_sql_sync)
        self._is_syncing = False
        
        # 7. Live Synchronization Timer (Checks SQL for updates every 15 seconds)
        self.last_sync_timestamp = None
        self.live_sync_timer = QTimer()
        self.live_sync_timer.timeout.connect(self._check_for_live_updates)
        self.live_sync_timer.start(15000) # 15 seconds

    def normalize_sql_config(self):
        """Ensures legacy flat SQL keys are synced into the structured sqlConfig object."""
        if "appSettings" not in self.data: self.data["appSettings"] = {}
        settings = self.data["appSettings"]
        
        if "sqlConfig" not in settings: settings["sqlConfig"] = {}
        sc = settings["sqlConfig"]
        
        # List of legacy keys and their modern equivalents
        mapping = {
            "sqlServer": "server",
            "sqlDatabase": "database",
            "sqlUser": "user",
            "sqlPassword": "password",
            "sqlTableView": "table",
            "sqlStatusView": "status_view",
            "sqlStatusInterval": "status_interval",
            "sqlExportEnabled": "export_enabled",
            "sqlLiveSyncEnabled": "live_sync_enabled",
            "syncSource": "sync_source",
            "apiEnabled": "api_enabled",
            "apiUrl": "api_url",
            "apiToken": "api_token",
            "apiInterval": "api_interval"
        }
        
        # Sync: Legacy -> Modern (If modern is missing)
        for legacy_key, modern_key in mapping.items():
            if legacy_key in settings and not sc.get(modern_key):
                sc[modern_key] = settings[legacy_key]
        
        # Reverse Sync: Modern -> Legacy (For backward compatibility in components)
        for legacy_key, modern_key in mapping.items():
            if sc.get(modern_key):
                settings[legacy_key] = sc[modern_key]

        if sc.get("server"):
            if sc.get("export_enabled") is not True:
                sc["export_enabled"] = True
                settings["sqlExportEnabled"] = True
                print("SQL NORMALIZATION: Force-enabled sqlExportEnabled (Mirror to SQL)")
        
        # 5. Terminal Feedback
        mode = sc.get("sync_source", "sql").upper()
        print(f"--- INTEGRATION SETTINGS NORMALIZED ---")
        print(f"ACTIVE MODE: {mode}")
        if mode == "API":
            print(f"API ENDPOINT: {sc.get('api_url')}")
        else:
            print(f"SQL SERVER: {sc.get('server')}")
        print(f"----------------------------------------")
        
        # 6. Initialize Sync API (Now started early in run_app.py)
        # self.api_thread = start_api_server(lambda: self.data, port=api_port)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Top Navigation Bar
        self.top_nav = QFrame()
        self.top_nav.setObjectName("TopNav")
        top_nav_layout = QHBoxLayout(self.top_nav)
        top_nav_layout.setContentsMargins(25, 10, 25, 0)
        top_nav_layout.setSpacing(2)
        
        # Brand
        brand_label = QLabel("PRINTFLOW PRO")
        brand_label.setStyleSheet("font-size: 16px; font-weight: 800; color: #38bdf8; margin-right: 20px;")
        top_nav_layout.addWidget(brand_label)
        
        # Tab System
        self.tab_container = QWidget()
        tab_layout = QHBoxLayout(self.tab_container)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        
        self.nav_btns = {}
        full_nav_info = [
            ("PLANNER", "planner"),
            ("FINISHING", "finishing"),
            ("PACKING", "packing"),
            ("DELIVERY", "delivery"),
            ("RECORDS", "records"),
            ("SUMMARY", "summary"),
            ("SETTINGS", "settings"),
            ("ABOUT", "about")
        ]
        
        # Filter tabs based on role and permissions
        user_perms = str(self.current_user.get("permissions", "")).lower().split(",")
        is_admin = self.current_user.get("role") == "Administrator"
        
        nav_info = []
        user_role = str(self.current_user.get("role", "")).lower()
        is_admin = user_role == "administrator"
        is_viewer = user_role == "viewer"
        
        for name, key in full_nav_info:
            # Admins see everything
            if is_admin:
                nav_info.append((name, key))
            # Viewers see exactly what's in their perms list
            elif is_viewer:
                if key in user_perms:
                    nav_info.append((name, key))
            # Others (Planners) see what's in their perms list
            elif key in user_perms:
                nav_info.append((name, key))
        
        for name, key in nav_info:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("TabItem")
            btn.clicked.connect(lambda checked, k=key: self.switch_view(k))
            tab_layout.addWidget(btn)
            self.nav_btns[key] = btn
        
        top_nav_layout.addWidget(self.tab_container)
        top_nav_layout.addStretch()
        
        # Global Actions (Export)
        export_btn = QPushButton("EXPORT PDF")
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(56, 189, 248, 0.1);
                border: 1px solid #38bdf8;
                color: #38bdf8;
                padding: 6px 15px;
                border-radius: 6px;
                font-weight: 800;
                font-size: 10px;
                margin-bottom: 5px;
            }
            QPushButton:hover { background-color: #38bdf8; color: #1e1e1e; }
        """)
        export_btn.clicked.connect(self.export_report)
        top_nav_layout.addWidget(export_btn)
        
        # Logout Action
        logout_btn = QPushButton("LOGOUT")
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #f43f5e;
                color: #f43f5e;
                padding: 6px 15px;
                border-radius: 6px;
                font-weight: 800;
                font-size: 10px;
                margin-left: 10px;
                margin-bottom: 5px;
            }
            QPushButton:hover { background-color: #f43f5e; color: #ffffff; }
        """)
        logout_btn.clicked.connect(self.logout)
        top_nav_layout.addWidget(logout_btn)
        
        self.main_layout.addWidget(self.top_nav)
        
        # Content Area
        self.content_stack = QStackedWidget()
        self.main_layout.addWidget(self.content_stack)
        
        self.refresh_all_views()
        self.switch_view("planner")
        
        # Status Footer
        self.footer = QFrame()
        self.footer.setObjectName("StatusFooter")
        self.footer.setStyleSheet("""
            QFrame#StatusFooter { 
                background: #111122; 
                border-top: 1px solid #232a4e; 
                max-height: 25px;
            }
        """)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(20, 0, 20, 0)
        
        user_label = QLabel(f"● SESSION: {self.current_user['name'].upper()} ({self.current_user['role'].upper()})")
        user_label.setStyleSheet("color: #38bdf8; font-weight: 800; font-size: 9px;")
        footer_layout.addWidget(user_label)
        footer_layout.addStretch()
        
        version_label = QLabel("PRINTFLOW ENGINE v3.8.0")
        version_label.setStyleSheet("color: #475569; font-weight: 700; font-size: 9px;")
        footer_layout.addWidget(version_label)
        
        self.main_layout.addWidget(self.footer)

    def refresh_all_views(self):
        # Clear existing
        while self.content_stack.count() > 0:
            widget = self.content_stack.widget(0)
            self.content_stack.removeWidget(widget)
            widget.deleteLater()
            
        # Initialize Logic again with current settings
        self.logic = PlannerLogic(self.data.get("appSettings", {}))
            
        # Initialize Views
        # Determine initial machine for Production category
        production_machines = [n for n, d in self.data.get("machines", {}).items() if d.get("category", "production") == "production"]
        initial_production = production_machines[0] if production_machines else "MACHINE 1"
        
        self.planning_view = PlanningBoard(self.data.get("machines", {}),
                                          initial_production,
                                          self.logic,
                                          self.data.get("appSettings", {}),
                                          self.current_user,
                                          save_callback=self.persist_all_data,
                                          filter_category="production")
        
        # Determine initial machine for Finishing category
        finishing_machines = [n for n, d in self.data.get("machines", {}).items() if d.get("category") == "finishing"]
        initial_finishing = finishing_machines[0] if finishing_machines else "FINISHING 1"
        
        self.finishing_view = PlanningBoard(self.data.get("machines", {}),
                                           initial_finishing,
                                           self.logic,
                                           self.data.get("appSettings", {}),
                                           self.current_user,
                                           save_callback=self.persist_all_data,
                                           filter_category="finishing")

        # Determine initial machine for Packing category
        packing_machines = [n for n, d in self.data.get("machines", {}).items() if d.get("category") == "packing"]
        initial_packing = packing_machines[0] if packing_machines else "PACKING 1"
        
        self.packing_view = PlanningBoard(self.data.get("machines", {}),
                                         initial_packing,
                                         self.logic,
                                         self.data.get("appSettings", {}),
                                         self.current_user,
                                         save_callback=self.persist_all_data,
                                         filter_category="packing")
        
        # Determine initial machine for Delivery category
        delivery_machines = [n for n, d in self.data.get("machines", {}).items() if d.get("category") == "delivery"]
        initial_delivery = delivery_machines[0] if delivery_machines else "DELIVERY 1"
        
        self.delivery_view = PlanningBoard(self.data.get("machines", {}),
                                          initial_delivery,
                                          self.logic,
                                          self.data.get("appSettings", {}),
                                          self.current_user,
                                          save_callback=self.persist_all_data,
                                          filter_category="delivery")

        self.records_view = AllRecordsView(self.data)
        
        # KPI Dashboards REMOVED
        
        self.settings_view = SettingsView(
            self.data.get("appSettings", {}), 
            self.data.get("machines", {}),
            self.on_settings_saved,
            self.on_save_planning,
            self.on_load_planning,
            current_user=self.current_user
        )
        self.summary_view = SummaryReportView(self.data)
        self.about_view = AboutView()
        
        # Stack Order
        self.content_stack.addWidget(self.planning_view)    # 0 -> planner
        self.content_stack.addWidget(self.finishing_view)   # 1 -> finishing
        self.content_stack.addWidget(self.packing_view)     # 2 -> packing
        self.content_stack.addWidget(self.delivery_view)    # 3 -> delivery
        self.content_stack.addWidget(self.records_view)     # 4 -> records
        self.content_stack.addWidget(self.summary_view)     # 5 -> summary
        self.content_stack.addWidget(self.settings_view)    # 6 -> settings
        self.content_stack.addWidget(self.about_view)       # 7 -> about

    def switch_view(self, view_key):
        # Safety check: if view_key no longer available (due to perm change), switch to first available
        if view_key not in self.nav_btns:
            if self.nav_btns:
                view_key = list(self.nav_btns.keys())[0]
            else:
                return

        mapping = {
            "planner": 0, "finishing": 1, "packing": 2, "delivery": 3, "records": 4, 
            "summary": 5, "settings": 6, "about": 7
        }
        
        # We need to find the correct index in the content_stack for the given view_key
        # Since we might have skipped some widgets in content_stack, we need a smarter mapping
        # OR better: content_stack indices remain fixed, but we just check if view_key is in nav_btns.
        
        if view_key in mapping:
            # Trigger refreshes for analytical views
            if view_key in ["planner", "finishing", "packing", "delivery"]:
                # Ensure the board is fresh when switching to it
                if hasattr(self, 'planning_view'): self.planning_view.refresh_table()
                if hasattr(self, 'finishing_view'): self.finishing_view.refresh_table()
                if hasattr(self, 'packing_view'): self.packing_view.refresh_table()
                if hasattr(self, 'delivery_view'): self.delivery_view.refresh_table()
            elif view_key == "records":
                self.records_view.refresh()
            elif view_key == "summary":
                self.summary_view.refresh()
            
            self.content_stack.setCurrentIndex(mapping[view_key])
            for k, btn in self.nav_btns.items():
                btn.setChecked(k == view_key)

    def persist_all_data(self):
        """Saves data to local JSON immediately and schedules a background SQL sync."""
        try:
            if not self.data_file: return
            
            # 1. Save to JSON (Immediate / Fast)
            save_planner_data(self.data_file, self.data)
            
            # 2. Schedule SQL Sync (Debounced 2 seconds)
            # This prevents UI hang by moving high-latency SQL operations to a background thread
            self.sql_sync_timer.start(2000) 
            
            # 3. Synchronize UI Boards (Local UI only, fast)
            if hasattr(self, 'planning_view') and self.planning_view:
                self.planning_view.refresh_table()
            if hasattr(self, 'finishing_view') and self.finishing_view:
                self.finishing_view.refresh_table()
        except Exception as e:
            print(f"PERSIST ERROR: {e}")

    def _run_background_sql_sync(self):
        """Logic to execute SQL sync in a non-blocking thread."""
        if self._is_syncing: return
        
        def sync_worker():
            self._is_syncing = True
            try:
                sql_config = self.data.get("appSettings", {}).get("sqlConfig", {})
                if sql_config.get("server"):
                    from floor_view.api import sql_service
                    # 1. App state/machines
                    sql_service.save_full_state_to_sql(self.data, sql_config)
                    # 2. Sync all jobs
                    sql_service.sync_planner_to_sql(self.data.get("machines", {}), sql_config)
                    # print("SQL BACKGROUND SYNC: Completed.")
            except Exception as e:
                print(f"SQL BACKGROUND SYNC ERROR: {e}")
            finally:
                self._is_syncing = False

        threading.Thread(target=sync_worker, daemon=True).start()

    def _check_for_live_updates(self):
        """Checks if another instance has updated the SQL data."""
        if self._is_syncing: return
        
        # Edit Protection: If any board is currently being edited, skip this polling cycle
        if hasattr(self, 'planning_view') and self.planning_view and self._is_board_busy(self.planning_view): return
        if hasattr(self, 'finishing_view') and self.finishing_view and self._is_board_busy(self.finishing_view): return
        
        def check_worker():
            try:
                sql_config = self.data.get("appSettings", {}).get("sqlConfig", {})
                if sql_config.get("server"):
                    from floor_view.api import sql_service
                    new_ts = sql_service.get_last_global_change(sql_config)
                    if new_ts and new_ts != self.last_sync_timestamp:
                        print(f"LIVE SYNC: Change detected ({new_ts}). Reloading...")
                        self.reload_from_sql()
                        self.last_sync_timestamp = new_ts
                    elif not self.last_sync_timestamp:
                        self.last_sync_timestamp = new_ts
            except Exception as e:
                print(f"LIVE SYNC CHECK ERROR: {e}")

        threading.Thread(target=check_worker, daemon=True).start()

    def _is_board_busy(self, board):
        """Returns True if the user is currently editing a cell on the board."""
        try:
            if board.table.state() == QAbstractItemView.State.EditingState: return True
            if board.frozen_table.state() == QAbstractItemView.State.EditingState: return True
            return False
        except: return False

    def reload_from_sql(self):
        """Soft-reloads data from SQL and refreshes the UI without a full rebuild if possible."""
        def reload_worker():
            try:
                sql_config = self.data.get("appSettings", {}).get("sqlConfig", {})
                from floor_view.api import sql_service
                new_data = sql_service.load_full_plan_from_sql(sql_config)
                if new_data:
                    # In-place update to maintain object references
                    # We preserve appSettings and machinesMetadata to keep local state
                    local_settings = json.loads(json.dumps(self.data.get("appSettings", {})))
                    
                    # Update data on UI thread
                    QMetaObject.invokeMethod(self, "_apply_live_update", 
                                          Qt.ConnectionType.QueuedConnection,
                                          Q_ARG(dict, new_data),
                                          Q_ARG(dict, local_settings))
            except Exception as e:
                print(f"LIVE SYNC RELOAD ERROR: {e}")

        threading.Thread(target=reload_worker, daemon=True).start()

    @pyqtSlot(dict, dict)
    def _apply_live_update(self, new_data, local_settings):
        """Safely applies the reloaded SQL data to the live application."""
        try:
            # Preserve current machines reference to avoid breakage in child views
            self.data.clear()
            self.data.update(new_data)
            
            # Restore local settings (columns config, zoom, etc.)
            for k, v in local_settings.items():
                self.data["appSettings"][k] = v
                
            # Perform a soft refresh on all boards
            if hasattr(self, 'planning_view'): self.planning_view.refresh_table()
            if hasattr(self, 'finishing_view'): self.finishing_view.refresh_table()
            if hasattr(self, 'packing_view'): self.packing_view.refresh_table()
            if hasattr(self, 'delivery_view'): self.delivery_view.refresh_table()
            if hasattr(self, 'records_view'): self.records_view.refresh()
            print("LIVE SYNC: UI Refreshed.")
        except Exception as e:
            print(f"LIVE SYNC APPLY ERROR: {e}")

    def on_settings_saved(self, new_settings):
        self.data["appSettings"] = new_settings
        self.normalize_sql_config()
        self.persist_all_data()
        QMessageBox.information(self, "Success", "Configuration updated and logic recalculated.")
        self.refresh_all_views()
        self.switch_view("settings")

    def on_save_planning(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Planning Data", "Production_Plan.json", "JSON Files (*.json)")
        if path:
            try:
                save_planner_data(path, self.data)
                QMessageBox.information(self, "Success", f"Planning data exported to {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save data: {str(e)}")

    def on_load_planning(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Planning Data", "", "JSON Files (*.json)")
        if path:
            try:
                new_data = load_planner_data(path)
                self.data.clear()
                self.data.update(new_data)
                save_planner_data(self.data_file, self.data) # Persist as current data
                self.refresh_all_views()
                QMessageBox.information(self, "Success", f"Planning data imported from {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load data: {str(e)}")

    def export_report(self):
        current_widget = self.content_stack.currentWidget()
        path, _ = QFileDialog.getSaveFileName(self, "Export Report", "PrintFlow_Report.pdf", "PDF Files (*.pdf)")
        if path:
            success = PDFGenerator.export_widget_to_pdf(current_widget, path)
            if success:
                QMessageBox.information(self, "Success", f"Report exported to {path}")
            else:
                QMessageBox.critical(self, "Error", "Failed to generate PDF.")

    def logout(self):
        reply = QMessageBox.question(self, "Logout", "Are you sure you want to logout and switch user?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.is_logging_out = True
            self.close()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
