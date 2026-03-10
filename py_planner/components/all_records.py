from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QLabel, QHBoxLayout, QLineEdit, QFrame, QComboBox, QDateEdit)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor, QFont
from datetime import datetime
from py_planner.utils.planner_utils import PlannerLogic

class FilterHeader(QFrame):
    def __init__(self, data, on_filter_changed):
        super().__init__()
        # Store full data object to allow dynamic access to latest machines
        self.data = data
        self.on_filter_changed = on_filter_changed
        self.setStyleSheet("background-color: #181c33; border-bottom: 1px solid #232a4e;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(30, 15, 30, 15)
        layout.setSpacing(25)

        # Category Selector
        c_box = QVBoxLayout()
        cl = QLabel("CATEGORY")
        cl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 900;")
        self.cat_selector = QComboBox()
        self.cat_selector.addItem("All Categories", "all")
        self.cat_selector.addItem("Planner (Production)", "production")
        self.cat_selector.addItem("Finishing", "finishing")
        self.cat_selector.addItem("Packing", "packing")
        self.cat_selector.addItem("Delivery", "delivery")
        self.cat_selector.setStyleSheet("background: #111122; border: 1px solid #232a4e; color: white; padding: 5px; min-width: 150px;")
        
        c_box.addWidget(cl)
        c_box.addWidget(self.cat_selector)
        layout.addLayout(c_box)

        # Machine selector
        m_box = QVBoxLayout()
        ml = QLabel("MACHINE FOCUS")
        ml.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 900;")
        self.mc_selector = QComboBox()
        self.mc_selector.addItem("All Fleet Units", "all")
        self.mc_selector.setStyleSheet("background: #111122; border: 1px solid #232a4e; color: white; padding: 5px; min-width: 150px;")
        
        m_box.addWidget(ml)
        m_box.addWidget(self.mc_selector)
        layout.addLayout(m_box)

        # Initial machine population
        self.refresh_machines()

        self.cat_selector.currentIndexChanged.connect(self.on_category_changed)
        self.mc_selector.currentIndexChanged.connect(self.trigger_change)

        # Dates: wider default range to ensure all metrics are captured
        today = QDate.currentDate()
        self.end_date = today.addDays(365)
        self.start_date = today.addDays(-365)

        s_box = QVBoxLayout()
        sl = QLabel("START DATE")
        sl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 900;")
        self.s_edit = QDateEdit(self.start_date)
        self.s_edit.setCalendarPopup(True)
        self.s_edit.setStyleSheet("background: #111122; border: 1px solid #232a4e; color: white; padding: 5px;")
        self.s_edit.dateChanged.connect(self.trigger_change)
        s_box.addWidget(sl)
        s_box.addWidget(self.s_edit)
        layout.addLayout(s_box)

        e_box = QVBoxLayout()
        el = QLabel("END DATE")
        el.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 900;")
        self.e_edit = QDateEdit(self.end_date)
        self.e_edit.setCalendarPopup(True)
        self.e_edit.setStyleSheet("background: #111122; border: 1px solid #232a4e; color: white; padding: 5px;")
        self.e_edit.dateChanged.connect(self.trigger_change)
        e_box.addWidget(el)
        e_box.addWidget(self.e_edit)
        layout.addLayout(e_box)

        layout.addStretch()

    def on_category_changed(self):
        self.refresh_machines()
        self.trigger_change()

    def refresh_machines(self):
        """Dynamic population of machines based on current data and category."""
        try:
            cat = self.cat_selector.currentData()
            
            self.mc_selector.blockSignals(True)
            curr_m = self.mc_selector.currentData()
            self.mc_selector.clear()
            self.mc_selector.addItem("All Fleet Units", "all")
            self.mc_selector.setStyleSheet("background: #111122; border: 1px solid #232a4e; color: white; padding: 5px; min-width: 150px;")
            
            from py_planner.utils.planner_utils import PlannerLogic
            logic = PlannerLogic()
            machines = self.data.get("machines", {})
            for name, m in machines.items():
                m_cat = logic.normalize_category(m.get("category", "production"))
                if cat == "all" or m_cat == cat:
                    self.mc_selector.addItem(name, name)
                    
            idx = self.mc_selector.findData(curr_m)
            if idx >= 0: self.mc_selector.setCurrentIndex(idx)
            else: self.mc_selector.setCurrentIndex(0)
            self.mc_selector.blockSignals(False)
        except Exception as e:
            print(f"FILTER_HEADER ERROR: {e}")

    def trigger_change(self):
        c, m, s, e = self.get_filters()
        self.on_filter_changed(c, m, s, e)

    def get_filters(self):
        c = self.cat_selector.currentData()
        m = self.mc_selector.currentData()
        s = datetime.combine(self.s_edit.date().toPyDate(), datetime.min.time())
        e = datetime.combine(self.e_edit.date().toPyDate(), datetime.max.time())
        return c, m, s, e

    def set_date_range(self, start_date: QDate, end_date: QDate):
        """Allows external components to set the filter window."""
        self.s_edit.blockSignals(True)
        self.e_edit.blockSignals(True)
        self.s_edit.setDate(start_date)
        self.e_edit.setDate(end_date)
        self.s_edit.blockSignals(False)
        self.e_edit.blockSignals(False)
        self.trigger_change()

class AllRecordsView(QWidget):
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.init_ui()

    def refresh(self):
        # Ensure machine list is up-to-date with latest data
        if hasattr(self, 'header'):
            self.header.refresh_machines()
        self.refresh_table()

    def init_ui(self):
        self.setStyleSheet("background-color: #111122;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Search, Status and Table Widgets (must exist before header.set_date_range triggers refresh)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search PJC or Customer...")
        self.search_input.setFixedWidth(250)
        self.search_input.setStyleSheet("background: #181c33; border: 1px solid #232a4e; color: white; padding: 8px; border-radius: 6px;")
        self.search_input.textChanged.connect(self.filter_data)
        
        self.status_selector = QComboBox()
        self.status_selector.addItem("All Statuses", "all")
        # Standard statuses from PlanningBoard
        statuses = ["not_started", "in_progress", "completed", "on_hold", "cancelled"]
        for s in statuses:
            self.status_selector.addItem(s.replace("_", " ").title(), s)
        self.status_selector.setStyleSheet("background: #181c33; border: 1px solid #232a4e; color: white; padding: 8px; border-radius: 6px; min-width: 150px;")
        self.status_selector.currentIndexChanged.connect(self.on_filter_changed)
        
        self.table = QTableWidget()
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)

        # Global Filter Bar
        self.header = FilterHeader(self.data, self.on_filter_changed)
        
        # Default to a very wide range for 'All Records' to show future pending and past completed
        from PyQt6.QtCore import QDate
        today = QDate.currentDate()
        self.header.set_date_range(today.addDays(-365), today.addDays(365))
        
        layout.addWidget(self.header)

        header_container = QFrame()
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(30, 20, 30, 10)
        
        title = QLabel("All Production Records")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #f1f5f9;")
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(QLabel("STATUS:"))
        header_layout.addWidget(self.status_selector)
        header_layout.addSpacing(10)
        header_layout.addWidget(QLabel("SEARCH:"))
        header_layout.addWidget(self.search_input)
        layout.addWidget(header_container)
        layout.addWidget(self.table)
        
        self.refresh_table()
        
        # Deferred machine population: SQL data may load after widget init.
        # Use a short delay to ensure machines are populated after the main window finishes.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self._deferred_populate_machines)

    def _deferred_populate_machines(self):
        """Populates machine dropdown after SQL data is available."""
        if hasattr(self, 'header'):
            self.header.refresh_machines()

    def on_item_double_clicked(self, item):
        from py_planner.components.job_detail_dialog import JobDetailDialog
        row = item.row()
        # Find the actual job in all_jobs by finding which one matches the visible row
        # (This handles filtering correctly)
        visible_pjc = self.table.item(row, 0).text()
        visible_cust = self.table.item(row, 2).text()
        
        target_job = None
        for job in self.all_jobs:
            if job.get('pjc') == visible_pjc and job.get('customer') == visible_cust:
                target_job = job
                break
        
        if target_job:
            dialog = JobDetailDialog(target_job, self)
            dialog.exec()

    def on_filter_changed(self, *args):
        # Ensure the machine list always reflects the latest loaded data
        if hasattr(self, 'header'):
            self.header.refresh_machines()
        self.refresh_table()

    def refresh_table(self):
        c_filter, m_filter, s_date, e_date = self.header.get_filters()
        status_filter = self.status_selector.currentData()
        logic = PlannerLogic()
        
        all_jobs = []
        for m_name, m_data in self.data.get("machines", {}).items():
            if m_filter != "all" and m_name != m_filter:
                continue
                
            m_cat = m_data.get("category", "production")
            if c_filter != "all" and m_cat != c_filter:
                continue
                
            # Search Filter
            search_text = self.search_input.text().lower()
            
            for job in m_data.get("jobs", []):
                # Apply search filter if active
                if search_text:
                    pjc = str(job.get("pjc", "")).lower()
                    cust = str(job.get("customer", "")).lower()
                    if search_text not in pjc and search_text not in cust:
                        continue

                # Status Filter
                raw_status = job.get("status") or job.get("orderStatus")
                norm_status = logic.normalize_status(raw_status)
                
                if status_filter != "all" and norm_status != status_filter:
                    # Special check for 'pending' (normalized from not_started/etc)
                    if not (status_filter == "not_started" and norm_status == "pending"):
                        continue
                
                # Filter by date range for all jobs
                # Fallback Sequence: CompletedAt -> DeliveryDate -> OrderDate (pjcIn)
                job_date = datetime.min
                if norm_status == "completed":
                    job_date = logic.safe_date(job.get("completedAt"))
                    if job_date == datetime.min:
                        job_date = logic.safe_date(job.get("deliveryDate"))
                else:
                    job_date = logic.safe_date(job.get("deliveryDate"))
                    if job_date == datetime.min:
                        # Falling back to Order Date (pjcIn) if Delivery Date is missing
                        job_date = logic.safe_date(job.get("pjcIn"))
                
                # Apply Date Filter: If job has a date, it must be within range.
                if job_date != datetime.min:
                    if not (s_date <= job_date <= e_date):
                        continue
                else:
                    # LENIENT STRICTNESS: Only exclude undated jobs if range is active AND narrowband (< 350 days)
                    range_days = (e_date - s_date).days
                    if range_days < 350:
                        continue
                
                all_jobs.append({**job, "machine": m_name})
        
        self.all_jobs = all_jobs
        
        # Consistent Columns from React App
        cols = [
            ("PJC", "pjc"), ("Machine", "machine"), ("Customer", "customer"), 
            ("Description", "description"), ("Started", "startedAt"), 
            ("Completed", "completedAt"), ("Status", "status")
        ]
        self.cols = cols
        
        self.table.setColumnCount(len(cols))
        self.table.setRowCount(len(all_jobs))
        self.table.setHorizontalHeaderLabels([c[0] for c in cols])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        
        for r_idx, job in enumerate(all_jobs):
            for c_idx, (label, key) in enumerate(cols):
                val = job.get(key, "")
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Make PJC Bold
                if key == "pjc":
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                
                norm_status = logic.normalize_status(job.get("status"))
                if norm_status == "completed":
                    item.setForeground(Qt.GlobalColor.gray)
                elif norm_status == "in_progress":
                    item.setForeground(QColor("#38bdf8"))
                
                self.table.setItem(r_idx, c_idx, item)

    def filter_data(self, text):
        self.refresh_table()
