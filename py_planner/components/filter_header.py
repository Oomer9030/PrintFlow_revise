from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
                             QComboBox, QDateEdit, QFrame)
from PyQt6.QtCore import Qt, QDate
from datetime import datetime

class FilterHeader(QFrame):
    """
    Reusable filtering header for Production Records.
    Handles Category, Machine, and Date Range selection.
    """
    def __init__(self, data, filter_changed_callback):
        super().__init__()
        self.data = data
        self.callback = filter_changed_callback
        self.init_ui()

    def init_ui(self):
        self.setObjectName("FilterHeader")
        self.setStyleSheet("""
            QFrame#FilterHeader {
                background-color: #181c33;
                border-bottom: 3px solid #38bdf8;
                min-height: 80px;
            }
            QLabel { color: #94a3b8; font-size: 10px; font-weight: 800; }
            QComboBox, QDateEdit {
                background: #111122;
                border: 1px solid #232a4e;
                color: white;
                padding: 5px;
                border-radius: 4px;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(30, 10, 30, 10)
        layout.setSpacing(25)

        # 1. Category Filter
        cat_box = QVBoxLayout()
        cat_box.addWidget(QLabel("CATEGORY"))
        self.cat_selector = QComboBox()
        self.cat_selector.addItem("All Categories", "all")
        self.cat_selector.addItems(["Production", "Finishing", "Packing", "Delivery"])
        self.cat_selector.currentIndexChanged.connect(self.on_filter_trigger)
        cat_box.addWidget(self.cat_selector)
        layout.addLayout(cat_box)

        # 2. Machine Filter
        m_box = QVBoxLayout()
        m_box.addWidget(QLabel("MACHINE"))
        self.m_selector = QComboBox()
        self.m_selector.addItem("All Machines", "all")
        self.refresh_machines()
        self.m_selector.currentIndexChanged.connect(self.on_filter_trigger)
        m_box.addWidget(self.m_selector)
        layout.addLayout(m_box)

        layout.addStretch()

        # 3. Date Range
        date_box = QHBoxLayout()
        date_box.setSpacing(10)
        
        # Start
        s_box = QVBoxLayout()
        s_box.addWidget(QLabel("FROM DATE"))
        self.s_date = QDateEdit(QDate.currentDate().addDays(-30))
        self.s_date.setCalendarPopup(True)
        self.s_date.dateChanged.connect(self.on_filter_trigger)
        s_box.addWidget(self.s_date)
        date_box.addLayout(s_box)

        # End
        e_box = QVBoxLayout()
        e_box.addWidget(QLabel("TO DATE"))
        self.e_date = QDateEdit(QDate.currentDate().addDays(7))
        self.e_date.setCalendarPopup(True)
        self.e_date.dateChanged.connect(self.on_filter_trigger)
        e_box.addWidget(self.e_date)
        date_box.addLayout(e_box)

        layout.addLayout(date_box)

    def refresh_machines(self):
        """Populates machine list based on currently selected category."""
        self.m_selector.blockSignals(True)
        current = self.m_selector.currentText()
        self.m_selector.clear()
        self.m_selector.addItem("All Machines", "all")
        
        cat_filter = self.cat_selector.currentText().lower()
        if cat_filter == "all categories": cat_filter = "all"
        
        machines = self.data.get("machines", {})
        for m_name, m_data in machines.items():
            if cat_filter == "all" or m_data.get("category", "").lower() == cat_filter:
                self.m_selector.addItem(m_name)
        
        # Restore selection if possible
        idx = self.m_selector.findText(current)
        self.m_selector.setCurrentIndex(idx if idx >= 0 else 0)
        self.m_selector.blockSignals(False)

    def on_filter_trigger(self):
        # Specific logic: if category changes, update machine list
        if self.sender() == self.cat_selector:
            self.refresh_machines()
        
        if self.callback:
            self.callback()

    def get_filters(self):
        cat = self.cat_selector.currentText().lower()
        if cat == "all categories": cat = "all"
        
        m_filter = self.m_selector.currentText()
        if m_filter == "All Machines": m_filter = "all"
        
        s_dt = datetime.combine(self.s_date.date().toPyDate(), datetime.min.time())
        e_dt = datetime.combine(self.e_date.date().toPyDate(), datetime.max.time())
        
        return cat, m_filter, s_dt, e_dt

    def set_date_range(self, start_qdate, end_qdate):
        self.blockSignals(True)
        self.s_date.setDate(start_qdate)
        self.e_date.setDate(end_qdate)
        self.blockSignals(False)
        if self.callback:
            self.callback()
