from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QPushButton, QHBoxLayout, QLabel, QComboBox, 
                             QProgressBar, QMenu, QInputDialog, QMessageBox, QApplication, 
                             QAbstractItemView, QFrame, QColorDialog, QTableWidgetSelectionRange,
                             QCheckBox, QGridLayout)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint
from PyQt6.QtGui import QColor, QFont, QAction, QKeyEvent, QKeySequence
import json
import copy
from datetime import datetime, timedelta
import threading
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QDateTime
from ..utils.styles import PLANNER_LIGHT_STYLE
from floor_view.api import api_service
from floor_view.api import sql_service
import sys

class PJCBackgroundWorker(QThread):
    """Background worker to fetch PJC data from SQL without blocking UI."""
    result_ready = pyqtSignal(dict, dict) # sql_data, job_obj

    def __init__(self, pjc, job_obj, sql_config):
        super().__init__()
        self.pjc = pjc
        self.job_obj = job_obj
        self.sql_config = sql_config

    def run(self):
        try:
            from floor_view.api import sql_service, api_service
            api_service.log_to_file(f"DEBUG: PJC Background Worker thread STARTING for {self.pjc}...")
            
            sync_src = self.sql_config.get("syncSource") or self.sql_config.get("sync_source", "sql")
            api_mode = (sync_src == "api") or self.sql_config.get("apiEnabled", False)
            sql_data = {}
            
            api_service.log_to_file(f"DEBUG: Worker {self.pjc} | Mode: {'API' if api_mode else 'SQL'}")
            
            if api_mode:
                # 1. Fetch via API
                api_service.log_to_file(f"DEBUG: PJC Background Worker using LABELTRAXX API for {self.pjc}")
                sql_data = api_service.get_job_from_api(self.pjc, self.sql_config) or {}
            else:
                # 1. Fetch main job data via SQL
                api_service.log_to_file(f"DEBUG: PJC Background Worker using SQL for {self.pjc}")
                results = sql_service.get_bulk_job_data([self.pjc], self.sql_config)
                sql_data = results[0] if results else {}
            
            if sql_data:
                api_service.log_to_file(f"DEBUG: Worker {self.pjc} SUCCESS. Result keys: {list(sql_data.keys())}")
                self.result_ready.emit(sql_data, self.job_obj)
            else:
                api_service.log_to_file(f"DEBUG: No data found for PJC {self.pjc}")
        except RuntimeError as e:
            from floor_view.api import api_service
            api_service.log_to_file(f"NOTICE: Background Fetch Timeout/Error for {self.pjc}: {e}")
            # Don't emit result if failed to avoid overwriting with empty
        except Exception as e:
            from floor_view.api import api_service
            api_service.log_to_file(f"CRITICAL: Background Fetch Error for {self.pjc}: {e}")
            import traceback
            api_service.log_to_file(traceback.format_exc())


class StatusBackgroundWorker(QThread):
    """Background worker to fetch current statuses via API for all visible jobs."""
    statuses_ready = pyqtSignal(dict) # { "PJC": "translated_status" }

    def __init__(self, pjc_list, sql_config):
        super().__init__()
        self.pjc_list = [str(p).strip() for p in pjc_list if p and str(p).strip() != "NEW"]
        self.sql_config = sql_config

    def run(self):
        if not self.pjc_list:
            return
            
        try:
            from floor_view.api import api_service
            # The user explicitly wants ONLY the API GET request
            api_service.log_to_file(f"STATUS WORKER: Polling API for {len(self.pjc_list)} jobs...")
            
            # Fetch statuses in bulk via API
            raw_results = api_service.get_live_job_statuses(self.pjc_list, self.sql_config)
            
            # Extract just the status string from the API result Dict
            clean_results = {}
            for pjc, data in raw_results.items():
                if isinstance(data, dict):
                    clean_results[pjc] = data.get("status", "not_started")
                else:
                    clean_results[pjc] = str(data)
            
            if clean_results:
                self.statuses_ready.emit(clean_results)
                
        except Exception as e:
            from floor_view.api import api_service
            api_service.log_to_file(f"STATUS WORKER ERROR: {e}")



