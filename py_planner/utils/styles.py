# Geckoboard-Inspired Premium Dark Styles for Production Planner

DARK_PALETTE = {
    "background": "#111122", # Deep Navy
    "surface": "#181c33",    # Card Background
    "primary": "#38bdf8",    # Electric Cyan
    "secondary": "#94a3b8",  # Muted Slate
    "accent": "#fbbf24",     # Vivid Yellow
    "text": "#f1f5f9",       # Soft White
    "border": "#232a4e",     # Subtle Border
    "success": "#34d399",    # Emerald
    "danger": "#f43f5e",     # Rose
    "header_bg": "#111122"
}

LIGHT_PALETTE = {
    "background": "#ffffff", # Pure White
    "surface": "#f8fafc",    # Very Light Gray
    "text": "#000000",       # Deep Black
    "border": "#e2e8f0",     # Reverted to subtle blue-gray
    "primary": "#0284c7",    # Sky Blue (Darker for Contrast)
    "secondary": "#475569",  # Darker Slate
    "accent": "#d97706",     # Amber
    "success": "#16a34a",    # Green
    "danger": "#dc2626"      # Red
}

QSS_STYLES = f"""
QMainWindow {{
    background-color: {DARK_PALETTE['background']};
}}

QWidget {{
    color: {DARK_PALETTE['text']};
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}}

QFrame#TopNav {{
    background-color: {DARK_PALETTE['header_bg']};
    border-bottom: 1px solid {DARK_PALETTE['border']};
}}

QPushButton#TabItem {{
    padding: 10px 14px;
    background-color: transparent;
    color: rgba(255, 255, 255, 0.5);
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}}

QPushButton#TabItem:hover {{
    color: #ffffff;
}}

QPushButton#TabItem:checked {{
    color: {DARK_PALETTE['primary']};
    border-bottom: 2px solid {DARK_PALETTE['primary']};
}}

QPushButton {{
    background-color: {DARK_PALETTE['surface']};
    color: {DARK_PALETTE['text']};
    border: 1px solid {DARK_PALETTE['border']};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 700;
}}

QPushButton:hover {{
    background-color: #232a4e;
    border-color: {DARK_PALETTE['primary']};
}}

QPushButton#PrimaryAction {{
    background-color: {DARK_PALETTE['primary']};
    color: #ffffff;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 900;
    font-size: 11px;
    text-transform: uppercase;
    border: none;
}}

QPushButton#PrimaryAction:hover {{
    background-color: #7dd3fc;
}}

/* Scrollbar Visibility Fix (Dark Theme) */
QScrollBar:vertical {{
    background-color: {DARK_PALETTE['background']};
    width: 14px;
    margin: 15px 3px 15px 3px;
    border: 1px solid {DARK_PALETTE['border']};
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: {DARK_PALETTE['primary']};
    min-height: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #7dd3fc;
}}

QScrollBar:horizontal {{
    background-color: {DARK_PALETTE['background']};
    height: 14px;
    margin: 3px 15px 3px 15px;
    border: 1px solid {DARK_PALETTE['border']};
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: {DARK_PALETTE['primary']};
    min-width: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #7dd3fc;
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    border: none;
    background: none;
}}

QTableWidget {{
    background-color: {DARK_PALETTE['background']};
    alternate-background-color: rgba(255, 255, 255, 0.02);
    border: 1px solid {DARK_PALETTE['border']};
    gridline-color: {DARK_PALETTE['border']};
    selection-background-color: #0ea5e9;
    selection-color: #ffffff;
    border-radius: 12px;
}}

QTableWidget::item:selected {{
    background-color: #0ea5e9;
    color: #ffffff;
}}

QTableWidget::item:selected:!active {{
    background-color: #0ea5e9;
    color: #ffffff;
}}

QTableWidget QWidget {{
    background-color: {DARK_PALETTE['background']};
}}

QHeaderView::section {{
    background-color: {DARK_PALETTE['background']};
    color: {DARK_PALETTE['secondary']};
    padding: 5px;
    border: none;
    border-bottom: 1px solid {DARK_PALETTE['border']};
    font-weight: 900;
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.5px;
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: {DARK_PALETTE['background']};
    border: 1px solid {DARK_PALETTE['border']};
    border-radius: 8px;
    padding: 10px;
    color: {DARK_PALETTE['text']};
}}

QComboBox QAbstractItemView {{
    background-color: {DARK_PALETTE['surface']};
    color: {DARK_PALETTE['text']};
    selection-background-color: {DARK_PALETTE['primary']};
    selection-color: #111122;
    border: 1px solid {DARK_PALETTE['border']};
    outline: none;
}}

QTableCornerButton::section {{
    background-color: {DARK_PALETTE['background']};
    border: none;
}}

/* Professional styling for pop-ups (QMessageBox) */
QMessageBox {{
    background-color: #ffffff;
}}

QMessageBox QLabel {{
    color: #000000;
}}

QMessageBox QPushButton {{
    background-color: #f1f5f9;
    color: #000000;
    border: 1px solid #cbd5e1;
}}

QMessageBox QPushButton:hover {{
    background-color: #cbd5e1;
}}

/* Styling for Input Dialogs */
QInputDialog {{
    background-color: #ffffff;
}}

QInputDialog QLabel {{
    color: #000000;
}}

QInputDialog QLineEdit {{
    background-color: #f8fafc;
    color: #000000;
    border: 1px solid #cbd5e1;
}}

QInputDialog QPushButton {{
    background-color: #f1f5f9;
    color: #000000;
    border: 1px solid #cbd5e1;
}}
"""

