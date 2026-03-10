from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
                             QGridLayout, QScrollArea, QDateEdit, QPushButton, QComboBox)
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QStandardItemModel, QStandardItem
from py_planner.utils.chart_utils import ChartManager
from py_planner.utils.planner_utils import PlannerLogic
from datetime import datetime

class CustomProgressBar(QFrame):
    def __init__(self, value, color="#6366f1", height=6):
        super().__init__()
        self.setFixedHeight(height)
        self.setMinimumWidth(80)
        self.setStyleSheet(f"background-color: #232a4e; border-radius: {height//2}px;")
        
        inner_layout = QHBoxLayout(self)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        
        self.fill = QFrame()
        self.fill.setFixedHeight(height)
        val = min(100, max(0, value))
        self.fill.setStyleSheet(f"background-color: {color}; border-radius: {height//2}px;")
        
        inner_layout.addWidget(self.fill, int(val))
        inner_layout.addStretch(100 - int(val))

class StepKPICard(QFrame):
    """Specific KPI card for a production step (e.g. Packing)"""
    def __init__(self, title, rev, counts, color="#38bdf8"):
        super().__init__()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #181c33;
                border-radius: 20px;
                border: 1px solid #232a4e;
            }}
            QLabel {{ background: transparent; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # Title
        t = QLabel(title.upper())
        t.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 900; letter-spacing: 1px;")
        layout.addWidget(t)
        
        # Revenue
        rev_box = QVBoxLayout()
        r_lbl = QLabel("REVENUE (MUR)")
        r_lbl.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700;")
        self.r_val = QLabel(f"MUR {int(rev):,}")
        self.r_val.setStyleSheet("color: #f1f5f9; font-size: 20px; font-weight: 900;")
        rev_box.addWidget(r_lbl)
        rev_box.addWidget(self.r_val)
        layout.addLayout(rev_box)
        
        # Status Grid
        status_layout = QGridLayout()
        status_layout.setContentsMargins(0, 10, 0, 0)
        
        # Helper to create status mini-stats
        def add_stat(row, label, val, s_color):
            l = QLabel(label)
            l.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 600;")
            v = QLabel(str(val))
            v.setStyleSheet(f"color: {s_color}; font-size: 13px; font-weight: 900;")
            status_layout.addWidget(l, row, 0)
            status_layout.addWidget(v, row, 1, Qt.AlignmentFlag.AlignRight)
            return v

        self.pending_val = add_stat(0, "PENDING", counts.get("pending", 0), "#6366f1")
        self.ip_val = add_stat(1, "IN PROGRESS", counts.get("in_progress", 0), "#fbbf24")
        self.hold_val = add_stat(2, "ON HOLD", counts.get("on_hold", 0), "#f43f5e")
        self.comp_val = add_stat(3, "COMPLETED", counts.get("completed", 0), "#10b981")
        
        layout.addLayout(status_layout)
        
        # Progress Bar (Completion %)
        total = counts.get("total_jobs", 0)
        comp = counts.get("completed", 0)
        perc = (comp / total * 100) if total > 0 else 0
        
        self.prog_bar = CustomProgressBar(perc, color=color)
        layout.addWidget(self.prog_bar)
        self.perc_lbl = QLabel(f"{int(perc)}% COMPLETE")
        self.perc_lbl.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;")
        layout.addWidget(self.perc_lbl)

    def update_data(self, rev, counts):
        self.r_val.setText(f"MUR {int(rev):,}")
        self.pending_val.setText(str(counts.get("pending", 0)))
        self.ip_val.setText(str(counts.get("in_progress", 0)))
        self.hold_val.setText(str(counts.get("on_hold", 0)))
        self.comp_val.setText(str(counts.get("completed", 0)))
        
        total = counts.get("total_jobs", 0)
        comp = counts.get("completed", 0)
        perc = (comp / total * 100) if total > 0 else 0
        
        # Recreate progress bar fill for simplicity or just replace widget
        # For now, let's keep it simple.
        self.perc_lbl.setText(f"{int(perc)}% COMPLETE")

class CheckableComboBox(QComboBox):
    selectionChanged = pyqtSignal() # Custom signal for multi-select

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view().viewport().installEventFilter(self)
        self.model().itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item):
        self.selectionChanged.emit()

    def eventFilter(self, widget, event):
        if widget is self.view().viewport() and event.type() == event.Type.MouseButtonRelease:
            index = self.view().indexAt(event.pos())
            item = self.model().itemFromIndex(index)
            if item.checkState() == Qt.CheckState.Checked:
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Checked)
            return True
        return super().eventFilter(widget, event)

    def hidePopup(self):
        super().hidePopup()
        # Ensure we always update on close just in case
        self.selectionChanged.emit()

    def addItem(self, text, data=None):
        item = QStandardItem(text)
        item.setCheckable(True)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.model().appendRow(item)

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def currentText(self):
        items = self.get_selected_items()
        return ", ".join(items) if items else "ALL STATUSES"

    def get_selected_items(self):
        res = []
        for i in range(self.model().rowCount()):
            item = self.model().item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                res.append(item.text())
        return res