class PlanningTable(QTableWidget):
    """
    Subclassed QTableWidget to handle Drag-and-Drop and professional Excel-like features.
    """
    # Global internal clipboard to store job objects for cross-machine migration
    INTERNAL_CLIPBOARD = []
    CLIPBOARD_MODE = "COPY"  # "COPY" or "CUT"
    SOURCE_MACHINE = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.setWordWrap(True)
        self.setTextElideMode(Qt.TextElideMode.ElideNone) # Prevent "..." if possible, wrap instead
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setWordWrap(True)
        self.verticalHeader().setDefaultSectionSize(40)
        self.setStyleSheet("gridline-color: #232a4e;")
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        
        # Check if parent is a viewer to disable editing globally
        self.is_viewer_mode = False
        if parent and hasattr(parent, 'current_user'):
            role = str(parent.current_user.get("role", "")).lower()
            if role in ["viewer", "pre-press dep."]:
                self.is_viewer_mode = True
                self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                self.setDragEnabled(False)
                self.setAcceptDrops(False)
        
        # Undo/Redo Stacks (Delegated to Parent Board)
        pass

        # Drag-to-Fill State
        self._is_filling = False
        self._fill_start_cell = None  # (row, col)
        self._fill_current_cells = [] # List of (row, col)

    def wheelEvent(self, event):
        if hasattr(self.parent(), 'is_viewer') and self.parent().is_viewer():
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                zoom_step = 0.1 if delta > 0 else -0.1
                if hasattr(self.parent(), 'apply_zoom'):
                    self.parent().apply_zoom(zoom_step)
                event.accept()
                return
            super().wheelEvent(event)
            return

        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            zoom_step = 0.1 if delta > 0 else -0.1
            if hasattr(self.parent(), 'apply_zoom'):
                self.parent().apply_zoom(zoom_step)
            event.accept()
        else:
            super().wheelEvent(event)

    def save_state(self):
        """Delegates state saving to the parent PlanningBoard."""
        pb = self.parent()
        if pb and hasattr(pb, 'save_state'):
            pb.save_state()

    def undo(self):
        """Delegates undo to the parent PlanningBoard."""
        pb = self.parent()
        if pb and hasattr(pb, 'undo'):
            pb.undo()

    def redo(self):
        """Delegates redo to the parent PlanningBoard."""
        pb = self.parent()
        if pb and hasattr(pb, 'redo'):
            pb.redo()

    def keyPressEvent(self, event: QKeyEvent):
        if self.is_viewer_mode:
            # Still allow navigation (Arrows, PgUp/Down, Ctrl+C) but block all editing keys
            allowed_keys = [
                Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
                Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End,
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab
            ]
            if event.matches(QKeySequence.StandardKey.Copy):
                super().keyPressEvent(event)
                return
            if event.key() not in allowed_keys:
                event.ignore()
                return
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()

        # Undo / Redo
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Z:
            self.undo()
            return
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Y:
            self.redo()
            return

        # Basic Selection
        if modifiers == Qt.KeyboardModifier.ShiftModifier and key == Qt.Key.Key_Space:
            self.selectRow(self.currentRow())
            return
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Space:
            self.selectColumn(self.currentColumn())
            return
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_A:
            self.selectAll()
            return

        # Clipboard
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste_selection()
            return
        elif event.matches(QKeySequence.StandardKey.Cut):
            self.cut_selection()
            return
        elif modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier) and key == Qt.Key.Key_V:
            self.paste_special_transpose()
            return

        # Clear Selection (Delete / Backspace)
        if key in [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]:
            if self.state() != QAbstractItemView.State.EditingState:
                items = self.selectedItems()
                if items:
                    pb = self.parent()
                    self.save_state()
                    self.blockSignals(True)
                    if pb: pb._is_batch_updating = True
                    
                    for item in items:
                        try:
                            item.setText("")
                            if pb and hasattr(pb, 'on_item_changed'):
                                pb.on_item_changed(item)
                        except (RuntimeError, AttributeError):
                            continue
                            
                    if pb:
                        pb._is_batch_updating = False
                        pb.run_optimizer()
                            
                    self.blockSignals(False)
                    if pb and hasattr(pb, 'save_data'):
                        pb.save_data()
                return

        # Row/Col Management
        if modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) and key == Qt.Key.Key_Plus:
            self.parent().add_row(self.currentRow() - 1)
            return
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_Minus:
            self.parent().delete_row()
            return
        
        # Hide/Unhide
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_9:
            self.setRowHidden(self.currentRow(), True)
            return
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_0:
            self.setColumnHidden(self.currentColumn(), True)
            return
        if modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) and key == Qt.Key.Key_9:
            for i in range(self.rowCount()): self.setRowHidden(i, False)
            return
        if modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) and key == Qt.Key.Key_0:
            for i in range(self.columnCount()): self.setColumnHidden(i, False)
            return

        # Navigation & Entry
        if key == Qt.Key.Key_F2:
            self.editItem(self.currentItem())
            return
        if modifiers == Qt.KeyboardModifier.AltModifier and key == Qt.Key.Key_Return:
            item = self.currentItem()
            if item: item.setText(item.text() + "\n")
            return
        
        # Jump to edge (Ctrl + Arrows)
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_Up: self.jump_to_edge('up'); return
            if key == Qt.Key.Key_Down: self.jump_to_edge('down'); return
            if key == Qt.Key.Key_Left: self.jump_to_edge('left'); return
            if key == Qt.Key.Key_Right: self.jump_to_edge('right'); return

        # Flash Fill (Ctrl + E)
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_E:
            self.flash_fill()
            return

        # Horizontal Tab Navigation (Excel-like) handled by focusNextPrevChild

        # Enter/Return moves to the next row (Excel-like behavior)
        if key in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            curr_row = self.currentRow()
            curr_col = self.currentColumn()
            
            # 1. Let the base class handle the Enter key first (commits data)
            super().keyPressEvent(event)
            
            def move_and_edit():
                pb = self.parent()
                if not pb or not hasattr(pb, 'all_machines_data'):
                    return
                
                mc = pb.all_machines_data.get(pb.current_machine, {})
                visible_jobs = [j for j in mc.get("jobs", []) if j.get("visible", True)]
                
                if curr_row == len(visible_jobs) - 1:
                    pb.add_row(target_col=curr_col, auto_edit=True)
                else:
                    self.setCurrentCell(curr_row + 1, curr_col)
                    # Start editing immediately for a seamless feel
                    item = self.currentItem()
                    if item:
                        self.editItem(item)

            # Defer so the commit process finishes completely
            QTimer.singleShot(70, move_and_edit)
            return

        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        """Detects click on the bottom-right corner 'Fill Handle'."""
        if self.is_viewer_mode:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                # Calculate if click is in the bottom-right corner (10x10 pixels)
                cell_rect = self.visualItemRect(item)
                handle_size = 10
                corner_rect = cell_rect.adjusted(cell_rect.width() - handle_size, cell_rect.height() - handle_size, 0, 0)
                
                if corner_rect.contains(event.pos()):
                    self._is_filling = True
                    self._fill_start_cell = (item.row(), item.column())
                    self._fill_current_cells = [self._fill_start_cell]
                    self.setCursor(Qt.CursorShape.CrossCursor)
                    # Don't call super() to prevent selection change
                    event.accept()
                    return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Updates the fill range highlight while dragging."""
        if self._is_filling:
            item = self.itemAt(event.pos())
            if item:
                start_row, start_col = self._fill_start_cell
                curr_row, curr_col = item.row(), item.column()
                
                # Currently we only support vertical fill for Excel feel
                new_cells = []
                r_step = 1 if curr_row >= start_row else -1
                for r in range(start_row, curr_row + r_step, r_step):
                    new_cells.append((r, start_col))
                
                if new_cells != self._fill_current_cells:
                    self._fill_current_cells = new_cells
                    # Visually highlight the range using selection
                    self.blockSignals(True)
                    self.clearSelection()
                    for r, c in self._fill_current_cells:
                        self.setRangeSelected(QTableWidgetSelectionRange(r, c, r, c), True)
                    self.blockSignals(False)
            event.accept()
            return
            
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Finalizes the fill operation and copies data."""
        if self._is_filling:
            self._is_filling = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
            if len(self._fill_current_cells) > 1:
                self.save_state()
                start_row, start_col = self._fill_start_cell
                source_item = self.item(start_row, start_col)
                source_text = source_item.text() if source_item else ""
                
                pb = self.parent()
                self.blockSignals(True)
                for r, c in self._fill_current_cells:
                    if r == start_row: continue # Skip source
                    
                    # Create or update item
                    target_item = self.item(r, c)
                    if not target_item:
                        target_item = QTableWidgetItem(source_text)
                        self.setItem(r, c, target_item)
                    else:
                        target_item.setText(source_text)
                    
                    # Sync to underlying model
                    if pb and hasattr(pb, 'on_item_changed'):
                        pb.on_item_changed(target_item)
                
                self.blockSignals(False)
                if pb and hasattr(pb, 'save_data'):
                    pb.save_data()
            
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def focusNextPrevChild(self, next_in_order):
        """Intercepts focus changes to handle seamless cross-table Tab navigation."""
        pb = self.parent()
        if not pb or not hasattr(pb, 'table') or not hasattr(pb, 'frozen_table'):
            return super().focusNextPrevChild(next_in_order)

        col = self.currentColumn()
        
        # Forward Tab at the end of frozen table or main table column
        if next_in_order:
            if (self == pb.frozen_table and col == self.columnCount() - 1) or \
               (self == pb.table and col == self.columnCount() - 1):
                # Only handle if we aren't already in the middle of a transition
                if not getattr(self, '_in_tab_transition', False):
                    self.navigate_horizontal(forward=True)
                    return True
        # Backward Shift+Tab at the start of main table or frozen table
        else:
            if (self == pb.table and col == 0) or \
               (self == pb.frozen_table and col == 0):
                if not getattr(self, '_in_tab_transition', False):
                    self.navigate_horizontal(forward=False)
                    return True
        
        return super().focusNextPrevChild(next_in_order)

    def navigate_horizontal(self, forward=True):
        """Fixes lag and data loss by committing data before handover and avoiding full refreshes."""
        pb = self.parent()
        if not pb or not hasattr(pb, 'all_machines_data'): return
        
        # 1. Force the current editor (if any) to submit its value to the model
        self.commitData(self.viewport())
        self.closeEditor(self.currentItem() or QWidget(), QAbstractItemView.EndEditHint.SubmitModelCache)
        
        row, col = self.currentRow(), self.currentColumn()
        is_frozen = (self == pb.frozen_table)
        
        target_table = self
        target_row = row
        target_col = col
        
        if forward:
            if is_frozen:
                if col < self.columnCount() - 1:
                    target_col = col + 1
                else:
                    target_table = pb.table
                    target_col = 0
            else:
                if col < self.columnCount() - 1:
                    target_col = col + 1
                else:
                    if row < self.rowCount() - 1:
                        target_table = pb.frozen_table
                        target_row = row + 1
                        target_col = 0
        else: # Backward
            if is_frozen:
                if col > 0:
                    target_col = col - 1
                else:
                    if row > 0:
                        target_table = pb.table
                        target_row = row - 1
                        target_col = target_table.columnCount() - 1
            else:
                if col > 0:
                    target_col = col - 1
                else:
                    target_table = pb.frozen_table
                    target_col = target_table.columnCount() - 1
        
        # Mark transition start
        self._in_tab_transition = True
        if target_table != self:
            target_table._in_tab_transition = True
            self.clearSelection() # Clean transition visuals
            
        target_table.setCurrentCell(target_row, target_col)
        target_table.setFocus(Qt.FocusReason.TabFocusReason)
        target_table.scrollToItem(target_table.item(target_row, target_col))
        
        # Use a slightly longer delay (50ms) to allow the table state to settle after commitData
        def auto_focus_or_edit():
            self._in_tab_transition = False
            target_table._in_tab_transition = False
            
            widget = target_table.cellWidget(target_row, target_col)
            if widget:
                widget.setFocus(Qt.FocusReason.TabFocusReason)
                return
            
            item = target_table.item(target_row, target_col)
            if item:
                target_table.editItem(item)
                
        QTimer.singleShot(50, auto_focus_or_edit)


    def jump_to_edge(self, direction):
        row, col = self.currentRow(), self.currentColumn()
        if direction == 'up':
            while row > 0 and self.item(row-1, col) and self.item(row-1, col).text(): row -= 1
        elif direction == 'down':
            while row < self.rowCount()-1 and self.item(row+1, col) and self.item(row+1, col).text(): row += 1
        elif direction == 'left':
            while col > 0 and self.item(row, col-1) and self.item(row, col-1).text(): col -= 1
        elif direction == 'right':
            while col < self.columnCount()-1 and self.item(row, col+1) and self.item(row, col+1).text(): col += 1
        self.setCurrentCell(row, col)

    def flash_fill(self):
        """Simple pattern recognition (linear increment or repetition)."""
        row, col = self.currentRow(), self.currentColumn()
        if row < 1: return
        item1, item2 = self.item(row-1, col), self.item(row, col)
        if not item1 or not item2: return
        
        t1, t2 = item1.text(), item2.text()
        self.save_state()
        try:
            v1, v2 = float(t1), float(t2)
            diff = v2 - v1
            for i in range(row + 1, self.rowCount()):
                v2 += diff
                self.setItem(i, col, QTableWidgetItem(f"{v2:g}"))
        except:
            for i in range(row + 1, self.rowCount()):
                self.setItem(i, col, QTableWidgetItem(t2))
        self.parent().save_data()

    def copy_selection(self):
        selection = self.selectedRanges()
        if not selection: return
        
        # 1. Standard text clipboard for external apps
        rows = []
        for r in range(selection[0].topRow(), selection[0].bottomRow() + 1):
            row_data = [self.item(r, c).text() if self.item(r, c) else "" for c in range(selection[0].leftColumn(), selection[0].rightColumn() + 1)]
            rows.append("\t".join(row_data))
        QApplication.clipboard().setText("\n".join(rows))

        # 2. Internal job-based clipboard for migration
        PlanningTable.INTERNAL_CLIPBOARD = []
        PlanningTable.CLIPBOARD_MODE = "COPY"
        PlanningTable.SOURCE_MACHINE = getattr(self.parent(), 'current_machine', None)
        
        selected_rows = sorted(list(self.parent().get_selected_rows()))
        visible_jobs = self.parent().get_visible_jobs()
        
        for r in selected_rows:
            if r < len(visible_jobs):
                # Deep copy to avoid mutating the original until cut is pasted
                PlanningTable.INTERNAL_CLIPBOARD.append(copy.deepcopy(visible_jobs[r]))


    def paste_selection(self):
        self.save_state()
        
        # Priority 1: Internal Job Clipboard
        if PlanningTable.INTERNAL_CLIPBOARD:
            pb = self.parent()
            dest_mc = pb.all_machines_data[pb.current_machine]
            target_row = self.currentRow()
            
            # Deep copy back to avoid linkage
            jobs_to_insert = [copy.deepcopy(j) for j in PlanningTable.INTERNAL_CLIPBOARD]
            
            # If CUT, we need to remove from source if source is same OR different
            if PlanningTable.CLIPBOARD_MODE == "CUT" and PlanningTable.SOURCE_MACHINE:
                src_mc = pb.all_machines_data.get(PlanningTable.SOURCE_MACHINE)
                if src_mc:
                    for j_to_rem in PlanningTable.INTERNAL_CLIPBOARD:
                        # Match by ID to ensure we remove the correct job
                        src_mc["jobs"] = [j for j in src_mc["jobs"] if j.get("id") != j_to_rem.get("id")]
                PlanningTable.INTERNAL_CLIPBOARD = [] # Clear after cut
            
            # Insert at target
            visible_jobs = pb.get_visible_jobs()
            if target_row >= 0 and target_row < len(visible_jobs):
                ref_job = visible_jobs[target_row]
                master_idx = dest_mc["jobs"].index(ref_job)
                for i, job in enumerate(jobs_to_insert):
                    dest_mc["jobs"].insert(master_idx + i, job)
            else:
                dest_mc["jobs"].extend(jobs_to_insert)
                
            pb.save_data()
            pb.refresh_table()
            return

        # Priority 2: Standard Text Clipboard
        text = QApplication.clipboard().text()
        rows = text.split("\n")
        curr_row, curr_col = self.currentRow(), self.currentColumn()
        
        pb = self.parent()
        if pb: pb._is_batch_updating = True
        
        for r_idx, row_text in enumerate(rows):
            if not row_text.strip(): continue
            cols = row_text.split("\t")
            for c_idx, col_text in enumerate(cols):
                if curr_row + r_idx < self.rowCount() and curr_col + c_idx < self.columnCount():
                    self.setItem(curr_row + r_idx, curr_col + c_idx, QTableWidgetItem(col_text))
                    
        if pb:
            pb._is_batch_updating = False
            pb.run_optimizer()
            
        self.parent().save_data()


    def paste_special_transpose(self):
        self.save_state()
        text = QApplication.clipboard().text()
        rows = [r.split("\t") for r in text.split("\n") if r.strip()]
        transposed = list(zip(*rows))
        curr_row, curr_col = self.currentRow(), self.currentColumn()
        
        pb = self.parent()
        if pb: pb._is_batch_updating = True
        
        for r_idx, row_data in enumerate(transposed):
            for c_idx, val in enumerate(row_data):
                if curr_row + r_idx < self.rowCount() and curr_col + c_idx < self.columnCount():
                    self.setItem(curr_row + r_idx, curr_col + c_idx, QTableWidgetItem(val))
                    
        if pb:
            pb._is_batch_updating = False
            pb.run_optimizer()
            
        self.parent().save_data()

    def cut_selection(self):
        self.copy_selection()
        PlanningTable.CLIPBOARD_MODE = "CUT"
        # We don't delete immediately; we wait for Paste or move to verify


    def set_row_color(self):
        selected_rows = self.parent().get_selected_rows()
        if not selected_rows: return
            
        color = QColorDialog.getColor()
        if color.isValid():
            self.parent().set_row_color(list(selected_rows), color.name())

    def clear_row_color(self):
        selected_rows = self.parent().get_selected_rows()
        if not selected_rows: return
        self.parent().set_row_color(list(selected_rows), None)

    def show_context_menu(self, pos):
        if self.is_viewer_mode:
            return
        
        menu = QMenu(self)
            
        # Determine the row where the user right-clicked
        item = self.itemAt(pos)
        clicked_row = item.row() if item else self.currentRow()
        
        menu = QMenu()
        menu.addAction("Undo (Ctrl+Z)", self.undo)
        menu.addAction("Redo (Ctrl+Y)", self.redo)
        menu.addSeparator()
        menu.addAction("Copy", self.copy_selection)
        menu.addAction("Paste", self.paste_selection)
        menu.addAction("Paste Transpose", self.paste_special_transpose)
        menu.addSeparator()
        
        # Move to Machine Submenu
        move_menu = menu.addMenu("Move to Another Machine")
        pb = self.parent()
        if pb and hasattr(pb, 'all_machines_data'):
            for mc_name in sorted(pb.all_machines_data.keys()):
                if mc_name != pb.current_machine:
                    move_menu.addAction(mc_name, lambda m=mc_name: pb.move_selected_jobs_to_machine(m))
        
        menu.addSeparator()
        menu.addAction("Insert Row", lambda: self.parent().add_row(clicked_row))
        menu.addAction("Add Maintenance / Downtime", lambda: self.parent().add_maintenance(clicked_row))
        menu.addAction("Delete Row", self.parent().delete_row)
        menu.addSeparator()
        menu.addAction("Set Row Color", self.set_row_color)
        menu.addAction("Clear Row Color", self.clear_row_color)
        menu.exec(self.viewport().mapToGlobal(pos))

    def dropEvent(self, event):
        if hasattr(self.parent(), 'is_viewer') and self.parent().is_viewer():
            event.ignore()
            return

        if event.source() == self:
            rows = sorted(set(item.row() for item in self.selectedItems()))
            target_row = self.indexAt(event.position().toPoint()).row()
            self.save_state()
            self.parent().on_rows_moved(rows, target_row)
            event.accept()
        else:
            super().dropEvent(event)

