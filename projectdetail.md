# Project Technical Details: PrintFlow Pro

This document outlines the specific logic, architectural patterns, and synchronization mechanisms used in the PrintFlow Pro application.

## 1. Core Architecture
- Framework: Built with PyQt6 for a high-performance, native desktop experience.
- Component-Based UI: The application is structured into reusable components (e.g., `PlanningTable`, `SettingsView`, `AllRecordsView`) managed by a `QStackedWidget` for seamless navigation.
- Role-Based Access Control (RBAC):
    - Administrator: Full access to all tabs, editing, and engine settings.
    - Planner/Operator: Access to production tabs (Planner, Finishing, etc.) with full editing.
    - Viewer: Read-only access; the UI automatically disables drag-and-drop, cell triggers, and context menus.

## 2. Bootstrapping & Data Handling (`run_app.py`)
- AppData Isolation: To ensure compatibility with Windows security (e.g., Program Files being read-only), all writable data and logs are isolated in `%APPDATA%\ProductionPlanning`.
- JSON Bootstrapping: If no data exists, the app automatically copies a bundled `test_planning_100_jobs.json` template to the AppData folder.
- SQL Normalization: On startup, it synchronizes "legacy" configuration keys into a modern `sqlConfig` structure to maintain backward compatibility with older data files.
- Early API Startup: Start an internal FastAPI-like server on port 8000 before login, allowing external "Floor Views" to see the active plan even if the main UI is closed.

## 3. Synchronization Mechanism (The "Live Engine")
The app uses a sophisticated multi-user sync logic to prevent data collisions:

### A. Granular SQL Save
- Instead of saving the whole database (which is slow), the app uses `granular_save`.
- Logic: Any change to a single cell (Status, PJC, Quantity) triggers a background thread that executes a SQL MERGE (UPSERT) query. 
- Non-Blocking: Because it runs in a `threading.Thread`, the UI never lags during network operations.

### B. Background Status Sync
- Status Worker: A background polling thread runs every 30 seconds.
- API Integration: It fetches live job statuses from the LabelTraxx API.
- Translation Logic: API responses (e.g., "Press Run", "Washup") are automatically translated into internal statuses ("in_progress", "completed") using pattern matching.
- Auto-Persistence: When a status change is detected, the app automatically updates the UI and pushes the new status to the SQL table immediately.

### C. Multi-User Live Sync
- Change Signaling: Every write to SQL updates a `LastUpdated` timestamp in the `Production_Planner_State` table.
- Polling Logic: Every 15 seconds, all open app instances check this timestamp. If it has changed, the app triggers a "Soft Reload" to fetch new data without losing the user's current scroll position or selection.

## 4. SQL Integration & Data Sanitization (`sql_service.py`)
- Dynamic ODBC Detection: The app automatically detects the best available driver (e.g., ODBC Driver 17 or 18) for SQL Server.
- Data Sanitization: 
    - Currency/Units: Logic automatically strips symbols like "$" or "MUR" and units like "m" from inputs, converting them to proper floats before sending them to SQL.
    - Date Parsing: A robust parser handles various date formats (ISO, DD-MMM-YY) to prevent SQL insertion errors.
- Deletions: A dedicated `delete_job_from_sql` function ensures that when a row is removed from the UI, its `RowID` is instantly purged from the SQL Server table.

## 5. UI Interactivity (`planning_table.py`)
- Drag-to-Fill: Selecting a cell and dragging handles allows for bulk-filling data, similar to Excel.
- MimeData DND: Uses custom MimeData formats to handle job migration between different machine boards (e.g., moving a job from "PRINTER 1" to "PRINTER 2").
- Visual Feedback: Row colors are dynamically applied based on job status or manual overrides preserved in the SQL record.
