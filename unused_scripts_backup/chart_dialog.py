from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
from PyQt6.QtCore import Qt

class ChartDialog(QDialog):
    def __init__(self, title, chart_widget_creator, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(1000, 700)
        self.setStyleSheet("background-color: #111122;")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
        header = QHBoxLayout()
        t = QLabel(title)
        t.setStyleSheet("color: #f1f5f9; font-size: 20px; font-weight: 800; background: transparent;")
        header.addWidget(t)
        header.addStretch()
        
        close_btn = QPushButton("CLOSE")
        close_btn.setFixedSize(80, 32)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border-radius: 8px;
                font-weight: 800;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #334155; color: white; }
        """)
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        
        layout.addLayout(header)
        
        # Chart Content
        content_frame = QFrame()
        content_frame.setStyleSheet("background-color: #181c33; border-radius: 20px; border: 1px solid #232a4e;")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # Create a new version of the chart for the dialog
        self.chart = chart_widget_creator()
        if self.chart:
            # Adjust min height for dialog
            self.chart.setMinimumHeight(500)
            content_layout.addWidget(self.chart)
        
        layout.addWidget(content_frame)
        self.showMaximized()