class PlanningBoard(QWidget):
    machine_changed = pyqtSignal(str)
    STATUS_OPTIONS = ["not_started", "in_progress", "completed", "on_hold", "cancelled"]

    def safe_float(self, val):
        """Safely convert a value to float, handling strings with commas or non-numeric characters."""
        if val is None: return 0.0
        try:
            # Remove common non-numeric characters found in the planner (commas, currency markers)
            clean_val = str(val).replace(",", "").replace("MUR", "").replace("%", "").strip()
            return float(clean_val) if clean_val else 0.0
        except (ValueError, TypeError):
            return 0.0

    def save_state(self):
        """Saves current global machine data for undo/redo."""
        state = copy.deepcopy(self.all_machines_data)
        self.undo_stack.append(state)
        self.redo_stack.clear()
        if len(self.undo_stack) > 50: self.undo_stack.pop(0)

    def undo(self):
        """Reverts to the last saved global state."""
        if not self.undo_stack: return
        # Save current state for redo
        self.redo_stack.append(copy.deepcopy(self.all_machines_data))
        # Restore old state (Update in-place to maintain reference to MainWindow.data)
        state = self.undo_stack.pop()
        self.all_machines_data.clear()
        self.all_machines_data.update(state)
        self.refresh_table()
        self.save_data() # Save to persist the undo

    def redo(self):
        """Re-applies the next state in the redo stack."""
        if not self.redo_stack: return
        # Save current state for undo
        self.undo_stack.append(copy.deepcopy(self.all_machines_data))
        # Restore redo state (Update in-place to maintain reference to MainWindow.data)
        state = self.redo_stack.pop()
        self.all_machines_data.clear()
        self.all_machines_data.update(state)
        self.refresh_table()
        self.save_data() # Save to persist the redo

    def __init__(self, all_machines_data, initial_machine, logic, settings=None, current_user=None, save_callback=None, filter_category="production"):
        super().__init__()
        self.all_machines_data = all_machines_data
        self.filter_category = filter_category
        
        # Ensure machines have a category property if missing
        for m_name, m_data in self.all_machines_data.items():
            if "category" not in m_data:
                # Default logic: if it's already in a 'finishing' context, or has no jobs yet, 
                # keep it as production, but let the board decide what to show.
                m_data["category"] = "production"
        self.current_machine = initial_machine
        self.logic = logic
        self.settings = settings or {}
        self.current_user = current_user or {}
        self.save_callback = save_callback
        self.show_calendar = True
        self.zoom_level = 0.7
        self.custom_column_widths = {} # Key: column_key, Value: width
        self._is_refreshing = False # Flag to avoid signal loops
        
        self.undo_stack = []
        self.redo_stack = []
        
        self.status_locks = {} # { "PJC": timestamp } - Prevents SQL heartbeat overwrite
        self.delta_sync_in_progress = False # Flag to prevent multiple delta syncs
        self.delta_worker = None # Reference to the current delta sync worker
        
        # --- Live Status Polling ---
        self.status_sync_timer = QTimer()
        self.status_sync_timer.timeout.connect(self._poll_live_statuses)
        self._is_status_syncing = False
        self._status_worker = None
        
        

        self.show_completed = False
        # Default Visibility: Hide completed jobs on startup
        for machine_name, machine_data in self.all_machines_data.items():
            for job in machine_data.get("jobs", []):
                if job.get("status") == "completed":
                    job["visible"] = self.show_completed
                else:
                    job["visible"] = True

        self.init_ui()
        
        # Batch Update State
        self._is_batch_updating = False
        
        # Startup Optimization: Recalculate schedule based on current settings
        QTimer.singleShot(500, self.run_optimizer)
        
        # Start API Status Polling
        QTimer.singleShot(2000, self.refresh_sync_timers)

    def get_display_columns(self, machine_data):
        """Returns the list of columns to actually display based on category."""
        all_cols = machine_data.get("columns", [])
        
        # Exclude specific technical columns for finishing, packing, and delivery
        if self.filter_category in ["finishing", "packing", "delivery"]:
            excluded_keys = ["gearTeeth", "meters", "width", "orderStatus", "colValue", "colorsVarnish", "plateId", "finishingMachine", "packingMachine", "mcTime"]
            if self.filter_category != "finishing":
                excluded_keys.append("dieCut")
            return [c for c in all_cols if c.get("key") not in excluded_keys]
        
        return all_cols

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        
        toolbar = QHBoxLayout()
        self.machine_selector = QComboBox()
        
        # Filter machines by category
        filtered_machines = [name for name, data in self.all_machines_data.items() if data.get("category", "production") == self.filter_category]
        self.machine_selector.addItems(filtered_machines)
        
        if self.current_machine in filtered_machines:
            self.machine_selector.setCurrentText(self.current_machine)
        elif filtered_machines:
            self.current_machine = filtered_machines[0]
            self.machine_selector.setCurrentText(self.current_machine)
        else:
            # Handle empty category: we need at least one machine usually
            pass

        self.machine_selector.currentTextChanged.connect(self.on_machine_selector_changed)
        
        add_mc_btn = QPushButton("+ Machine")
        add_mc_btn.clicked.connect(self.add_machine)
        rename_mc_btn = QPushButton("Rename")
        rename_mc_btn.clicked.connect(self.rename_machine)
        self.unhide_btn = QPushButton("Unhide Completed")
        self.unhide_btn.clicked.connect(self.toggle_completed_visibility)
        
        user_role = str(self.current_user.get("role", "")).lower()
        is_viewer = user_role == "viewer"
        
        toolbar.addWidget(QLabel("Machine:"))
        toolbar.addWidget(self.machine_selector)
        
        if not is_viewer:
            toolbar.addWidget(add_mc_btn)
            toolbar.addWidget(rename_mc_btn)
            toolbar.addWidget(self.unhide_btn)
            
        toolbar.addStretch()
        
        add_job_btn = QPushButton("+ New Job")
        add_job_btn.clicked.connect(lambda: self.add_row())
        run_opt_btn = QPushButton("Run Optimizer")
        run_opt_btn.setObjectName("PrimaryAction")
        run_opt_btn.clicked.connect(self.run_optimizer)
        self.cal_toggle = QPushButton("Hide Calendar")
        self.cal_toggle.setCheckable(True)
        self.cal_toggle.setChecked(True)
        self.cal_toggle.clicked.connect(self.toggle_calendar)
        
        toolbar.addWidget(self.cal_toggle)
        
        if not is_viewer:
            toolbar.addWidget(add_job_btn)
        
        # Zoom Controls
        zoom_in_btn = QPushButton("Zoom +")
        zoom_in_btn.clicked.connect(lambda: self.apply_zoom(0.1))
        zoom_out_btn = QPushButton("Zoom -")
        zoom_out_btn.clicked.connect(lambda: self.apply_zoom(-0.1))
        zoom_reset_btn = QPushButton("Reset")
        zoom_reset_btn.clicked.connect(self.reset_zoom)
        
        toolbar.addWidget(zoom_in_btn)
        toolbar.addWidget(zoom_out_btn)
        toolbar.addWidget(zoom_reset_btn)
        
        if not is_viewer:
            toolbar.addWidget(run_opt_btn)
            
        self.main_layout.addLayout(toolbar)
        
        # Dual Table for Frozen Columns
        table_container = QHBoxLayout()
        table_container.setSpacing(0)
        
        self.frozen_table = PlanningTable(self)
        self.frozen_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frozen_table.itemChanged.connect(self.on_item_changed)
        
        self.table = PlanningTable(self) # We keep 'self.table' as the main scrollable one to minimize code changes elsewhere
        self.table.itemChanged.connect(self.on_item_changed)
        
        # Sync scrolling
        self.table.verticalScrollBar().valueChanged.connect(self.frozen_table.verticalScrollBar().setValue)
        self.frozen_table.verticalScrollBar().valueChanged.connect(self.table.verticalScrollBar().setValue)
        
        # Restore Row Numbers on Frozen Panel & Fix Header Heights for perfect alignment
        self.frozen_table.verticalHeader().show()
        self.frozen_table.verticalHeader().setFixedWidth(40) # Fixed width for row numbers to prevent jitter
        self.table.verticalHeader().hide()
        
        self.table.horizontalHeader().setFixedHeight(40)
        self.frozen_table.horizontalHeader().setFixedHeight(40)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.frozen_table.verticalHeader().setDefaultSectionSize(40)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.frozen_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        
        self.table.setCornerButtonEnabled(False)
        self.frozen_table.setCornerButtonEnabled(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.frozen_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        
        self.frozen_table.itemSelectionChanged.connect(self.sync_selection_to_main)
        self.table.itemSelectionChanged.connect(self.sync_selection_to_frozen)

        # Persistence for manual column resizing
        self.frozen_table.horizontalHeader().sectionResized.connect(self.on_column_resized)
        self.table.horizontalHeader().sectionResized.connect(self.on_column_resized)

        table_container.addWidget(self.frozen_table)
        table_container.addWidget(self.table)
        self.main_layout.addLayout(table_container)
        
        # Apply light theme to specific components
        self.setStyleSheet(PLANNER_LIGHT_STYLE)
        self.frozen_table.setStyleSheet(PLANNER_LIGHT_STYLE)
        self.table.setStyleSheet(PLANNER_LIGHT_STYLE)
        
        self.footer_label = QLabel()
        self.footer_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self.main_layout.addWidget(self.footer_label)
        
        if self.filter_category in ["finishing", "packing", "delivery"]:
            self.show_calendar = False
        else:
            self.show_calendar = True
        
        self.refresh_table()
            
        # 7. STARTUP OPTIMIZATION: Ensure calendar is populated immediately
        QTimer.singleShot(100, self.run_optimizer)

    def sync_selection_to_main(self):
        self.table.blockSignals(True)
        self.table.clearSelection()
        seen_rows = set()
        for item in self.frozen_table.selectedItems():
            row = item.row()
            if row not in seen_rows:
                self.table.selectRow(row)
                seen_rows.add(row)
        self.table.blockSignals(False)

    def sync_selection_to_frozen(self):
        self.frozen_table.blockSignals(True)
        self.frozen_table.clearSelection()
        seen_rows = set()
        for item in self.table.selectedItems():
            row = item.row()
            if row not in seen_rows:
                self.frozen_table.selectRow(row)
                seen_rows.add(row)
        self.frozen_table.blockSignals(False)

    def format_display_value(self, key, val):
        if val is None or str(val).lower() in ["", "none", "nan", "null"]:
            return ""
        
        # Numeric Columns
        numeric_keys = ["qty", "gearTeeth", "meters", "mcTime", "width", "totalAmt", "totalRevenue", "progress", "colValue"]
        if key in numeric_keys:
            try:
                f_val = self.logic.safe_float(val)
                if f_val == 0 and key not in ["progress", "qty"]: return ""
                
                if key in ["totalAmt", "totalRevenue"]:
                    return f"MUR {f_val:,.2f}"
                elif key in ["qty", "meters", "colValue", "gearTeeth"]:
                    # Round and remove decimal places for specific integer-like columns
                    return f"{int(round(f_val)):,}"
                
                return f"{f_val:,.2f}"
            except:
                return str(val)
            
        # Date Columns
        date_keys = ["deliveryDate", "pjcIn", "prodDeliveryDate", "startedAt", "completedAt"]
        if key in date_keys:
            try:
                dt = self.logic.safe_date(val)
                if dt == datetime.min: return str(val)
                # Show time only for Started/Completed columns
                if key in ["startedAt", "completedAt"]:
                    return dt.strftime("%d-%b %H:%M")
                return dt.strftime("%d-%b")
            except:
                return str(val)
                
        return str(val)

    def apply_zoom(self, delta):
        self.zoom_level = max(0.5, min(2.0, self.zoom_level + delta))
        self.refresh_table()

    def reset_zoom(self):
        self.zoom_level = 1.0
        self.refresh_table()

    def add_machine(self):
        name, ok = QInputDialog.getText(self, "Add Machine", "Machine Name:")
        if ok and name.strip():
            if name in self.all_machines_data: return
            self.all_machines_data[name] = {
                "jobs": [], 
                "columns": list(self.all_machines_data[self.current_machine]["columns"]) if self.current_machine in self.all_machines_data else [],
                "category": self.filter_category
            }
            self.machine_selector.addItem(name)
            self.machine_selector.setCurrentText(name)
            self.save_data()

    def rename_machine(self):
        name, ok = QInputDialog.getText(self, "Rename Machine", "New Name:", text=self.current_machine)
        if ok and name.strip() and name != self.current_machine:
            self.all_machines_data[name] = self.all_machines_data.pop(self.current_machine)
            self.machine_selector.setItemText(self.machine_selector.currentIndex(), name)
            self.current_machine = name
            self.save_data()

    def toggle_completed_visibility(self):
        self.show_completed = not self.show_completed
        
        for job in self.all_machines_data[self.current_machine]["jobs"]:
            if job.get("status") == "completed":
                job["visible"] = self.show_completed
            else:
                job["visible"] = True # Ensure other jobs are visible
        
        self.unhide_btn.setText("Hide Completed" if self.show_completed else "Unhide Completed")
        self.save_data()
        self.refresh_table()

    def get_visible_jobs(self):
        """Helper to get list of jobs that are actually shown in the table."""
        mc = self.all_machines_data.get(self.current_machine, {})
        return [j for j in mc.get("jobs", []) if j.get("visible", True)]

    def on_rows_moved(self, source_rows, target_row):
        self.save_state()
        mc = self.all_machines_data[self.current_machine]
        master_jobs = mc["jobs"]
        visible_jobs = self.get_visible_jobs()
        
        # 1. Identify objects to move (using visual indices)
        moved_jobs = [visible_jobs[i] for i in source_rows if i < len(visible_jobs)]
        if not moved_jobs: return

        # 2. Find target insertion point in master list
        insertion_job = None
        if target_row >= 0 and target_row < len(visible_jobs):
            insertion_job = visible_jobs[target_row]
        
        # 3. Remove from master list
        for job in moved_jobs:
            if job in master_jobs:
                master_jobs.remove(job)
        
        # 4. Insert at new location in master list
        if insertion_job and insertion_job in master_jobs:
            idx = master_jobs.index(insertion_job)
            
            # If moving DOWN, we want to land AFTER the target row to satisfy user expectation
            # (e.g. dragging 4 onto 5 results in 4 becoming the new 5)
            # Actually, inserting AT idx will push the current idx item down.
            # If moving DOWN (target > source), inserting at idx+1 is often what's felt as natural
            is_moving_down = any(target_row > r for r in source_rows)
            insert_idx = idx + 1 if is_moving_down else idx
            
            for i, job in enumerate(moved_jobs):
                master_jobs.insert(insert_idx + i, job)
        else:
            # Drop at end if target invalid
            master_jobs.extend(moved_jobs)
            
        self.run_optimizer()

    def get_visible_jobs(self):
        """Helper to get list of jobs that are actually shown in the table."""
        mc = self.all_machines_data.get(self.current_machine, {})
        return [j for j in mc.get("jobs", []) if j.get("visible", True)]

    def move_selected_jobs_to_machine(self, dest_machine_name):
        self.save_state()
        self.table.save_state()
        rows = sorted(list(self.get_selected_rows()), reverse=True)
        if not rows:
            return

        src_mc = self.all_machines_data[self.current_machine]
        dest_mc = self.all_machines_data.get(dest_machine_name)
        if not dest_mc:
            return

        visible_jobs = self.get_visible_jobs()
        moved_jobs = []
        for r in rows:
            if r < len(visible_jobs):
                job = visible_jobs[r]
                moved_jobs.append(job)

        # Confirm migration if multiple jobs
        if len(moved_jobs) > 1:
            reply = QMessageBox.question(self, "Confirm Migration", 
                                        f"Move {len(moved_jobs)} selected jobs to {dest_machine_name}?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return

        # Perform the move
        for job in moved_jobs:
            if job in src_mc["jobs"]:
                # Deep copy to destination
                new_job = copy.deepcopy(job)
                # Clear machine-specific schedule when moving to another machine
                new_job["schedule"] = {} 
                dest_mc["jobs"].append(new_job)
                # Remove from source
                src_mc["jobs"].remove(job)

        self.save_data()
        self.refresh_table()
        # Notify user (optional, can be quiet)
        # QMessageBox.information(self, "Migration Success", f"Moved {len(moved_jobs)} job(s) to {dest_machine_name}.")

    def add_row(self, at_index=-1, target_col=0, auto_edit=True, is_downtime=False):

        self.table.save_state()
        mc = self.all_machines_data[self.current_machine]
        master_jobs = mc["jobs"]
        visible_jobs = self.get_visible_jobs()

        if is_downtime:
            new_job = {
                "id": int(datetime.now().timestamp()*1000), 
                "pjc": "DOWNTIME", 
                "customer": "MAINTENANCE", 
                "description": "Machine Service / Repair",
                "mcTime": "4", 
                "status": "not_started", 
                "visible": True, 
                "rowColor": "#e2e8f0", # Distinct light grey
                "schedule": {}
            }
        else:
            # Assign a priority immediately so background syncs don't jump the row around
            # or lose it if they rely on priority for sorting.
            existing_jobs = mc.get("jobs", [])
            new_priority = float(len(existing_jobs))
            
            new_job = {
                "id": int(datetime.now().timestamp()*1000),
                "pjc": "NEW",
                "customer": "Customer",
                "description": "",
                "deliveryDate": "",
                "pjcIn": QDateTime.currentDateTime().toString("yyyy-MM-dd"),
                "qty": "",
                "gearTeeth": "",
                "meters": "",
                "mcTime": "8",
                "width": "",
                "orderStatus": "",
                "colValue": "",
                "colorsVarnish": "",
                "plateId": "",
                "totalAmt": "",
                "status": "not_started",
                "progress": "0",
                "notes": "",
                "visible": True,
                "priority": new_priority,
                "schedule": {}
            }
            
        target_row = 0
        if at_index == -1 or at_index >= len(visible_jobs): 
            master_jobs.append(new_job)
            target_row = len(visible_jobs) # Will be at the end
        else: 
            # Find the job at the current visual index to find master insertion point
            ref_job = visible_jobs[at_index]
            master_idx = master_jobs.index(ref_job)
            # Insert BEFORE the clicked row to satisfy "Insert Row" expectation
            master_jobs.insert(master_idx, new_job)
            target_row = at_index
            
        self.save_data()
        self.refresh_table()
        
        # Determine which table should handle the focus
        target_table = self.table
        # If target_col is within frozen columns (Customer, Description are usually 0, 1 in display),
        # but in our architecture, frozen_table handles the first few columns.
        frozen_cols_count = self.frozen_table.columnCount()
        
        actual_table = self.frozen_table if target_col < frozen_cols_count else self.table
        actual_col = target_col if target_col < frozen_cols_count else target_col - frozen_cols_count

        def focus_and_edit():
            actual_table.setCurrentCell(target_row, actual_col)
            actual_table.setFocus()
            if auto_edit:
                item = actual_table.item(target_row, actual_col)
                if item:
                    actual_table.editItem(item)

        QTimer.singleShot(100, focus_and_edit)

    def add_maintenance(self, at_index=-1):
        """Helper to specifically add a downtime block."""
        self.add_row(at_index=at_index, target_col=2, auto_edit=True, is_downtime=True)

    def get_selected_rows(self):
        """Helper to get unique selected row indices from both tables."""
        rows = set()
        for item in self.table.selectedItems():
            rows.add(item.row())
        for item in self.frozen_table.selectedItems():
            rows.add(item.row())
        return rows

    def delete_row(self):
        # Aggregate selected rows from BOTH tables (frozen and scrollable)
        rows = sorted(list(self.get_selected_rows()), reverse=True)
        if not rows:
            return
            
        # Confirmation Dialog to prevent accidental loss
        count = len(rows)
        msg = f"Are you sure you want to delete {count} selected row(s)?" if count > 1 else "Are you sure you want to delete the selected row?"
        reply = QMessageBox.question(self, "Confirm Deletion", msg, 
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.No:
            return

        self.save_state()
        self.table.save_state()
        mc = self.all_machines_data[self.current_machine]
        visible_jobs = self.get_visible_jobs()
        
        jobs_to_delete = []
        for r in rows:
            if r < len(visible_jobs):
                jobs_to_delete.append(visible_jobs[r])
        
        # Remove identified jobs from the master list
        deleted_count = 0
        sql_config = self.get_sql_config() # Use helper for consistency
        
        for job in jobs_to_delete:
            if job in mc["jobs"]:
                jid = job.get("id")
                pjc = job.get('pjc')
                mc["jobs"].remove(job)
                deleted_count += 1
                # SQL Delete: remove matching row from Production_Planner_Export
                if sql_config and jid:
                    api_service.log_to_file(f"SQL HARD-DELETE: Permanently removing PJC {pjc} (ID: {jid})")
                    # Run in background to avoid blocking UI during network operations
                    threading.Thread(
                        target=sql_service.delete_job_from_sql,
                        args=(str(jid), sql_config),
                        daemon=True
                    ).start()
                
        if deleted_count > 0:
            self.save_data()
            self.refresh_table()

    def set_row_color(self, rows, color_hex):
        self.save_state()
        if isinstance(rows, int): rows = [rows]
        mc = self.all_machines_data[self.current_machine]
        visible_jobs = [j for j in mc["jobs"] if j.get("visible", True)]
        
        updated = False
        self.table.save_state()
        for row in rows:
            if row < len(visible_jobs):
                visible_jobs[row]["rowColor"] = color_hex
                updated = True
                
        if updated:
            self.save_data()
            self.refresh_table()

    def save_data(self):
        # FIX: Ensure local job dictionaries receive the same priority index that SQL will assign, 
        # avoiding background sync worker sorting misalignments.
        for mc_name, mc_data in self.all_machines_data.items():
            for idx, job in enumerate(mc_data.get("jobs", [])):
                job["priority"] = float(idx)
                
        if self.save_callback:
            self.save_callback()
        else:
            # Fallback for direct testing if no callback provided
            try:
                from ..utils.planner_utils import save_planner_data
            except ImportError:
                from py_planner.utils.planner_utils import save_planner_data
            data_to_save = {"machines": self.all_machines_data, "appSettings": self.settings}
            data_path = self.settings.get("dataPath", "test_planning_100_jobs.json")
            print(f"PLANNING BOARD: Saving {len(self.all_machines_data)} machines to {data_path}")
            save_planner_data(data_path, data_to_save)

    def granular_save(self, job, machine_name=None):
        """Pushes a single job change to SQL immediately."""
        pjc = job.get('pjc')
        enabled = self.settings.get("sqlExportEnabled")
        
        if not enabled:
            api_service.log_to_file(f"SQL EXPORT: Skipping job {pjc} - sqlExportEnabled is False/None")
            return
            
        sql_config = self.settings.get("sqlConfig", {})
        if not sql_config or not sql_config.get("server"):
            api_service.log_to_file(f"SQL EXPORT: Skipping job {pjc} - No SQL server in config")
            return
            
        api_service.log_to_file(f"SQL EXPORT: Triggering save for Job {pjc}")
        
        user_name = self.current_user.get("name", "Unknown")
        target_machine = machine_name if machine_name else self.current_machine
        
        # TRIGGER SYNC SHIELD: Prevent immediate reload of stale data
        try:
            # PlanningBoard parent is usually the StackedWidget or ScrollArea, 
            # we need to find the MainWindow
            main_win = self.window()
            if hasattr(main_win, 'refresh_sync_shield'):
                main_win.refresh_sync_shield()
        except:
            pass

        # Run in a daemon thread to avoid UI lag
        threading.Thread(
            target=sql_service.save_single_job_to_sql,
            args=(job, target_machine, sql_config, user_name),
            daemon=True
        ).start()

    def run_optimizer(self):
        mc = self.all_machines_data[self.current_machine]
        mc["jobs"] = self.logic.apply_sequential_schedule(mc["jobs"], self.current_machine)
        self.save_data()
        self.refresh_table()


    def get_sql_config(self):
        """Helper to retrieve the current SQL configuration."""
        return self.settings.get("sqlConfig", {})




    def refresh_sync_timers(self):
        """Re-configures and restarts the API status polling timer."""
        self.status_sync_timer.stop()
        
        
        # 1. Determine sync source and interval
        sync_src = self.settings.get("syncSource") or self.settings.get("sync_source", "sql")
        # User explicitly asked for API only for live status updates in this turn
        api_enabled = (sync_src == "api") or self.settings.get("apiEnabled", False)
        
        
        if api_enabled:
            # Get interval in seconds (default 30s)
            interval_secs = self.settings.get("apiInterval") or self.settings.get("api_interval") or 30
            # User safety: Don't allow less than 5 seconds for background API polling
            try:
                interval_ms = max(5, int(interval_secs)) * 1000
            except:
                interval_ms = 30000
                
            self.status_sync_timer.start(interval_ms)
        else:
            pass

    def _poll_live_statuses(self):
        """Identifies active PJCs and triggers the background API check."""
        if self._is_status_syncing: return
        
        # 1. Get ALL PJCs that are active (not completed) across all machines
        pjcs = []
        for m_name, mc_data in self.all_machines_data.items():
            for j in mc_data.get("jobs", []):
                pjc = str(j.get("pjc", "")).strip()
                status = str(j.get("status", "")).lower()
                if pjc and pjc != "NEW" and status not in ["completed", "cancelled"]:
                    if pjc not in pjcs:
                        pjcs.append(pjc)
        
        if not pjcs:
            return
            
        self._is_status_syncing = True
        sql_config = self.get_sql_config()
        
        self._status_worker = StatusBackgroundWorker(pjcs, sql_config)
        self._status_worker.statuses_ready.connect(self.apply_status_updates)
        self._status_worker.finished.connect(self._on_status_worker_finished)
        self._status_worker.start()

    def _on_status_worker_finished(self):
        self._is_status_syncing = False
        self._status_worker = None

    def apply_status_updates(self, status_map):
        """Updates internal job objects and syncs changes back to SQL."""
        if not status_map: return
        
        from floor_view.api import api_service
        # Optional: Noise reduction, keep it if you need diagnostics
        api_service.log_to_file(f"DEBUG UI: apply_status_updates triggered with {len(status_map)} statuses.")
        
        updated_count = 0
        
        # Search across ALL machines
        for machine_name, machine_data in self.all_machines_data.items():
            for job in machine_data.get("jobs", []):
                pjc = str(job.get("pjc", "")).strip()
                if pjc in status_map:
                    raw_val = status_map[pjc]
                    # Robust extraction: if worker returned a dict, get 'status' field
                    if isinstance(raw_val, dict):
                        new_status = raw_val.get("status")
                    else:
                        new_status = str(raw_val)
                    
                    old_status = job.get("status")
                    
                    if new_status and new_status != old_status:
                        api_service.log_to_file(f"LIVE STATUS UPDATE: Job {pjc} | {old_status} -> {new_status}")
                        job["status"] = new_status
                        updated_count += 1
                        
                        # Handle workflow duplication (to finishing/packing/delivery)
                        self._handle_workflow_transitions(job, old_status, new_status)
                        
                        # Automatically push this status update to SQL
                        self.granular_save(job, machine_name)

        if updated_count > 0:
            self.refresh_table()
            self.save_data()




    def on_item_changed(self, item):
        try:
            row, col = item.row(), item.column()
            self.table.blockSignals(True)
            self.frozen_table.blockSignals(True)
            
            mc = self.all_machines_data[self.current_machine]
            visible_jobs = self.get_visible_jobs()
            display_cols = self.get_display_columns(mc)
            
            # Calculate global column index
            frozen_count = len(display_cols)
            
            if item.tableWidget() == self.table:
                # This is the Scroll Table (Calendar)
                global_col = col + frozen_count
            else:
                # This is the Frozen Table (Data Columns)
                global_col = col

            if row < len(visible_jobs):
                job = visible_jobs[row]
                
                # Check if this is a data column vs calendar column
                if global_col < len(display_cols):
                    key = display_cols[global_col]["key"]
                    
                    if key == "status": # Handle status separately if it's not handled by dropdown
                        self.table.blockSignals(False)
                        self.frozen_table.blockSignals(False)
                        return
                    
                    new_val = item.text()
                    # Smart Date Entry: DDMM -> DD-MMM
                    date_keys = ["deliveryDate", "pjcIn", "prodDeliveryDate", "startedAt", "completedAt"]
                    if key in date_keys and len(new_val) == 4 and new_val.isdigit():
                        try:
                            day = int(new_val[:2])
                            month = int(new_val[2:])
                            if 1 <= month <= 12 and 1 <= day <= 31:
                                dt = datetime(datetime.now().year, month, day)
                                new_val = dt.strftime("%d-%b")
                                item.setText(new_val)
                        except Exception as e:
                            api_service.log_to_file(f"DEBUG: Date shortcut conversion skipped for {new_val}: {e}")

                    if key in ["qty", "meters", "mcTime", "totalAmt", "totalRevenue", "width", "gearTeeth", "progress", "colValue"]:
                        # Remove currency markers and thousands separators
                        new_val = new_val.replace("MUR", "").replace("Rs", "").replace(",", "").replace("%", "").strip()

                    if str(job.get(key)) != new_val:
                        self.table.save_state()
                        job[key] = new_val
                        
                        key_lower = str(key).lower()
                        label_lower = str(display_cols[global_col].get("label", "")).lower()
                        
                        if any(x == "customer" for x in [key_lower, label_lower]):
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere)
                        elif any(x == "description" for x in [key_lower, label_lower]):
                            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere)
                        else:
                            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
                        
                        if key_lower == "pjc" and new_val and new_val != "NEW":
                            job["pjcIn"] = datetime.now().strftime("%Y-%m-%d")
                            api_service.log_to_file(f"DEBUG UI: PJC Change detected: '{new_val}'. Setting pjcIn to {job['pjcIn']} and triggering background fetch.")
                            self.trigger_pjc_background_fetch(new_val, job)
                        
                        pjc = str(job.get("pjc", "")).strip()
                        if pjc:
                            import time
                            if not hasattr(self, 'status_locks'): self.status_locks = {}
                            self.status_locks[pjc] = time.time()
                            api_service.log_to_file(f"SYNC LOCK: Locked PJC {pjc} for manual edit on {key}")

                        if key == "mcTime": 
                            api_service.log_to_file(f"UI CHANGE: {key} changed to {new_val}. Running optimizer...")
                            if not self._is_batch_updating:
                                self.run_optimizer()
                            else:
                                # We'll save but delay the heavy refresh until the end of the batch
                                self.save_data()
                            # FIXED: Persist mcTime change immediately to SQL
                            self.granular_save(job)
                        else: 
                            api_service.log_to_file(f"UI CHANGE: {key} changed to {new_val}. Saving...")
                            self.save_data()
                            self.granular_save(job)
                            
                elif self.show_calendar:
                    dates_info = self.get_dates()
                    date_idx = global_col - len(display_cols)
                    
                    if 0 <= date_idx < len(dates_info):
                        date_label = dates_info[date_idx]["label"]
                        new_val = item.text().strip()
                        
                        if "schedule" not in job: job["schedule"] = {}
                        if str(job["schedule"].get(date_label)) != new_val:
                            self.table.save_state()
                            job["schedule"][date_label] = new_val
                            
                            try:
                                has_work = float(new_val) > 0 if new_val else False
                            except:
                                has_work = False
                            
                            if has_work:
                                item.setBackground(QColor("#0ea5e9" if job.get("status") != "completed" else "#cbd5e1"))
                                item.setForeground(Qt.GlobalColor.white)
                            else:
                                row_color = job.get("rowColor")
                                item.setBackground(QColor(row_color) if row_color else QColor("#ffffff"))
                                item.setForeground(QColor("#000000"))
                            
                            api_service.log_to_file(f"CALENDAR CHANGE: {date_label} changed to {new_val}. Saving...")
                            self.save_data()
                            self.granular_save(job)
                            
        except Exception as e:
            api_service.log_to_file(f"CRITICAL ERROR in on_item_changed: {e}")
            import traceback
            api_service.log_to_file(traceback.format_exc())
        finally:
            self.table.blockSignals(False)
            self.frozen_table.blockSignals(False)

    def trigger_pjc_background_fetch(self, pjc, job):
        # Use structured config if available, fallback to legacy if not
        sql_config = self.settings.get("sqlConfig", {})
        if not sql_config or not sql_config.get("server"):
            sql_config = {
                "server": self.settings.get("sqlServer", ""),
                "database": self.settings.get("sqlDatabase", ""),
                "user": self.settings.get("sqlUser", ""),
                "password": self.settings.get("sqlPassword", ""),
                "table": self.settings.get("sqlTableView", "YourViewName"),
                "apiEnabled": self.settings.get("apiEnabled"),
                "syncSource": self.settings.get("syncSource"),
                "apiUrl": self.settings.get("apiUrl"),
                "apiToken": self.settings.get("apiToken")
            }
        
        # Ensure nested structured config has the mode flags if missing
        if "apiEnabled" not in sql_config: sql_config["apiEnabled"] = self.settings.get("apiEnabled")
        if "syncSource" not in sql_config: sql_config["syncSource"] = self.settings.get("syncSource")
        if "apiUrl" not in sql_config: sql_config["apiUrl"] = self.settings.get("apiUrl")
        if "apiToken" not in sql_config: sql_config["apiToken"] = self.settings.get("apiToken")

        # Normalize snake_case keys saved by save_sql_config_only into camelCase keys
        # that api_service.get_job_from_api expects (apiUrl, apiToken, syncSource, apiEnabled).
        if not sql_config.get("apiUrl"):
            sql_config["apiUrl"] = sql_config.get("api_url") or self.settings.get("apiUrl", "")
        if not sql_config.get("apiToken"):
            sql_config["apiToken"] = sql_config.get("api_token") or self.settings.get("apiToken", "")
        if not sql_config.get("syncSource"):
            sql_config["syncSource"] = sql_config.get("sync_source") or self.settings.get("syncSource", "sql")
        if not sql_config.get("apiEnabled"):
            sql_config["apiEnabled"] = sql_config.get("apiEnabled") or (sql_config.get("sync_source") == "api")

        # Always inject table name and driver from flat settings if missing from the nested config.
        # This fixes the case where config came from the first-run wizard (which does not write
        # sqlTableView into sqlConfig), causing get_bulk_job_data to default to "YourViewName".
        if not sql_config.get("table") or sql_config.get("table") == "YourViewName":
            sql_config["table"] = self.settings.get("sqlTableView", "")
        if not sql_config.get("driver"):
            sql_config["driver"] = self.settings.get("sqlDriver", "{ODBC Driver 17 for SQL Server}")

        # VALIDATION: Require either a SQL Server OR the API to be enabled
        is_api = sql_config.get("syncSource") == "api" or sql_config.get("apiEnabled")
        has_server = bool(sql_config.get("server"))

        if not has_server and not is_api:
            api_service.log_to_file(f"DEBUG: PJC Background Worker SKIPPED for {pjc} - No Server or API configured. Settings: apiEnabled={self.settings.get('apiEnabled')}, syncSource={self.settings.get('syncSource')}")
            return

        api_service.log_to_file(f"DEBUG: Background Worker starting for PJC {pjc} on table {sql_config.get('table')}")
        if is_api:
            api_service.log_to_file(f"DEBUG: Mode: API (Endpoint: {sql_config.get('apiUrl')})")
        else:
            api_service.log_to_file(f"DEBUG: Mode: SQL (Server: {sql_config.get('server')})")

        worker = PJCBackgroundWorker(pjc, job, sql_config)
        worker.result_ready.connect(self.apply_sql_result)
        if not hasattr(self, '_pjc_workers'): self._pjc_workers = []
        self._pjc_workers.append(worker)
        worker.finished.connect(lambda: print(f"DEBUG: PJC Worker finished for {pjc}"))
        worker.finished.connect(lambda: self._pjc_workers.remove(worker) if worker in self._pjc_workers else None)
        worker.start()

    def apply_sql_result(self, sql_data, job):
        """Merges background SQL results into the job object and updates UI granularly."""
        # Use a safe way to log or print if api_service.log_to_file is inactive
        try:
            from floor_view.api import api_service
            api_service.log_to_file(f"DEBUG UI: Received PJC Result for {sql_data.get('pjc')}: {list(sql_data.keys())}")
        except:
            pass
        
        # PyQt cross-thread signals deep-copy dicts. We MUST grab the real UI reference.
        target_id = job.get('id')
        real_job = None
        for m_name, mc_data in self.all_machines_data.items():
            for j in mc_data.get("jobs", []):
                if str(j.get("id")) == str(target_id):
                    real_job = j
                    break
            if real_job: break
            
        if not real_job:
            return
            
        job = real_job # Swap to the real reference connected to the UI model
        
        updated = False
        # Only update if the PJC still matches (in case it was changed again during fetch)
        if str(job.get("pjc")).strip() == str(sql_data.get("pjc")).strip():
            # Find the visual row index for this job
            visible_jobs = self.get_visible_jobs()
            row_idx = -1
            try:
                row_idx = visible_jobs.index(job)
            except ValueError:
                pass

            display_cols = self.get_display_columns(self.all_machines_data.get(self.current_machine, {}))
            key_to_col = {c["key"]: i for i, c in enumerate(display_cols)}

            for key, val in sql_data.items():
                if key != "pjc" and val and str(val).strip() not in ["", "-"]:
                    if key == "pjcIn": continue # Keep system date
                        
                    current_val = str(job.get(key, "")).strip()
                    new_val_str = str(val).strip()
                    
                    if current_val in ["", "-"] or current_val != new_val_str:
                        job[key] = val
                        updated = True
                        
                        # GRANULAR UI UPDATE: Directly update the cell if it's visible
                        if row_idx != -1 and key in key_to_col:
                            col_idx = key_to_col[key]
                            # Robust signal blocking with try...finally
                            try:
                                self.frozen_table.blockSignals(True)
                                item = self.frozen_table.item(row_idx, col_idx)
                                if item:
                                    # Fix: Use QAbstractItemView.State.EditingState (Standard across ScrollArea widgets)
                                    from PyQt6.QtWidgets import QAbstractItemView
                                    is_editing = (self.frozen_table.state() == QAbstractItemView.State.EditingState)
                                    is_current = (self.frozen_table.currentRow() == row_idx and 
                                                 self.frozen_table.currentColumn() == col_idx)
                                    
                                    if not (is_editing and is_current):
                                        item.setText(new_val_str)
                            except Exception as e:
                                pass
                            finally:
                                self.frozen_table.blockSignals(False)
        
        if updated:
            self.refresh_table()
            self.save_data()
            self.granular_save(job)


    def on_status_changed(self, text, job):
        if str(job.get("status")) != text:
            old_status = job.get("status")
            self.save_state()
            self.table.save_state()
            job["status"] = text
            
            # Status Lock: Prevent background sync from overwriting this change for 2 minutes
            pjc = str(job.get("pjc", "")).strip()
            if pjc:
                import time
                self.status_locks[pjc] = time.time()
            
            # User Attribution logic
            job["updatedBy"] = self.current_user.get("name", "Unknown")
            job["updatedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Auto-fill logic for status transitions
            now_iso = datetime.now().isoformat()
            
            if text.lower() == "completed":
                # Only set if not already set or specifically requested
                job["completedAt"] = now_iso
                job["progress"] = "100"
                
                # Trigger Workflow Automation
                self._handle_workflow_transitions(job, old_status, text)

                job["visible"] = self.show_completed # Hide in production if not explicitly showing completed
                self.run_optimizer()
            elif text.lower() == "in_progress":
                job["visible"] = True # Ensure visible if moved back from completed
                if not job.get("startedAt"):
                    job["startedAt"] = now_iso
                # Default progress to 10% if 0/empty to reflect cost on dashboard
                if self.logic.safe_float(job.get("progress")) <= 0:
                    job["progress"] = "10"
                self.run_optimizer()
            else:
                job["visible"] = True # Ensure visible for all other active statuses
                self.run_optimizer() # Recalculate everything when status changes

            # Ensure the status change is pushed to SQL immediately
            self.granular_save(job)

    def _handle_workflow_transitions(self, job, old_status, new_status):
        """Centralized logic to duplicate jobs across machine categories on completion."""
        if str(new_status).lower() != "completed":
            return
            
        pjc = job.get('pjc')
        now_iso = datetime.now().isoformat()

        # 1. AUTOMATIC FINISHING WORKFLOW
        finishing_mc = job.get("finishingMachine")
        if self.filter_category == "production" and finishing_mc and finishing_mc != "None":
            dest_mc = self.all_machines_data.get(finishing_mc)
            if dest_mc:
                try:
                    # Create a clean copy for finishing
                    finishing_job = copy.deepcopy(job)
                    finishing_job["id"] = int(datetime.now().timestamp() * 1000) # Fresh ID
                    finishing_job["status"] = "not_started"
                    finishing_job["progress"] = "0"
                    finishing_job["completedAt"] = None
                    finishing_job["visible"] = True
                    finishing_job["schedule"] = {}
                    
                    dest_mc["jobs"].append(finishing_job)
                    from floor_view.api import api_service
                    api_service.log_to_file(f"WORKFLOW: Duplicated PJC {pjc} to Finishing Machine: {finishing_mc}")
                    self.save_data()
                except Exception as e:
                    from floor_view.api import api_service
                    api_service.log_to_file(f"WORKFLOW ERROR: Failed to duplicate to Finishing: {e}")

        # 2. AUTOMATIC PACKING WORKFLOW
        packing_mc = job.get("packingMachine")
        if self.filter_category == "finishing":
            if not packing_mc or packing_mc == "None":
                packing_mcs = [n for n, d in self.all_machines_data.items() if d.get("category") == "packing"]
                if packing_mcs:
                    packing_mc = packing_mcs[0]

            if packing_mc and packing_mc != "None":
                dest_mc = self.all_machines_data.get(packing_mc)
                if dest_mc:
                    try:
                        packing_job = copy.deepcopy(job)
                        packing_job["id"] = int(datetime.now().timestamp() * 1000) + 1 # Fresh ID
                        packing_job["status"] = "not_started"
                        packing_job["progress"] = "0"
                        packing_job["completedAt"] = None
                        packing_job["visible"] = True
                        packing_job["schedule"] = {}
                        
                        dest_mc["jobs"].append(packing_job)
                        from floor_view.api import api_service
                        api_service.log_to_file(f"WORKFLOW: Duplicated PJC {pjc} to Packing Machine: {packing_mc}")
                        self.save_data()
                    except Exception as e:
                        from floor_view.api import api_service
                        api_service.log_to_file(f"WORKFLOW ERROR: Failed to duplicate to Packing: {e}")

        # 3. AUTOMATIC DELIVERY WORKFLOW
        if self.filter_category == "packing":
            delivery_mcs = [n for n, d in self.all_machines_data.items() if str(d.get("category", "")).lower() == "delivery"]
            if delivery_mcs:
                delivery_mc = delivery_mcs[0]
                dest_mc = self.all_machines_data.get(delivery_mc)
                if dest_mc:
                    try:
                        delivery_job = copy.deepcopy(job)
                        delivery_job["id"] = int(datetime.now().timestamp() * 1000) + 2 # Fresh ID
                        delivery_job["status"] = "not_started"
                        delivery_job["progress"] = "0"
                        delivery_job["completedAt"] = None
                        delivery_job["visible"] = True
                        delivery_job["schedule"] = {}
                        delivery_job["machine"] = delivery_mc
                        delivery_job["machineName"] = delivery_mc
                        
                        dest_mc["jobs"].append(delivery_job)
                        from floor_view.api import api_service
                        api_service.log_to_file(f"WORKFLOW: Duplicated PJC {pjc} to Delivery Machine: {delivery_mc}")
                        self.save_data()
                    except Exception as e:
                        from floor_view.api import api_service
                        api_service.log_to_file(f"WORKFLOW ERROR: Failed to duplicate to Delivery: {e}")

    def toggle_calendar(self):
        self.show_calendar = not self.show_calendar
        self.cal_toggle.setText("Hide Calendar" if self.show_calendar else "Show Calendar")
        self.refresh_table()

    def get_dates(self):
        from datetime import datetime, timedelta
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        dates = []
        holidays = self.settings.get("publicHolidays", [])
        working_sats = self.settings.get("workingSaturdays", [])
        
        for i in range(31):
            dt = today + timedelta(days=i)
            iso = dt.strftime("%Y-%m-%d")
            is_weekend = dt.weekday() >= 5 # 5=Sat, 6=Sun
            
            # Explicit Override: If it's a working Saturday, it's not a "non-working" day
            is_non_working = (is_weekend or iso in holidays) and (iso not in working_sats)
            
            dates.append({
                "label": dt.strftime("%d-%b"),
                "iso": iso,
                "is_non_working": is_non_working
            })
        return dates

    def is_viewer(self):
        role = str(self.current_user.get("role", "")).lower()
        return role == "viewer" or role == "pre-press dep."

    def refresh_table(self):
        self.table.setUpdatesEnabled(False)
        self.frozen_table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.frozen_table.blockSignals(True)

        # SYNC SAFETY: If user is actively typing or a cell is in edit mode, 
        # skip the full refresh to avoid losing the current cursor/text.
        from PyQt6.QtWidgets import QTableWidget
        if self.table.state() == QTableWidget.State.EditingState or \
           self.frozen_table.state() == QTableWidget.State.EditingState:
            print("REFRESH TABLE: Skipping refresh - User is currently editing.")
            self.table.blockSignals(False)
            self.frozen_table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
            self.frozen_table.setUpdatesEnabled(True)
            return
        
        # Clear existing contents to prevent data leak into shifted rows (e.g. Capacity Meter)
        self.table.clearContents()
        self.frozen_table.clearContents()
        
        # Explicitly Enforce Word Wrap
        self.table.setWordWrap(True)
        self.frozen_table.setWordWrap(True)
        
        if self.current_machine not in self.all_machines_data:
            # Initialize a blank machine if it doesn't exist
            self.all_machines_data[self.current_machine] = {
                "jobs": [],
                "columns": [
                    {"label": "PJC", "key": "pjc"},
                    {"label": "Customer", "key": "customer"},
                    {"label": "Description", "key": "description"},
                    {"label": "Delivery Date", "key": "deliveryDate"},
                    {"label": "PJC In", "key": "pjcIn"},
                    {"label": "Delivery date given by Prod", "key": "prodDeliveryDate"},
                    {"label": "Qty", "key": "qty"},
                    {"label": "Gear teeth", "key": "gearTeeth"},
                    {"label": "Meters", "key": "meters"},
                    {"label": "M/C Time", "key": "mcTime"},
                    {"label": "Width", "key": "width"},
                    {"label": "Order Status", "key": "orderStatus"},
                    {"label": "Col", "key": "colValue"},
                    {"label": "Colors + Varnish", "key": "colorsVarnish"},
                    {"label": "Plate ID", "key": "plateId"},
                    {"label": "Die Cut", "key": "dieCut"},
                    {"label": "Total Amt", "key": "totalAmt"},
                    {"label": "Finishing Machine", "key": "finishingMachine"},
                    {"label": "Status", "key": "status"},
                    {"label": "Progress %", "key": "progress"},
                    {"label": "Started", "key": "startedAt"},
                    {"label": "Completed", "key": "completedAt"},
                    {"label": "Notes", "key": "notes"}
                ]
            }
        
        mc = self.all_machines_data[self.current_machine]
        
        # Safety Fix: Ensure 'columns' key exists if machine was partially loaded (e.g. from SQL names list)
        if "columns" not in mc:
            mc["columns"] = [
                {"label": "PJC", "key": "pjc"},
                {"label": "Customer", "key": "customer"},
                {"label": "Description", "key": "description"},
                {"label": "Delivery Date", "key": "deliveryDate"},
                {"label": "PJC In", "key": "pjcIn"},
                {"label": "Delivery date given by Prod", "key": "prodDeliveryDate"},
                {"label": "Qty", "key": "qty"},
                {"label": "Gear teeth", "key": "gearTeeth"},
                {"label": "Meters", "key": "meters"},
                {"label": "M/C Time", "key": "mcTime"},
                {"label": "Width", "key": "width"},
                {"label": "Order Status", "key": "orderStatus"},
                {"label": "Col", "key": "colValue"},
                {"label": "Colors + Varnish", "key": "colorsVarnish"},
                {"label": "Plate ID", "key": "plateId"},
                {"label": "Die Cut", "key": "dieCut"},
                {"label": "Total Amt", "key": "totalAmt"},
                {"label": "Finishing Machine", "key": "finishingMachine"},
                {"label": "Status", "key": "status"},
                {"label": "Progress %", "key": "progress"},
                {"label": "Started", "key": "startedAt"},
                {"label": "Completed", "key": "completedAt"},
                {"label": "Notes", "key": "notes"}
            ]
        
        # Cleanup: Remove retired 'Packing Machine' column if it persists in JSON
        mc["columns"] = [c for c in mc.get("columns", []) if c.get("key") != "packingMachine"]

        # Migration: Ensure 'Finishing Machine' exists
        col_keys = [c["key"] for c in mc["columns"]]
        if "finishingMachine" not in col_keys:
            # Insert before 'Status'
            try:
                status_idx = next(i for i, c in enumerate(mc["columns"]) if c["key"] == "status")
                mc["columns"].insert(status_idx, {"label": "Finishing Machine", "key": "finishingMachine"})
            except StopIteration:
                mc["columns"].append({"label": "Finishing Machine", "key": "finishingMachine"})

        # Migration: Ensure 'Delivery date given by Prod' exists in existing machines
        col_keys = [c["key"] for c in mc["columns"]]
        if "prodDeliveryDate" not in col_keys:
            # Find index of pjcIn to insert after it
            try:
                pjc_idx = next(i for i, c in enumerate(mc["columns"]) if c["key"] == "pjcIn")
                mc["columns"].insert(pjc_idx + 1, {"label": "Delivery date given by Prod", "key": "prodDeliveryDate"})
            except StopIteration:
                mc["columns"].append({"label": "Delivery date given by Prod", "key": "prodDeliveryDate"})

        # Migration: Ensure 'Plate ID' exists
        col_keys = [c["key"] for c in mc["columns"]]
        if "plateId" not in col_keys:
            try:
                # Insert before 'Die Cut' or 'Total Amt'
                target_idx = next(i for i, c in enumerate(mc["columns"]) if c["key"] in ["dieCut", "totalAmt"])
                mc["columns"].insert(target_idx, {"label": "Plate ID", "key": "plateId"})
            except StopIteration:
                mc["columns"].append({"label": "Plate ID", "key": "plateId"})

        # Migration/Reorder: Ensure 'Die Cut' exists strictly before 'Total Amt'
        col_keys = [c["key"] for c in mc["columns"]] # Refresh list
        has_dieCut = "dieCut" in col_keys
        has_amt = "totalAmt" in col_keys
        
        if has_dieCut and has_amt:
            # Ensure order: dieCut must be before totalAmt
            die_idx = col_keys.index("dieCut")
            amt_idx = col_keys.index("totalAmt")
            if die_idx > amt_idx:
                # Remove dieCut and insert it right before totalAmt
                die_col = mc["columns"].pop(die_idx)
                # Re-find amt index because popping might have shifted it
                new_amt_idx = [c["key"] for c in mc["columns"]].index("totalAmt")
                mc["columns"].insert(new_amt_idx, die_col)
                
        elif not has_dieCut and has_amt:
            amt_idx = col_keys.index("totalAmt")
            mc["columns"].insert(amt_idx, {"label": "Die Cut", "key": "dieCut"})
        elif not has_dieCut and not has_amt:
            mc["columns"].append({"label": "Die Cut", "key": "dieCut"})
            mc["columns"].append({"label": "Total Amt", "key": "totalAmt"})
            
        display_cols = self.get_display_columns(mc)
        self._is_refreshing = True # Block resize signals during rebuild

        # Filter visible jobs
        all_jobs = mc.get("jobs", [])
        
        # Filter visible jobs
        visible_jobs = [j for j in mc.get("jobs", []) if j.get("visible", True)]
        
        dates_info = self.get_dates() if self.show_calendar else []
        
        # Absolute Word Wrap Enforcement
        self.table.setWordWrap(True)
        self.frozen_table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.frozen_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        
        # Dynamic Scaling Factors based on Zoom Level
        base_font_size = 9
        scaled_font_size = max(6, int(base_font_size * self.zoom_level))
        base_row_height = 75
        scaled_row_height = max(50, int(base_row_height * self.zoom_level))
        
        # Increase header height significantly to ensure multi-line wraps (e.g. "Delivery date given by Prod") fit
        base_header_height = 110
        scaled_header_height = max(80, int(base_header_height * self.zoom_level))
        
        font = QFont("Inter", scaled_font_size)
        bold_font = QFont("Inter", scaled_font_size, QFont.Weight.Bold)
        
        # Create a specifically smaller font for the headers to prevent overflow
        header_font_size = max(5, int((base_font_size - 3.5) * self.zoom_level))
        header_font = QFont("Inter", header_font_size, QFont.Weight.Bold)
        
        # We freeze all data columns (so they stay on screen), calendar scrolls on right
        frozen_count = len(display_cols)
        scroll_count = len(dates_info)
        row_count = len(visible_jobs) + (1 if self.show_calendar else 0)

        self.frozen_table.setColumnCount(frozen_count)
        self.frozen_table.setRowCount(row_count)
        self.table.setColumnCount(scroll_count)
        self.table.setRowCount(row_count)
        
        frozen_headers = [display_cols[i]["label"] for i in range(frozen_count)]
        scroll_headers = [d["label"] for d in dates_info]
        
        self.frozen_table.setHorizontalHeaderLabels(frozen_headers)
        self.table.setHorizontalHeaderLabels(scroll_headers)
        
        self.frozen_table.horizontalHeader().setFont(header_font)
        self.table.horizontalHeader().setFont(header_font)
        
        # Enable Word Wrap for Headers
        self.frozen_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere)
        
        self.frozen_table.verticalHeader().setFont(font)

        holidays = self.settings.get("publicHolidays", [])
        NON_WORKING_BG = QColor("#f1f5f9") # Very light gray for light theme
        
        column_totals = {col["key"]: 0.0 for col in display_cols}
        
        # Track total hours assigned per calendar day for capacity warnings
        machine_shifts = self.settings.get("machineShifts", {})
        max_shift = self.safe_float(machine_shifts.get(self.current_machine, self.settings.get("shiftHours", 8)))
        daily_hours = {i: 0.0 for i in range(len(dates_info))} if self.show_calendar else {}
        
        # Pre-calculate machine lists for dropdowns to avoid redundant looping inside the row loop
        finishing_mcs = ["None"] + sorted([n for n, d in self.all_machines_data.items() if d.get("category") == "finishing"])
        
        for r, job in enumerate(visible_jobs):
            # 1. Populate Frozen Table (Left - All Data Columns)
            for c in range(frozen_count):
                col = display_cols[c]
                key = col["key"]
                val = str(job.get(key, ""))
                
                if key == "plateId":
                    container = QFrame()
                    # Use a grid layout to maximize space
                    layout = QGridLayout(container)
                    layout.setContentsMargins(2, 2, 2, 2)
                    layout.setSpacing(0)
                    
                    lbl = QLabel(val)
                    lbl.setFont(font)
                    lbl.setWordWrap(True)
                    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                    lbl.setStyleSheet("background: transparent; color: black; border: none;")
                    layout.addWidget(lbl, 0, 0, 1, 2) # Span across columns
                    
                    cb = QCheckBox()
                    cb_container = QWidget()
                    cb_layout = QHBoxLayout(cb_container)
                    cb_layout.setContentsMargins(0, 0, 0, 0)
                    cb_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
                    cb_layout.addWidget(cb)
                    layout.addWidget(cb_container, 1, 1) # Bottom right corner
                    
                    ready_state = job.get("plateReady", False)
                    cb.setChecked(ready_state)
                    
                    # Permission Check
                    user_role = str(self.current_user.get("role", "")).lower()
                    allowed_roles = ["administrator", "planner", "pre-press dep."]
                    cb.setEnabled(user_role in allowed_roles)
                    
                    cb.clicked.connect(lambda checked, j=job: self.on_plate_ready_changed(checked, j))
                    
                    # Small Black Box Styling for Pre-Press (No white background to blend with row)
                    cb_qss = """
                        QCheckBox {
                            background-color: transparent;
                        }
                        QCheckBox::indicator {
                            width: 14px;
                            height: 14px;
                            border: 2px solid #000000;
                            background-color: transparent;
                            border-radius: 2px;
                        }
                        QCheckBox::indicator:checked {
                            background-color: #000000;
                        }
                    """
                    
                    # Cell Styling: Distinct Green if Ready
                    cb_container.setStyleSheet("background-color: transparent;")
                    if ready_state:
                         container.setStyleSheet("QFrame { background-color: #22c55e; border-radius: 4px; }")
                         lbl.setStyleSheet("background: transparent; color: white; font-weight: bold; padding-top: 2px;")
                         cb.setStyleSheet(cb_qss)
                    else:
                         row_color = job.get("rowColor") or "transparent"
                         container.setStyleSheet(f"QFrame {{ background-color: {row_color}; border-radius: 4px; }}")
                         lbl.setStyleSheet("background: transparent; color: black; padding-top: 2px;")
                         cb.setStyleSheet(cb_qss)
                    
                    self.frozen_table.setCellWidget(r, c, container)
                    continue

                if key == "colorsVarnish":
                    container = QFrame()
                    # Use a grid layout to maximize space
                    layout = QGridLayout(container)
                    layout.setContentsMargins(2, 2, 2, 2)
                    layout.setSpacing(0)
                    
                    lbl = QLabel(val)
                    lbl.setFont(font)
                    lbl.setWordWrap(True)
                    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                    lbl.setStyleSheet("background: transparent; color: black; border: none;")
                    layout.addWidget(lbl, 0, 0, 1, 2) # Span across columns
                    
                    cb = QCheckBox()
                    cb_container = QWidget()
                    cb_layout = QHBoxLayout(cb_container)
                    cb_layout.setContentsMargins(0, 0, 0, 0)
                    cb_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
                    cb_layout.addWidget(cb)
                    layout.addWidget(cb_container, 1, 1) # Bottom right corner
                    
                    ready_state = job.get("inkReady", False)
                    cb.setChecked(ready_state)
                    
                    # Permission Check
                    user_role = str(self.current_user.get("role", "")).lower()
                    allowed_roles = ["administrator", "planner", "pre-press dep."]
                    cb.setEnabled(user_role in allowed_roles)
                    
                    cb.clicked.connect(lambda checked, j=job: self.on_ink_ready_changed(checked, j))
                    
                    # Small Black Box Styling for Pre-Press (No white background to blend with row)
                    cb_qss = """
                        QCheckBox {
                            background-color: transparent;
                        }
                        QCheckBox::indicator {
                            width: 14px;
                            height: 14px;
                            border: 2px solid #000000;
                            background-color: transparent;
                            border-radius: 2px;
                        }
                        QCheckBox::indicator:checked {
                            background-color: #000000;
                        }
                    """
                    
                    # Cell Styling: Distinct Blue/Green if Ready (using green to match requirement)
                    cb_container.setStyleSheet("background-color: transparent;")
                    if ready_state:
                         container.setStyleSheet("QFrame { background-color: #22c55e; border-radius: 4px; }")
                         lbl.setStyleSheet("background: transparent; color: white; font-weight: bold; padding-top: 2px;")
                         cb.setStyleSheet(cb_qss)
                    else:
                         row_color = job.get("rowColor") or "transparent"
                         container.setStyleSheet(f"QFrame {{ background-color: {row_color}; border-radius: 4px; }}")
                         lbl.setStyleSheet("background: transparent; color: black; padding-top: 2px;")
                         cb.setStyleSheet(cb_qss)
                    
                    self.frozen_table.setCellWidget(r, c, container)
                    continue

                if key == "finishingMachine" and self.filter_category == "production":
                    combo = QComboBox()
                    combo.addItems(finishing_mcs)
                    
                    if val in finishing_mcs:
                        combo.setCurrentText(val)
                    
                    combo.setProperty("job", job)
                    combo.currentTextChanged.connect(lambda text, j=job: self.on_finishing_machine_changed(text, j))
                    
                    self.frozen_table.setCellWidget(r, c, combo)
                    continue

                if key == "status":
                    status_colors = {
                        "completed": ("#22c55e", "white"),    # Green
                        "in_progress": ("#3b82f6", "white"),  # Blue
                        "not_started": ("#e2e8f0", "black")   # Gray
                    }
                    bg_color, fg_color = status_colors.get(val, ("transparent", "black"))

                    is_viewer = self.is_viewer()
                    if is_viewer:
                        display_val = self.format_display_value(key, val)
                        item = QTableWidgetItem(display_val)
                        
                        if val in status_colors:
                            item.setBackground(QColor(bg_color))
                            item.setForeground(QColor(fg_color))
                            font.setBold(True)
                            item.setFont(font)
                            font.setBold(False)
                        else:
                            item.setFont(font)
                            item.setForeground(QColor("#000000"))
                            row_color = job.get("rowColor")
                            if row_color: item.setBackground(QColor(row_color))
                            
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
                        self.frozen_table.setItem(r, c, item)
                    else:
                        cb = QComboBox()
                        cb.addItems(self.STATUS_OPTIONS)
                        cb.setCurrentText(val if val in self.STATUS_OPTIONS else "not_started")
                        cb.currentTextChanged.connect(lambda text, j=job: self.on_status_changed(text, j))
                        
                        row_color = job.get("rowColor")
                        # Status Pill Badge Styling
                        if val in status_colors:
                            cb.setStyleSheet(f"""
                                QComboBox {{ 
                                    background: {bg_color}; border: none; color: {fg_color}; 
                                    padding: 2px 10px; border-radius: 10px; font-weight: bold; margin: 2px 5px; 
                                }} 
                                QComboBox::drop-down {{ border: 0px; }}
                            """)
                        elif row_color:
                            cb.setStyleSheet(f"QComboBox {{ background: {row_color}; border: none; color: black; }}")
                        else:
                            cb.setStyleSheet("QComboBox { background: transparent; border: none; }")
                            
                        self.frozen_table.setCellWidget(r, c, cb)
                        if val not in self.STATUS_OPTIONS: job["status"] = "not_started"
                else:
                    display_val = self.format_display_value(key, val)
                    item = QTableWidgetItem(display_val)
                    item.setFont(font)
                    
                    # Consistent Column Alignment
                    col_key = str(key).lower()
                    col_label = str(col.get("label", "")).lower()

                    if any(x in [col_key, col_label] for x in ["customer", "description"]):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere)
                    else:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
                    
                    if col_key == "pjc":
                        item.setFont(bold_font)
                        
                    item.setForeground(QColor("#000000")) # Black text
                    row_color = job.get("rowColor")
                    
                    # Highlight "New" Order Status explicitly
                    if col_key == "orderstatus" and "new" in str(val).lower():
                        item.setBackground(QColor("#ef4444")) # Bright Red
                        item.setForeground(QColor("#ffffff")) # White text for contrast
                    # Visual Enhancement: Overdue and Urgent Delivery Dates
                    elif col_key == "deliverydate" and val and job.get("status") != "completed":
                        try:
                            from datetime import datetime
                            # Parse expected format YYYY-MM-DD
                            deliv_date = datetime.strptime(val.split("T")[0], "%Y-%m-%d")
                            today = datetime.now()
                            delta_days = (deliv_date - today).days
                            
                            if delta_days < 0: # Overdue
                                item.setBackground(QColor("#fee2e2")) # Light Red
                                item.setForeground(QColor("#991b1b")) # Dark Red
                                font.setBold(True)
                                item.setFont(font)
                                font.setBold(False)
                            elif delta_days <= 3: # Urgent (within 3 days)
                                item.setBackground(QColor("#fef08a")) # Light Yellow
                                item.setForeground(QColor("#a16207")) # Dark Yellow / Orange
                            elif row_color:
                                item.setBackground(QColor(row_color))
                        except Exception as e:
                            if row_color: item.setBackground(QColor(row_color))
                    elif row_color:
                        item.setBackground(QColor(row_color))
                        
                    # Restriction for Viewers
                    if self.is_viewer():
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    else:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                        
                    self.frozen_table.setItem(r, c, item)
                
                # Accumulate totals
                try:
                    if key in ["meters", "mcTime", "totalAmt", "totalRevenue"]:
                        clean_val = val.replace(",", "").replace("MUR", "").strip()
                        if clean_val: column_totals[key] += float(clean_val)
                except: pass
                
            # 2. Populate Scroll Table (Right - Calendar Only)
            if self.show_calendar:
                for d_idx, d in enumerate(dates_info):
                    d_str = d["label"]
                    # Extract and normalize schedule keys for robustness (mismatched case or month names)
                    normalized_sched = {str(k).lower().strip(): v for k, v in job.get("schedule", {}).items()}
                    
                    # Try multiple potential key matches
                    val = ""
                    potential_keys = [d_str, d_str.lower(), d["date"].strftime("%d-%b") if "date" in d else d_str]
                    for pk in potential_keys:
                        if pk.lower().strip() in normalized_sched:
                            val = normalized_sched[pk.lower().strip()]
                            break
                    
                    # Robust numeric check
                    try: 
                        has_work = float(str(val)) > 0 if val else False
                        numeric_val = float(str(val)) if has_work else 0.0
                        daily_hours[d_idx] += numeric_val
                    except: 
                        has_work = False
                        
                    item = QTableWidgetItem(str(val) if has_work else "")
                    item.setFont(font)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    
                    # Restriction for Viewers: Explicitly disable editing flag
                    if self.is_viewer():
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    else:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

                    row_color = job.get("rowColor")
                    if d["is_non_working"]: 
                        item.setBackground(QColor("#f1f5f9"))
                    
                    if has_work: 
                        # Visual Enhancement: Capacity Overload (Red Cell)
                        if daily_hours.get(d_idx, 0.0) > max_shift:
                            item.setBackground(QColor("#ef4444")) # Bright Red (Overload)
                        else:
                            item.setBackground(QColor("#0ea5e9" if job.get("status") != "completed" else "#cbd5e1"))
                            
                        item.setForeground(Qt.GlobalColor.white)
                    elif row_color:
                        item.setBackground(QColor(row_color))
                        item.setForeground(QColor("#000000"))
                    else:
                        item.setForeground(QColor("#000000"))
                    
                    self.table.setItem(r, d_idx, item)

        if self.show_calendar:
            meter_row = len(visible_jobs)
            m_item = QTableWidgetItem("CAPACITY METER (HRS)")
            m_item.setFont(bold_font)
            self.frozen_table.setItem(meter_row, 0, m_item)
            self.frozen_table.item(meter_row, 0).setForeground(QColor("#475569"))
            
            # Fill frozen columns with totals where applicable
            for c in range(1, frozen_count): 
                key = mc["columns"][c]["key"]
                if key in ["meters", "mcTime", "totalAmt", "totalRevenue"]:
                    total_val = column_totals.get(key, 0.0)
                    if total_val > 0:
                        t_item = QTableWidgetItem(f"{total_val:,.2f}")
                        t_item.setFont(bold_font)
                        t_item.setForeground(QColor("#0284c7"))
                        t_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        self.frozen_table.setItem(meter_row, c, t_item)
                    else:
                        m_empty = QTableWidgetItem("")
                        m_empty.setFont(font)
                        self.frozen_table.setItem(meter_row, c, m_empty)
                else:
                    m_empty = QTableWidgetItem("")
                    m_empty.setFont(font)
                    self.frozen_table.setItem(meter_row, c, m_empty)

            machine_shifts = self.settings.get("machineShifts", {})
            shift_limit = float(machine_shifts.get(self.current_machine, self.settings.get("shiftHours", 8)))
            
            for d_idx, d in enumerate(dates_info):
                d_str = d["label"]
                total_hrs = sum(float(j.get("schedule", {}).get(d_str, 0) or 0) for j in mc["jobs"])
                item_val = QTableWidgetItem(f"{total_hrs:,.2f} / {shift_limit:,.2f}")
                item_val.setFont(bold_font)
                item_val.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if d["is_non_working"]: item_val.setBackground(NON_WORKING_BG)
                if total_hrs > shift_limit + 0.01: item_val.setForeground(QColor("#dc2626"))
                elif total_hrs > 0: item_val.setForeground(QColor("#16a34a"))
                self.table.setItem(meter_row, d_idx, item_val)

        # Synchronize Column and Row Sizing
        self.frozen_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        # Scale header heights
        self.frozen_table.horizontalHeader().setFixedHeight(scaled_header_height)
        self.table.horizontalHeader().setFixedHeight(scaled_header_height)
        
        # Maintain manual column widths correctly across all tabs (Planner, Finishing, etc.)
        width_map = {
            "pjc": 60, "customer": 130, "description": 160,
            "deliveryDate": 90, "pjcIn": 75, "prodDeliveryDate": 110,
            "qty": 65, "gearTeeth": 80, "meters": 75, "mcTime": 75, "width": 70,
            "orderStatus": 90, "colValue": 55, "colorsVarnish": 150, "plateId": 120,
            "totalAmt": 80, "dieCut": 75, "status": 95, "progress": 85,
            "startedAt": 80, "completedAt": 80, "notes": 120
        }

        for c, col in enumerate(display_cols):
            key = col["key"]
            base_w = width_map.get(key, 70)
            scaled_w = max(60, int(base_w * self.zoom_level))
            
            # Use custom width if user has manually resized it
            final_w = self.custom_column_widths.get(key, scaled_w)
            self.frozen_table.setColumnWidth(c, final_w)

        if self.show_calendar:
            for j in range(len(dates_info)):
                curr_w = self.table.columnWidth(j)
                # Check for custom width for this calendar column
                cal_key = f"calendar_{j}"
                final_w = self.custom_column_widths.get(cal_key, max(38, curr_w))
                self.table.setColumnWidth(j, final_w)

        # Ensure vertical headers match and sync heights
        for r in range(self.frozen_table.rowCount()):
            self.table.setRowHeight(r, scaled_row_height)
            self.frozen_table.setRowHeight(r, scaled_row_height)

        # Allow the frozen table to have its own horizontal scrollbar since it holds all data
        self.frozen_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Calculate ideal width based on content
        self.frozen_table.verticalHeader().setFixedWidth(int(40 * self.zoom_level))
        header_width = self.frozen_table.verticalHeader().width()
        content_width = self.frozen_table.horizontalHeader().length()
        total_ideal_width = header_width + content_width + 5
        
        # Display Logic: Single vs Dual Table
        if not self.show_calendar:
            # Finishing Tab Style: Single Full-Width Table
            self.table.setVisible(False)
            
            # Dynamic Full Width: Account for margins and vertical header
            v_header_w = self.frozen_table.verticalHeader().width()
            available_w = self.width() - v_header_w - 60 
            self.frozen_table.setFixedWidth(max(800, available_w))
            
            self.frozen_table.horizontalHeader().setStretchLastSection(True)
            self.frozen_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            # Planner Tab Style: Dual Table (Frozen Data + Scrollable Calendar)
            self.table.setVisible(True)
            self.frozen_table.horizontalHeader().setStretchLastSection(False)
            self.frozen_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            
            # Limit the frozen table to a maximum of 75% of the total widget width so the calendar is still visible
            max_allowed_width = int(self.width() * 0.75)
            
            # Set width to either the full content (if it fits) or the 75% max (which will trigger the scrollbar)
            final_width = min(total_ideal_width, max_allowed_width)
            
            # Fallback safeguard in case widget hasn't rendered width yet
            if final_width < 200: final_width = 800
            
            self.frozen_table.setFixedWidth(final_width)

        self.footer_label.setText(f"Machine: {self.current_machine} | Visible: {len(visible_jobs)} / {len(mc['jobs'])}")
        self.table.blockSignals(False)
        self.frozen_table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.frozen_table.setUpdatesEnabled(True)
        # Force a refresh of the viewport after enabling updates
        self.table.viewport().update()
        self.frozen_table.viewport().update()
        
        # Hide calendar toggle in finishing, packing, and delivery
        if hasattr(self, 'cal_toggle'):
            self.cal_toggle.setVisible(self.filter_category not in ["finishing", "packing", "delivery"])
            
        self._is_refreshing = False # Re-enable resize monitoring

    def on_column_resized(self, index, old_size, new_size):
        """Captures manual column resizing by the user and stores it to prevent resets."""
        if self._is_refreshing: return
        
        sender = self.sender()
        if sender == self.frozen_table.horizontalHeader():
            mc = self.all_machines_data.get(self.current_machine, {})
            display_cols = self.get_display_columns(mc)
            if index < len(display_cols):
                key = display_cols[index]["key"]
                self.custom_column_widths[key] = new_size
        elif sender == self.table.horizontalHeader():
            cal_key = f"calendar_{index}"
            self.custom_column_widths[cal_key] = new_size

    def resizeEvent(self, event):
        """Trigger a table refresh on window resize to ensure full-width tables fit correctly."""
        super().resizeEvent(event)
        # We use a slight delay to avoid over-refreshing during smooth dragging
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer()
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self.refresh_table)
        self._resize_timer.start(50)

    def on_machine_selector_changed(self, text):
        if text:
            self.current_machine = text
            self.refresh_table()
            self.machine_changed.emit(text)

    def on_finishing_machine_changed(self, text, job):
        job["finishingMachine"] = text
        api_service.log_to_file(f"UI: PJC {job.get('pjc')} set finishing machine to {text}")
        self.save_data()
        self.granular_save(job)

        self.refresh_table()

    def on_plate_ready_changed(self, checked, job):
        job["plateReady"] = checked
        pjc = job.get("pjc", "Unknown")
        api_service.log_to_file(f"UI: PJC {pjc} plateReady set to {checked}")
        self.save_data()
        self.granular_save(job)
        self.refresh_table()

    def on_ink_ready_changed(self, checked, job):
        job["inkReady"] = checked
        pjc = job.get("pjc", "Unknown")
        api_service.log_to_file(f"UI: PJC {pjc} inkReady set to {checked}")
        self.save_data()
        self.granular_save(job)
        self.refresh_table()

    def is_viewer(self):
        """Helper to check if the current user is a viewer or restricted pre-press dep."""
        user_role = str(self.current_user.get("role", "")).lower()
        return user_role in ["viewer", "pre-press dep."]
