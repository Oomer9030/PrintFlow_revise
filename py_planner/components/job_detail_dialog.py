from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QFrame, QGridLayout, QPushButton, QScrollArea, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from py_planner.utils.styles import DARK_PALETTE

class JobDetailDialog(QDialog):
    def __init__(self, job_data, parent=None):
        super().__init__(parent)
        self.job = job_data
        self.setWindowTitle(f"Job Intelligence: {self.job.get('pjc', 'N/A')}")
        self.setMinimumSize(650, 750)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setStyleSheet(f"background-color: {DARK_PALETTE['background']}; border: 1px solid {DARK_PALETTE['border']};")
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Premium Header Section
        header_frame = QFrame()
        header_frame.setStyleSheet(f"background-color: {DARK_PALETTE['surface']}; border: none; border-bottom: 2px solid {DARK_PALETTE['primary']};")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(30, 30, 30, 30)

        pjc_label = QLabel(self.job.get('pjc', 'N/A'))
        pjc_label.setStyleSheet(f"font-size: 28px; font-weight: 900; color: {DARK_PALETTE['primary']}; letter-spacing: 1px;")
        header_layout.addWidget(pjc_label)

        cust_label = QLabel(self.job.get('customer', 'Unknown Entity'))
        cust_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #94a3b8; text-transform: uppercase;")
        header_layout.addWidget(cust_label)

        # Status Badge
        status = self.job.get('status', 'not_started').upper()
        status_color = DARK_PALETTE['success'] if status == 'COMPLETED' else DARK_PALETTE['primary']
        if status == 'NOT_STARTED': status_color = "#64748b"
        
        status_badge = QLabel(status.replace('_', ' '))
        status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_badge.setFixedWidth(120)
        status_badge.setStyleSheet(f"""
            background-color: {status_color}22;
            color: {status_color};
            border: 1px solid {status_color};
            border-radius: 6px;
            font-size: 10px;
            font-weight: 900;
            padding: 4px;
            margin-top: 15px;
        """)
        header_layout.addWidget(status_badge)
        main_layout.addWidget(header_frame)

        # 2. Key Data Grid (Scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        container = QWidget()
        container.setStyleSheet(f"background-color: {DARK_PALETTE['background']};")
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(30, 20, 30, 30)
        content_layout.setSpacing(25)

        # Section: Operational Specifications
        content_layout.addWidget(self._create_section_title("OPERATIONAL SPECIFICATIONS"))
        grid1 = QGridLayout()
        grid1.setSpacing(15)
        
        metrics = [
            ("Description", self.job.get('description', 'N/A')),
            ("Assigned Machine", self.job.get('machine', 'N/A')),
            ("Production Qty", f"{int(float(self.job.get('qty', 0)) or 0):,}"),
            ("Linear Meters", f"{int(float(self.job.get('meters', 0)) or 0):,} m"),
            ("M/C Time Requirements", f"{self.job.get('mcTime', '0')} Hours"),
            ("Material Width", f"{self.job.get('width', 'N/A')} mm"),
            ("Gear Teeth Spec", self.job.get('gearTeeth', 'N/A')),
            ("Colors + Varnish", self.job.get('colorsVarnish', 'N/A')),
            ("Printing Plate ID", self.job.get('plateId', 'N/A')),
            ("Color Count (Col)", self.job.get('colValue', 'N/A')),
            ("Core / Size", f"{self.job.get('core', 'N/A')} / {self.job.get('size', 'N/A')}")
        ]
        
        for i, (label, val) in enumerate(metrics):
            grid1.addWidget(self._create_data_box(label, str(val)), i // 2, i % 2)
        content_layout.addLayout(grid1)

        # Section: Lifecycle & Planning
        content_layout.addWidget(self._create_section_title("LIFECYCLE & PLANNING INTELLIGENCE"))
        grid2 = QGridLayout()
        grid2.setSpacing(15)
        
        planning = [
            ("Order Status Code", self.job.get('orderStatus', 'N/A')),
            ("Current Progress", f"{self.job.get('progress', '0')}%" if self.job.get('progress') else "0%"),
            ("PJC Entered (In)", self.job.get('pjcIn', 'N/A')),
            ("Customer Promised Delivery", self.job.get('deliveryDate', 'N/A')),
            ("Actual Started At", self.job.get('startedAt', 'Not Started')),
            ("Actual Completed At", self.job.get('completedAt', 'Pending'))
        ]
        
        for i, (label, val) in enumerate(planning):
            grid2.addWidget(self._create_data_box(label, str(val)), i // 2, i % 2)
        content_layout.addLayout(grid2)

        # Section: Revenue Impact
        content_layout.addWidget(self._create_section_title("STRATEGIC REVENUE IMPACT"))
        grid3 = QGridLayout()
        grid3.setSpacing(15)
        
        rev = float(str(self.job.get('totalAmt', 0)).replace(',', '').replace('MUR', '') or 0)
        time = float(self.job.get('mcTime', 1) or 1)
        grid3.addWidget(self._create_data_box("Cumulative Revenue Value", f"MUR {int(rev):,}" if rev else "MUR 0"), 0, 0)
        grid3.addWidget(self._create_data_box("Production Revenue Velocity", f"MUR {int(rev/time):,}/Hr" if rev else "TBD"), 0, 1)
        content_layout.addLayout(grid3)

        # Section: Executive Notes
        notes = (self.job.get('notes') or '').strip()
        if notes:
            content_layout.addWidget(self._create_section_title("EXECUTIVE PRODUCTION NOTES"))
            notes_box = self._create_data_box("Notes Content", notes)
            content_layout.addWidget(notes_box)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        # 3. Footer Action
        footer = QFrame()
        footer.setStyleSheet(f"background-color: {DARK_PALETTE['surface']}; border: none; border-top: 1px solid {DARK_PALETTE['border']};")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 15, 20, 15)
        
        close_btn = QPushButton("CLOSE INTELLIGENCE VIEW")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DARK_PALETTE['primary']}22;
                border: 1px solid {DARK_PALETTE['primary']};
                color: {DARK_PALETTE['primary']};
                padding: 10px 20px;
                font-weight: 900;
                font-size: 11px;
                border-radius: 8px;
            }}
            QPushButton:hover {{ background-color: {DARK_PALETTE['primary']}; color: {DARK_PALETTE['background']}; }}
        """)
        close_btn.clicked.connect(self.accept)
        footer_layout.addStretch()
        footer_layout.addWidget(close_btn)
        main_layout.addWidget(footer)

    def _create_section_title(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {DARK_PALETTE['primary']}; font-weight: 900; font-size: 11px; letter-spacing: 1.5px;")
        return lbl

    def _create_data_box(self, label, value):
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {DARK_PALETTE['surface']}; border-radius: 12px; border: 1px solid {DARK_PALETTE['border']};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 12, 15, 12)
        
        l_lbl = QLabel(label)
        l_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: 800; text-transform: uppercase;")
        layout.addWidget(l_lbl)
        
        v_lbl = QLabel(value)
        v_lbl.setWordWrap(True)
        v_lbl.setStyleSheet("color: #f1f5f9; font-size: 13px; font-weight: 700;")
        layout.addWidget(v_lbl)
        
        return frame