PLANNER_LIGHT_STYLE = f"""
QTableWidget {{
    background-color: {LIGHT_PALETTE['background']};
    alternate-background-color: #f1f5f9;
    color: {LIGHT_PALETTE['text']};
    border: 1px solid {LIGHT_PALETTE['border']};
    gridline-color: #94a3b8; /* Bolder slate-gray for sharp cell definition */
    selection-background-color: #0284c7;
    selection-color: #ffffff;
    font-size: 13px;
}}

QTableWidget::item:selected {{
    background-color: #0284c7;
    color: #ffffff;
}}

QTableWidget::item:selected:!active {{
    background-color: #0284c7;
    color: #ffffff;
}}

QTableWidget QWidget {{
    background-color: {LIGHT_PALETTE['background']};
    color: {LIGHT_PALETTE['text']};
}}

QHeaderView::section {{
    background-color: #f8fafc;
    color: {LIGHT_PALETTE['secondary']};
    padding: 8px;
    border: none;
    border-bottom: 2px solid {LIGHT_PALETTE['border']};
    border-right: 1px solid {LIGHT_PALETTE['border']};
    font-weight: 800;
    text-transform: uppercase;
    font-size: 11px;
}}

QTableCornerButton::section {{
    background-color: #f8fafc;
    border: none;
}}

QComboBox {{
    background-color: #ffffff;
    border: 1px solid {LIGHT_PALETTE['border']};
    border-radius: 4px;
    padding: 2px 5px;
    color: {LIGHT_PALETTE['text']};
}}

QComboBox QAbstractItemView {{
    background-color: #ffffff;
    color: {LIGHT_PALETTE['text']};
    selection-background-color: {LIGHT_PALETTE['primary']};
    selection-color: #ffffff;
    border: 1px solid {LIGHT_PALETTE['border']};
}}

QLabel {{
    color: #ffffff;
}}

/* Scrollbar Visibility Fix (Light Theme) */
QScrollBar:vertical {{
    background-color: #f1f5f9;
    width: 14px;
    margin: 15px 3px 15px 3px;
    border: 1px solid {LIGHT_PALETTE['border']};
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: #94a3b8;
    min-height: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #64748b;
}}

QScrollBar:horizontal {{
    background-color: #f1f5f9;
    height: 14px;
    margin: 3px 15px 3px 15px;
    border: 1px solid {LIGHT_PALETTE['border']};
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: #94a3b8;
    min-width: 30px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #64748b;
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    border: none;
    background: none;
}}
"""