class SummaryReportView(QWidget):
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.logic = PlannerLogic(data.get("appSettings", {}))
        
        # Default filters: wider range to ensure all current/future jobs are visible
        self.end_date = QDate.currentDate().addDays(365)
        self.start_date = QDate.currentDate().addDays(-365)
        
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("background-color: #111122;")
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Filter Bar
        self.filter_bar = QFrame()
        self.filter_bar.setStyleSheet("background-color: #181c33; border-bottom: 1px solid #232a4e;")
        filter_layout = QHBoxLayout(self.filter_bar)
        filter_layout.setContentsMargins(25, 15, 25, 15)
        filter_layout.setSpacing(20)
        
        # Date Filter Labels and Edits
        def add_date_picker(label, date_val, attr_name):
            box = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800;")
            editor = QDateEdit(date_val)
            editor.setCalendarPopup(True)
            editor.setStyleSheet("background: #111122; border: 1px solid #232a4e; color: white; padding: 5px;")
            box.addWidget(lbl)
            box.addWidget(editor)
            filter_layout.addLayout(box)
            setattr(self, attr_name, editor)
            return editor

        self.s_date_in = add_date_picker("START DATE", self.start_date, "s_date_in")
        self.s_date_in.dateChanged.connect(self.refresh)
        
        self.e_date_in = add_date_picker("END DATE", self.end_date, "e_date_in")
        self.e_date_in.dateChanged.connect(self.refresh)
        
        # Status Filter
        status_box = QVBoxLayout()
        s_lbl = QLabel("JOB STATUSES")
        s_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800;")
        self.status_filter = CheckableComboBox()
        self.status_filter.addItems(["NOT STARTED", "IN PROGRESS", "ON HOLD", "COMPLETED", "CANCELLED"])
        self.status_filter.setStyleSheet("""
            QComboBox { 
                background: #111122; border: 1px solid #232a4e; color: white; padding: 5px; min-width: 180px;
            }
            QComboBox QAbstractItemView { background: #181c33; color: white; selection-background-color: #38bdf8; }
        """)
        self.status_filter.selectionChanged.connect(self.refresh)
        status_box.addWidget(s_lbl)
        status_box.addWidget(self.status_filter)
        filter_layout.addLayout(status_box)
        
        refresh_btn = QPushButton("GENERATE REPORT")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: #38bdf8; color: #111122; font-weight: 800; border-radius: 6px; padding: 10px 20px; margin-top: 15px;
            }
            QPushButton:hover { background: #7dd3fc; }
        """)
        refresh_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(refresh_btn)
        filter_layout.addStretch()
        
        main_layout.addWidget(self.filter_bar)
        
        # 2. Scroll Area for Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        main_layout.addWidget(scroll)
        
        container = QWidget()
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setContentsMargins(25, 25, 25, 25)
        self.container_layout.setSpacing(30)
        scroll.setWidget(container)
        
        self.refresh()

    def refresh(self):
        try:
            # Clear existing
            while self.container_layout.count() > 0:
                item = self.container_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
                elif item.layout(): self._clear_layout(item.layout())
            
            # Get data
            start_dt = datetime.combine(self.s_date_in.date().toPyDate(), datetime.min.time())
            end_dt = datetime.combine(self.e_date_in.date().toPyDate(), datetime.max.time())
            
            # Get status filter
            selected = self.status_filter.get_selected_items()
            status_vals = [s.lower().replace(" ", "_") for s in selected] if selected else None
            
            stats = self.logic.get_summary_stats(self.data.get("machines", {}), start_dt, end_dt, status_filter=status_vals)
            
            # 3. Header
            header = QVBoxLayout()
            header.setContentsMargins(0, 0, 0, 10)
            h1 = QLabel("Cross-Departmental Summary Report")
            h1.setStyleSheet("color: #f1f5f9; font-size: 26px; font-weight: 900; background: transparent;")
            h2 = QLabel(f"Aggregated production metrics from {start_dt.strftime('%d %b %Y')} to {end_dt.strftime('%d %b %Y')}")
            h2.setStyleSheet("color: #94a3b8; font-size: 13px; background: transparent;")
            header.addWidget(h1)
            header.addWidget(h2)
            self.container_layout.addLayout(header)
            
            # 4. Department KPI Row
            kpi_row = QHBoxLayout()
            kpi_row.setSpacing(20)
            
            colors = {
                "production": "#6366f1", # Indigo
                "finishing": "#a855f7",  # Purple
                "packing": "#f43f5e",    # Rose
                "delivery": "#10b981"    # Emerald
            }
            
            for cat in ["production", "finishing", "packing", "delivery"]:
                cat_data = stats["categories"].get(cat, {})
                title = "PLANNER" if cat == "production" else cat
                card = StepKPICard(title, cat_data.get("rev", 0), cat_data, color=colors.get(cat, "#38bdf8"))
                kpi_row.addWidget(card)
            
            self.container_layout.addLayout(kpi_row)
            
            # 5. Charts Row
            chart_row = QHBoxLayout()
            chart_row.setSpacing(30)
            
            # Revenue by Step (Bar Chart)
            rev_data = {
                "Planner": stats["categories"]["production"]["rev"],
                "Finishing": stats["categories"]["finishing"]["rev"],
                "Packing": stats["categories"]["packing"]["rev"],
                "Delivery": stats["categories"]["delivery"]["rev"]
            }
            rev_chart = ChartManager.create_bar_chart_widget(rev_data, "Revenue by Production Stage", colors="#38bdf8")
            rev_chart.setMinimumHeight(350)
            chart_row.addWidget(self._wrap_chart("REVENUE PER STAGE (MUR)", rev_chart))
            
            # Status Concentration (Pie Chart)
            # Combine all categories for global status split
            global_status = {"Pending": 0, "In Progress": 0, "On Hold": 0, "Completed": 0, "Cancelled": 0}
            for cat in stats["categories"].values():
                global_status["Pending"] += cat.get("pending", 0)
                global_status["In Progress"] += cat.get("in_progress", 0)
                global_status["On Hold"] += cat.get("on_hold", 0)
                global_status["Completed"] += cat.get("completed", 0)
                global_status["Cancelled"] += cat.get("cancelled", 0)
                
            status_chart = ChartManager.create_pie_chart_widget(global_status, "Global Status Distribution")
            chart_row.addWidget(self._wrap_chart("PRODUCTION STATUS MIX", status_chart))
            
            self.container_layout.addLayout(chart_row)
            
            # 6. Top Customers Row
            if stats.get("top_customers"):
                cust_frame = QFrame()
                cust_frame.setStyleSheet("background-color: #181c33; border-radius: 20px; border: 1px solid #232a4e;")
                cust_layout = QVBoxLayout(cust_frame)
                cust_layout.setContentsMargins(25, 25, 25, 25)
                
                ct = QLabel("TOP 5 CUSTOMERS BY REVENUE")
                ct.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 950; letter-spacing: 1.5px; background: transparent;")
                cust_layout.addWidget(ct)
                
                grid = QGridLayout()
                grid.setSpacing(15)
                for i, (name, rev) in enumerate(stats["top_customers"]):
                    n_lbl = QLabel(name)
                    n_lbl.setStyleSheet("color: #f1f5f9; font-size: 14px; font-weight: 800; background: transparent;")
                    r_lbl = QLabel(f"MUR {int(rev):,}")
                    r_lbl.setStyleSheet("color: #38bdf8; font-size: 14px; font-weight: 900; background: transparent;")
                    
                    grid.addWidget(n_lbl, i, 0)
                    grid.addWidget(r_lbl, i, 1, Qt.AlignmentFlag.AlignRight)
                    
                    # Add a mini separator
                    if i < len(stats["top_customers"]) - 1:
                        line = QFrame()
                        line.setFrameShape(QFrame.Shape.HLine)
                        line.setStyleSheet("background: #232a4e; max-height: 1px; border: none;")
                        grid.addWidget(line, i, 0, 1, 2, Qt.AlignmentFlag.AlignBottom)
                
                cust_layout.addLayout(grid)
                self.container_layout.addWidget(cust_frame)
        except Exception as e:
            print(f"SUMMARY REPORT REFRESH ERROR: {e}")
            import traceback
            traceback.print_exc()

    def _wrap_chart(self, title, chart):
        frame = QFrame()
        frame.setStyleSheet("background-color: #181c33; border-radius: 24px; border: 1px solid #232a4e;")
        box = QVBoxLayout(frame)
        box.setContentsMargins(25, 25, 25, 15)
        
        t = QLabel(title)
        t.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 900; letter-spacing: 1.5px; background: transparent;")
        box.addWidget(t)
        box.addWidget(chart)
        return frame

    def _clear_layout(self, layout):
        while layout.count() > 0:
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            elif item.layout(): self._clear_layout(item.layout())
