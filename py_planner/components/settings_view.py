from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
                             QLineEdit, QCheckBox, QPushButton, QGridLayout, QDateEdit, 
                             QListWidget, QScrollArea, QMessageBox, QFileDialog, QInputDialog,
                             QRadioButton, QButtonGroup, QComboBox)
from PyQt6.QtCore import Qt, QDate, pyqtSlot
import sys
import traceback

class SettingsView(QWidget):
    def __init__(self, settings, machines_data, save_callback, save_planning_cb, load_planning_cb, current_user=None):
        super().__init__()
        self.settings = settings
        self.machines_data = machines_data
        self.machine_names = list(machines_data.keys())
        self.save_callback = save_callback
        self.save_planning_cb = save_planning_cb
        self.load_planning_cb = load_planning_cb
        self.current_user = current_user or {"name": "Guest", "role": "Viewer"}
        self.init_ui()

    def init_ui(self):
        # Create a scroll area for the entire settings view
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #0f172a; }")
        
        container = QWidget()
        container.setStyleSheet("background-color: #0f172a;")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setSpacing(30)
        
        # Header Row
        header_layout = QHBoxLayout()
        header = QLabel("Application Engine Settings")
        header.setStyleSheet("font-size: 26px; font-weight: 800; color: #f8fafc;")
        header_layout.addWidget(header)
        header_layout.addStretch()
        
        save_btn = QPushButton("SAVE ALL CHANGES")
        save_btn.setObjectName("PrimaryAction")
        save_btn.setFixedHeight(45)
        save_btn.setFixedWidth(220)
        save_btn.clicked.connect(self.save_settings)
        header_layout.addWidget(save_btn)
        container_layout.addLayout(header_layout)
        
        # INTEGRATION MODE & SQL/API CONFIG REMOVED (NOW HARDCODED)
            
        
        # Grid for cards
        grid_layout = QGridLayout()
        grid_layout.setSpacing(30)
        
        # --- COLUMN 0: SYSTEM & OPERATIONAL ---
        
        # 1. CORE OPERATIONAL SETTINGS
        core_card = self._create_card("OPERATIONAL PARAMETERS", "#6366f1")
        core_layout = QGridLayout()
        core_layout.setSpacing(20)
        
        core_layout.addWidget(QLabel("Global Shift Hours (Default):"), 0, 0)
        self.shift_input = QLineEdit(str(self.settings.get("shiftHours", 8)))
        core_layout.addWidget(self.shift_input, 0, 1)
        
        core_layout.addWidget(QLabel("Weekly Working Cycle:"), 1, 0)
        days_layout = QHBoxLayout()
        self.day_checks = {}
        for i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            cb = QCheckBox(day)
            cb.setChecked((i + 1) in self.settings.get("workingDays", [1,2,3,4,5]))
            cb.setStyleSheet("color: #cbd5e1; font-size: 11px;")
            days_layout.addWidget(cb)
            self.day_checks[i+1] = cb
        core_layout.addLayout(days_layout, 1, 1)
        core_card.layout().addLayout(core_layout)
        grid_layout.addWidget(core_card, 0, 0)
        
        # 2. Public Holidays
        h_card = self._create_card("PUBLIC HOLIDAYS", "#f43f5e")
        self.holiday_list = QListWidget()
        self.holiday_list.setMaximumHeight(130)
        self.holiday_list.setStyleSheet("background: #0f172a; border-radius: 8px; padding: 5px;")
        self.holiday_list.addItems(self.settings.get("publicHolidays", []))
        h_card.layout().addWidget(self.holiday_list)
        
        h_ctrl = QHBoxLayout()
        self.h_date_input = QDateEdit(QDate.currentDate())
        self.h_date_input.setCalendarPopup(True)
        add_h = QPushButton("+ ADD")
        add_h.setStyleSheet("background: #1e293b; border: 1px solid #f43f5e; color: #f43f5e; padding: 5px;")
        add_h.clicked.connect(self.add_holiday)
        rem_h = QPushButton("- REMOVE")
        rem_h.setStyleSheet("background: #1e293b; border: 1px solid #475569; color: #94a3b8; padding: 5px;")
        rem_h.clicked.connect(self.remove_holiday)
        h_ctrl.addWidget(self.h_date_input)
        h_ctrl.addWidget(add_h)
        h_ctrl.addWidget(rem_h)
        h_card.layout().addLayout(h_ctrl)
        grid_layout.addWidget(h_card, 1, 0)
        
        # 3. Working Saturdays
        s_card = self._create_card("WORKING SATURDAYS", "#10b981")
        self.sat_list = QListWidget()
        self.sat_list.setMaximumHeight(130)
        self.sat_list.setStyleSheet("background: #0f172a; border-radius: 8px; padding: 5px;")
        self.sat_list.addItems(self.settings.get("workingSaturdays", []))
        s_card.layout().addWidget(self.sat_list)
        
        s_ctrl = QHBoxLayout()
        self.sat_date_input = QDateEdit(QDate.currentDate())
        self.sat_date_input.setCalendarPopup(True)
        add_s = QPushButton("+ ADD")
        add_s.setStyleSheet("background: #1e293b; border: 1px solid #10b981; color: #10b981; padding: 5px;")
        add_s.clicked.connect(self.add_working_sat)
        rem_s = QPushButton("- REMOVE")
        rem_s.setStyleSheet("background: #1e293b; border: 1px solid #475569; color: #94a3b8; padding: 5px;")
        rem_s.clicked.connect(self.remove_working_sat)
        s_ctrl.addWidget(self.sat_date_input)
        s_ctrl.addWidget(add_s)
        s_ctrl.addWidget(rem_s)
        s_card.layout().addLayout(s_ctrl)
        grid_layout.addWidget(s_card, 2, 0)
        
        # --- COLUMN 1: MANAGEMENT & DATA ---
        
        # 4. MACHINE MANAGEMENT (SHIFTS & CATEGORIES)
        shift_card = self._create_card("MACHINE MANAGEMENT", "#38bdf8")
        shift_scroll = QScrollArea()
        shift_scroll.setWidgetResizable(True)
        shift_scroll.setFixedHeight(180)
        shift_scroll.setStyleSheet("background: transparent; border: none;")
        
        shift_list_container = QWidget()
        shift_list_layout = QVBoxLayout(shift_list_container)
        shift_list_layout.setSpacing(10)
        
        machine_shifts = self.settings.get("machineShifts", {})
        default_shift = self.settings.get("shiftHours", 8)
        self.machine_shift_inputs = {}
        self.machine_category_inputs = {}
        
        for m_name in self.machine_names:
            m_row = QFrame()
            m_row.setStyleSheet("background: #1e293b; border-radius: 8px; border: 1px solid #334155;")
            row_layout = QHBoxLayout(m_row)
            row_layout.setContentsMargins(15, 8, 15, 8)
            
            lbl = QLabel(m_name)
            lbl.setStyleSheet("color: #f1f5f9; font-weight: bold; border: none;")
            
            inp = QLineEdit(str(machine_shifts.get(m_name, default_shift)))
            inp.setFixedWidth(50)
            inp.setAlignment(Qt.AlignmentFlag.AlignCenter)
            inp.setStyleSheet("background: #0f172a; color: #38bdf8; border: 1px solid #334155; font-weight: bold;")
            
            row_layout.addWidget(lbl)
            row_layout.addStretch()
            
            row_layout.addWidget(QLabel("Cat:"))
            cat_cb = QComboBox()
            cat_cb.addItems(["production", "finishing", "packing", "delivery"])
            current_cat = self.machines_data.get(m_name, {}).get("category", "production")
            cat_cb.setCurrentText(current_cat)
            cat_cb.setStyleSheet("background: #0f172a; color: #10b981; border: 1px solid #334155; padding: 2px;")
            row_layout.addWidget(cat_cb)
            
            row_layout.addSpacing(10)
            row_layout.addWidget(QLabel("Hrs:"))
            row_layout.addWidget(inp)
            shift_list_layout.addWidget(m_row)
            self.machine_shift_inputs[m_name] = inp
            self.machine_category_inputs[m_name] = cat_cb
            
        shift_scroll.setWidget(shift_list_container)
        shift_card.layout().addWidget(shift_scroll)
        grid_layout.addWidget(shift_card, 0, 1)
        
        # 5. DATA PERSISTENCE
        dm_card = self._create_card("DATA MANAGEMENT", "#fbbf24")
        dm_layout = QVBoxLayout()
        dm_layout.setSpacing(15)
        
        dm_layout.addWidget(QLabel("Primary Data Storage Path:"))
        path_row = QHBoxLayout()
        self.data_path_input = QLineEdit(self.settings.get("dataPath", "PrintFlow.json"))
        browse_btn = QPushButton("Browse")
        browse_btn.setStyleSheet("background: #0f172a; border: 1px solid #334155; padding: 5px;")
        browse_btn.clicked.connect(self.browse_data_path)
        path_row.addWidget(self.data_path_input)
        path_row.addWidget(browse_btn)
        dm_layout.addLayout(path_row)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        exp_btn = QPushButton("EXPORT DATA")
        exp_btn.setStyleSheet("background: #1e293b; border: 1px solid #38bdf8; color: #38bdf8; padding: 8px; font-size: 10px;")
        exp_btn.clicked.connect(self.save_planning_cb)
        imp_btn = QPushButton("IMPORT DATA")
        imp_btn.setStyleSheet("background: #1e293b; border: 1px solid #fbbf24; color: #fbbf24; padding: 8px; font-size: 10px;")
        imp_btn.clicked.connect(self.load_planning_cb)
        btn_layout.addWidget(exp_btn)
        btn_layout.addWidget(imp_btn)
        dm_layout.addLayout(btn_layout)

        # Storage Status
        is_sql = self.settings.get("sqlServer") is not None
        status_color = "#38bdf8" if is_sql else "#94a3b8"
        status_text = "SQL SERVER (PRIMARY)" if is_sql else "LOCAL JSON (OFFLINE FALLBACK)"
        status_label = QLabel(f"CURRENT STORAGE: {status_text}")
        status_label.setStyleSheet(f"color: {status_color}; font-size: 9px; font-weight: 800; margin-top: 5px;")
        dm_layout.addWidget(status_label)
        
        dm_card.layout().addLayout(dm_layout)
        grid_layout.addWidget(dm_card, 1, 1)
        
        # 6. USER MANAGEMENT (Admin Only)
        if self.current_user.get("role") == "Administrator":
            user_card = self._create_card("USER MANAGEMENT", "#a855f7")
            user_layout = QVBoxLayout()
            user_layout.setSpacing(10)
            
            self.user_list = QListWidget()
            self.user_list.setFixedHeight(120)
            self.user_list.setStyleSheet("background: #0f172a; border-radius: 8px; padding: 5px;")
            
            # Load initial users
            self.users = self.settings.get("users", [
                {"name": "Admin", "role": "Administrator", "password": "admin", "permissions": "planner,finishing,dashboard,records,efficiency,financial,strategic,settings,about"},
                {"name": "Planner", "role": "Planner", "password": "pass", "permissions": "planner,finishing,dashboard,records,efficiency,financial,strategic,about"}
            ])
            self.refresh_user_list()
            
            user_layout.addWidget(self.user_list)
            
            u_btn_layout = QHBoxLayout()
            add_u_btn = QPushButton("ADD NEW USER")
            add_u_btn.setStyleSheet("background: #1e293b; border: 1px solid #a855f7; color: #a855f7; font-size: 10px; padding: 8px;")
            add_u_btn.clicked.connect(lambda: self.add_user_dialog())
            
            edit_u_btn = QPushButton("EDIT USER")
            edit_u_btn.setStyleSheet("background: #1e293b; border: 1px solid #38bdf8; color: #38bdf8; font-size: 10px; padding: 8px;")
            edit_u_btn.clicked.connect(self.edit_user_from_list)
            
            sync_u_btn = QPushButton("REFRESH LIST")
            sync_u_btn.setStyleSheet("background: #1e293b; border: 1px solid #10b981; color: #10b981; font-size: 10px; padding: 8px;")
            sync_u_btn.clicked.connect(self.refresh_users_from_sql)
            
            rem_u_btn = QPushButton("REMOVE")
            rem_u_btn.setStyleSheet("background: #1e293b; border: 1px solid #f43f5e; color: #f43f5e; font-size: 10px; padding: 8px;")
            rem_u_btn.clicked.connect(self.remove_user)
            
            u_btn_layout.addWidget(add_u_btn)
            u_btn_layout.addWidget(edit_u_btn)
            u_btn_layout.addWidget(sync_u_btn)
            u_btn_layout.addWidget(rem_u_btn)
            user_layout.addLayout(u_btn_layout)
            
            # Double click to edit
            self.user_list.doubleClicked.connect(self.edit_user_from_list)
            
            user_card.layout().addLayout(user_layout)
            grid_layout.addWidget(user_card, 2, 1)
        else:
            # Placeholder or Informational card for non-admins
            lock_card = self._create_card("USER MANAGEMENT", "#475569")
            lock_layout = QVBoxLayout()
            warn = QLabel("ACCESS RESTRICTED\nOnly Administrators can manage user accounts.")
            warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            warn.setStyleSheet("color: #94a3b8; font-weight: 700; font-size: 11px;")
            lock_layout.addWidget(warn)
            lock_card.layout().addLayout(lock_layout)
            grid_layout.addWidget(lock_card, 2, 1)
        
        container_layout.addLayout(grid_layout)

        
        scroll.setWidget(container)
        main_v = QVBoxLayout(self)
        main_v.setContentsMargins(0,0,0,0)
        main_v.addWidget(scroll)

    def _create_card(self, title, accent_color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1e293b;
                border-radius: 20px;
                border: 1px solid #334155;
            }}
            QLabel {{ border: none; font-weight: bold; color: #94a3b8; font-size: 11px; }}
            QLineEdit, QDateEdit, QListWidget {{
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #f1f5f9;
                padding: 8px;
            }}
        """)
        l = QVBoxLayout(card)
        l.setContentsMargins(25, 25, 25, 25)
        l.setSpacing(15)
        
        t = QLabel(title)
        t.setStyleSheet(f"color: {accent_color}; font-size: 10px; font-weight: 950; letter-spacing: 1.5px;")
        l.addWidget(t)
        return card

    def _get_sql_config(self):
        """Standardized SQL config from hardcoded constants in sql_service."""
        from floor_view.api.sql_service import SQL_CONFIG
        return SQL_CONFIG

    def browse_data_path(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Select Planner Data File", "", "JSON Files (*.json)")
        if file_path:
            self.data_path_input.setText(file_path)

    def add_holiday(self):
        date_str = self.h_date_input.date().toString("yyyy-MM-dd")
        items = [self.holiday_list.item(i).text() for i in range(self.holiday_list.count())]
        if date_str not in items:
            self.holiday_list.addItem(date_str)
            self.holiday_list.sortItems()

    def remove_holiday(self):
        selected = self.holiday_list.currentRow()
        if selected >= 0: self.holiday_list.takeItem(selected)

    def add_working_sat(self):
        date = self.sat_date_input.date()
        if date.toPyDate().weekday() != 5: return
        date_str = date.toString("yyyy-MM-dd")
        items = [self.sat_list.item(i).text() for i in range(self.sat_list.count())]
        if date_str not in items:
            self.sat_list.addItem(date_str)
            self.sat_list.sortItems()

    def remove_working_sat(self):
        selected = self.sat_list.currentRow()
        if selected >= 0: self.sat_list.takeItem(selected)

    def refresh_user_list(self):
        self.user_list.clear()
        for u in self.users:
            self.user_list.addItem(f"{u['name']} ({u['role']})")

    def edit_user_from_list(self):
        """Triggered by 'Edit User' button or double-click on user list."""
        row = self.user_list.currentRow()
        if row >= 0:
            self.add_user_dialog(existing_user=self.users[row])

    def add_user_dialog(self, existing_user=None):
        from PyQt6.QtWidgets import QDialog, QCheckBox, QGroupBox, QComboBox
        dialog = QDialog(self)
        dialog.setWindowTitle("User Management & Permissions")
        dialog.setMinimumWidth(350)
        dialog.setStyleSheet("background: #1e1e2d; color: white;")
        layout = QVBoxLayout(dialog)
        
        form = QGridLayout()
        form.setVerticalSpacing(15)
        
        form.addWidget(QLabel("User Name:"), 0, 0)
        name_in = QLineEdit(existing_user["name"] if existing_user else "")
        name_in.setStyleSheet("background: #0f172a; border: 1px solid #334155; padding: 5px;")
        form.addWidget(name_in, 0, 1)
        
        form.addWidget(QLabel("Role:"), 1, 0)
        role_in = QComboBox()
        role_in.addItems(["Administrator", "Planner", "Viewer", "Pre-Press Dep."])
        if existing_user:
            role_in.setCurrentText(existing_user["role"])
        role_in.setStyleSheet("background: #0f172a; border: 1px solid #334155; padding: 5px;")
        form.addWidget(role_in, 1, 1)
        
        form.addWidget(QLabel("Password:"), 2, 0)
        pwd_in = QLineEdit(existing_user["password"] if existing_user else "")
        pwd_in.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_in.setStyleSheet("background: #0f172a; border: 1px solid #334155; padding: 5px;")
        form.addWidget(pwd_in, 2, 1)
        layout.addLayout(form)
        
        # Permissions Group
        perm_group = QGroupBox("VISIBLE TABS (PERMISSIONS)")
        perm_group.setStyleSheet("QGroupBox { border: 1px solid #334155; margin-top: 15px; padding: 15px; font-weight: bold; color: #38bdf8; }")
        perm_layout = QVBoxLayout()
        
        tabs = [
            ("PLANNER BOARD", "planner"), 
            ("FINISHING BOARD", "finishing"),
            ("PACKING BOARD", "packing"),
            ("DELIVERY BOARD", "delivery"),
            #("MASTER DASHBOARD", "dashboard"), 
            ("ALL RECORDS", "records"),
            #("PRODUCTION EFFICIENCY", "efficiency"), ("FINANCIAL KPIs", "financial"), ("STRATEGIC KPIs", "strategic"),
            ("SUMMARY REPORT", "summary"),
            ("SYSTEM SETTINGS", "settings"), 
            ("ABOUT ENGINE", "about")
        ]
        checks = {}
        existing_perms = existing_user.get("permissions", "").split(",") if existing_user else []
        
        for label, key in tabs:
            cb = QCheckBox(label)
            if existing_user:
                cb.setChecked(key in existing_perms)
            else:
                # Admins default to all, others can be customized
                cb.setChecked(True)
            cb.setStyleSheet("QCheckBox { spacing: 10px; padding: 5px; }")
            perm_layout.addWidget(cb)
            checks[key] = cb
        perm_group.setLayout(perm_layout)
        layout.addWidget(perm_group)
        
        btns = QHBoxLayout()
        save = QPushButton("SAVE USER")
        save.setStyleSheet("background: #10b981; color: white; padding: 12px; font-weight: 800; border-radius: 6px;")
        save.clicked.connect(dialog.accept)
        cancel = QPushButton("CANCEL")
        cancel.setStyleSheet("background: #334155; color: white; padding: 12px; font-weight: 800; border-radius: 6px;")
        cancel.clicked.connect(dialog.reject)
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_in.text().strip()
            role = role_in.currentText()
            pwd = pwd_in.text().strip()
            if not name or not pwd: return
            
            selected_perms = [key for key, cb in checks.items() if cb.isChecked()]
            perms_str = ",".join(selected_perms)
            
            new_user = {"name": name, "role": role, "password": pwd, "permissions": perms_str}
            
            # Check for existing user to update instead of add if it's an edit-like flow
            # (Simplifying to always add/replace in this implementation)
            for i, u in enumerate(self.users):
                if u["name"] == name:
                    self.users[i] = new_user
                    break
            else:
                self.users.append(new_user)
            
            # SQL Sync
            if self.settings.get("sqlServer"):
                try:
                    from floor_view.api import sql_service
                    sql_service.save_sql_user(new_user, self._get_sql_config())
                    print(f"SQL SYNC: Saved user {name}")
                except Exception as e:
                    print(f"SQL SYNC ERROR: {e}")
            self.refresh_user_list()

    def remove_user(self):
        row = self.user_list.currentRow()
        if row >= 0:
            if len(self.users) <= 1:
                QMessageBox.warning(self, "Error", "Cannot remove the last remaining user account.")
                return
            
            user_to_rem = self.users[row]["name"]
            
            # 1. SQL Deletion First (using hardcoded config)
            from floor_view.api.sql_service import SQL_CONFIG
            if SQL_CONFIG.get("server"):
                try:
                    from floor_view.api import sql_service
                    sql_service.delete_sql_user(user_to_rem, SQL_CONFIG)
                    print(f"SQL SYNC: Deleted user {user_to_rem} from database.")
                except Exception as e:
                    print(f"SQL SYNC ERROR: {e}")
            
            # 2. Local Deletion
            del self.users[row]
            self.refresh_user_list()
            
            # 3. Persist change to local settings too
            self.settings["users"] = self.users
            self.save_callback(self.settings)

    def refresh_users_from_sql(self):
        """Manually force a fetch of all users from the SQL database using hardcoded config."""
        from floor_view.api.sql_service import SQL_CONFIG
        if not SQL_CONFIG.get("server"):
            QMessageBox.warning(self, "SQL Sync", "SQL Server connection not configured. Cannot refresh user list.")
            return

        try:
            from floor_view.api import sql_service
            users = sql_service.get_sql_users(SQL_CONFIG)
            if users:
                self.users = users
                self.refresh_user_list()
                # Also persist these to the data object
                self.settings["users"] = self.users
                self.save_callback(self.settings)
                QMessageBox.information(self, "SQL Sync", f"Successfully retrieved {len(users)} users from database.")
            else:
                QMessageBox.warning(self, "SQL Sync", "No users found in SQL database Table.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to sync users from SQL: {str(e)}")
    # Obsolete DB/API sync methods removed.

    def save_settings(self):
        try:
            # Baseline settings available to all roles
            new_settings = {
                "shiftHours": float(self.shift_input.text() or 8),
                "workingDays": [d for d, cb in self.day_checks.items() if cb.isChecked()],
                "publicHolidays": [self.holiday_list.item(i).text() for i in range(self.holiday_list.count())],
                "workingSaturdays": [self.sat_list.item(i).text() for i in range(self.sat_list.count())],
                "machineShifts": {m: float(inp.text() or 8) for m, inp in self.machine_shift_inputs.items()},
                "dataPath": self.data_path_input.text() or "test_planning_100_jobs.json",
                "users": self.users
            }
            
            # Preserve existing hardcoded-adjacent settings
            core_keys = ["sqlServer", "sqlDatabase", "sqlUser", "sqlPassword", "sqlTableView", 
                        "sqlExportEnabled", "sqlLiveSyncEnabled", "apiEnabled", "syncSource",
                        "apiPort", "apiUrl", "apiToken", "apiInterval"]
            for key in core_keys:
                new_settings[key] = self.settings.get(key)

            # Update machine categories directly in machines_data object
            if hasattr(self, 'machine_category_inputs'):
                for m_name, cb in self.machine_category_inputs.items():
                    if m_name in self.machines_data:
                        self.machines_data[m_name]["category"] = cb.currentText()
                
            self.save_callback(new_settings)
            
            # Sync all users to SQL using hardcoded config
            from floor_view.api.sql_service import SQL_CONFIG
            if SQL_CONFIG.get("server"):
                try:
                    from floor_view.api import sql_service
                    for u in self.users:
                        sql_service.save_sql_user(u, SQL_CONFIG)
                    print("SQL SYNC: All users synchronized to database.")
                except Exception as e:
                    print(f"SQL SYNC ERROR (Users): {e}")

            QMessageBox.information(self, "Success", "Settings saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")
    # Migration methods removed.
