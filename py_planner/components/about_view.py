from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QHBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap

class AboutView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # Scroll Area for long content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter) # Center vertically
        container_layout.setSpacing(30)
        container_layout.setContentsMargins(50, 20, 50, 50)

        # Header Section
        header = QLabel("PRINTFLOW PRO")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 32px; font-weight: 900; color: #38bdf8; letter-spacing: 2px;")
        container_layout.addWidget(header)

        version_label = QLabel("Version 3.9.0 - Titanium Performance Engine")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("font-size: 14px; color: #94a3b8; font-weight: 600;")
        container_layout.addWidget(version_label)

        # Info Cards
        info_outer = QHBoxLayout()
        info_outer.addStretch()
        info_layout = QHBoxLayout()
        info_layout.setSpacing(20)

        def create_info_card(title, value):
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: #181c33;
                    border: 1px solid #232a4e;
                    border-radius: 12px;
                    padding: 20px;
                }
            """)
            card_layout = QVBoxLayout(card)
            t_label = QLabel(title.upper())
            t_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t_label.setStyleSheet("color: #94a3b8; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
            v_label = QLabel(value)
            v_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v_label.setStyleSheet("color: #f1f5f9; font-size: 16px; font-weight: 700;")
            card_layout.addWidget(t_label)
            card_layout.addWidget(v_label)
            return card

        info_layout.addWidget(create_info_card("Developer", "Mohamad Oomer Habib Moussa & CO Prashaant Balaghee & Ashvin Domah"))
        info_layout.addWidget(create_info_card("Developed For", "AWOL LABELLING INDUSTRIES LTD"))
        info_layout.addWidget(create_info_card("Publisher", "Oomer Smart Application"))
        
        info_outer.addLayout(info_layout)
        info_outer.addStretch()
        container_layout.addLayout(info_outer)

        # 1. Technical Architecture Section
        tech_title = QLabel("SYSTEM INFRASTRUCTURE & ARCHITECTURE")
        tech_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tech_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #38bdf8; margin-top: 10px;")
        container_layout.addWidget(tech_title)

        tech_text = """
        <div style="color: #cbd5e1; font-size: 13px; line-height: 1.5; text-align: center;">
            PrintFlow Pro utilizes a <b>high-concurrency architecture</b>. The frontend utilizes <b>PyQt6</b> 
            with a <b>Multi-Threaded Sync Engine</b> that prioritizes UI responsiveness by offloading 
            heavy database operations to background workers.
        </div>
        """
        tech_desc = QLabel(tech_text)
        tech_desc.setWordWrap(True)
        tech_desc.setTextFormat(Qt.TextFormat.RichText)
        container_layout.addWidget(tech_desc)

        # 2. Enhanced Feature Matrix (Multi-column list)
        functions_title = QLabel("PRODUCTION CAPABILITIES & ENGINE FEATURES")
        functions_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        functions_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #10b981; margin-top: 10px;")
        container_layout.addWidget(functions_title)

        functions_text = """
        <table width="100%" cellspacing="10" style="color: #94a3b8; font-size: 13px; text-align: center;">
            <tr>
                <td width="50%" valign="top">
                    <b>• AI Optimization:</b> Sequential job ordering based on setup complexity and machine capacity.
                    <br><b>• Multi-Status Filtering:</b> Advanced Summary Report engine with checkable multi-status aggregation.
                    <br><b>• Robust Date Sync:</b> High-fidelity parsing of "DD-MMM" formats for Production Delivery Dates.
                    <br><b>• Background SQL Sync:</b> Real-time data mirroring using debounced background threading.
                    <br><b>• UI Refresh Batching:</b> Flicker-free table population with optimized widget recycling.
                </td>
                <td width="50%" valign="top">
                    <b>• Atomic SQL Sync:</b> Near-zero latency mirroring of production plans to centralized databases.
                    <br><b>• Drag-to-Fill:</b> Advanced Excel-like cell replication engine with context-aware data cloning.
                    <br><b>• Role-Based Access:</b> Multi-departmental security gateway with dynamic identity filtering.
                    <br><b>• High-Density UI:</b> Custom layout management supporting complex production datasets without lag.
                    <br><b>• Dynamic Gantt:</b> Drag-and-drop scheduling on interactive timeline with holiday awareness.
                </td>
            </tr>
        </table>
        """
        functions_desc = QLabel(functions_text)
        functions_desc.setWordWrap(True)
        functions_desc.setTextFormat(Qt.TextFormat.RichText)
        container_layout.addWidget(functions_desc)

        # 3. Security & Integrity Section
        sec_title = QLabel("SECURITY PROTOCOLS & DATA INTEGRITY")
        sec_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sec_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #f43f5e; margin-top: 10px;")
        container_layout.addWidget(sec_title)

        sec_text = """
        <div style="color: #cbd5e1; font-size: 13px; line-height: 1.5; text-align: center;">
            All data transitions are protected by <b>session-level authorization</b>. The local-to-remote mirror 
            utilizes <b>SQL Transaction Tracing</b> to ensure zero data loss during high-concurrency environments. 
            Access levels are strictly enforced via the <b>Identity Filtering Gateway</b>.
        </div>
        """
        sec_desc = QLabel(sec_text)
        sec_desc.setWordWrap(True)
        sec_desc.setTextFormat(Qt.TextFormat.RichText)
        container_layout.addWidget(sec_desc)

        # 4. Roadmap Section
        road_title = QLabel("PLATFORM ROADMAP (v3.9+)")
        road_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        road_title.setStyleSheet("font-size: 18px; font-weight: 800; color: #a855f7; margin-top: 10px;")
        container_layout.addWidget(road_title)

        road_text = """
        <div style="color: #94a3b8; font-size: 13px; text-align: center;">
            Future updates will include <b>Machine Learning</b> for predictive downtime analysis, 
            <b>Live Mobile Monitoring</b> modules.
        </div>
        <div style="margin-top: 20px; padding: 15px; background: rgba(56, 189, 248, 0.05); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 10px; text-align: center;">
            <b style="color: #38bdf8;">RECENT v3.9 PERFORMANCE & FEATURE UPDATES:</b>
            <div style="color: #cbd5e1; font-size: 12px; margin-top: 10px;">
                Implemented <b>Multi-Status Checkable Filtering</b>. Added <b>Background SQL Synchronization</b>.<br>
                Optimized <b>Table Refresh Performance</b>. Shortened <b>Navigation Tab labels</b>.<br>
                Enhanced <b>Packing & Delivery</b> department integration workflow.
            </div>
        </div>
        """
        road_desc = QLabel(road_text)
        road_desc.setWordWrap(True)
        road_desc.setTextFormat(Qt.TextFormat.RichText)
        container_layout.addWidget(road_desc)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
