from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtGui import QPainter, QPageLayout, QPageSize, QRegion
from PyQt6.QtCore import QSizeF, QRect, Qt
from PyQt6.QtWidgets import QScrollArea
import os

class PDFGenerator:
    @staticmethod
    def export_widget_to_pdf(widget, file_path):
        """
        Captures the ENTIRE content of a widget (including scrollable areas)
        and saves it to a multi-page PDF if necessary.
        """
        # 1. Identify the actual content to print
        target = widget
        if hasattr(widget, "scroll") and isinstance(widget.scroll, QScrollArea):
            target = widget.scroll.widget()
        elif isinstance(widget, QScrollArea):
            target = widget.widget()

        if not target:
            return False

        # 2. Setup Printer
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(file_path)
        
        # A4 Landscape is standard for these reports
        page_layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Landscape,
            QSizeF(10, 10, 10, 10), # 10mm margins
            QPageLayout.Unit.Millimeter
        )
        printer.setPageLayout(page_layout)

        painter = QPainter(printer)
        
        # 3. Calculate Scaling and Paging
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
        target_width = target.width()
        scale = page_rect.width() / target_width
        
        painter.scale(scale, scale)
        
        # How much height (in widget pixels) fits on one page?
        fitted_height = page_rect.height() / scale
        total_height = target.height()
        
        # 4. Multi-page Rendering Loop
        current_y = 0
        while current_y < total_height:
            # Source rectangle in the widget
            source_rect = QRect(0, int(current_y), int(target_width), int(fitted_height))
            
            # Render the slice
            target.render(painter, targetOffset=Qt.AlignmentFlag.AlignTop, sourceRegion=QRegion(source_rect))
            
            current_y += fitted_height
            
            # If there's more content, start a new page
            if current_y < total_height:
                printer.newPage()
                # Scaling is reset on new page in some PyQt versions, so we re-apply just in case
                # Actually QPrinter/QPainter state persists usually, but we move our coordinate system
                painter.translate(0, -fitted_height)

        painter.end()
        return os.path.exists(file_path)
