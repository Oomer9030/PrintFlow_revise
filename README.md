# Production Planner - Platinum Hybrid Engine

A high-performance, professional production planning application built with Python and PyQt6. This tool integrates seamlessly with Microsoft SQL Server and the LabelTraxx API to provide real-time production visibility, scheduling optimization, and strategic insights.

## Key Features

- Hybrid Data Gateway: Toggle between Microsoft SQL Server and LabelTraxx API for data synchronization.
- Intelligent Filtering: Automatically hides completed jobs to maintain a clean workspace (togglable via "Unhide" button).
- Dynamic Dashboard & KPIs: Real-time visualizations with unified category filtering (Planner vs. Finishing) across all analytics tabs.
- Granular Permissions: Secure access control with Role-Based Access Control (RBAC) locking critical system settings to Administrators only.
- Premium UI: Modern dark-themed interface with high-contrast text and fluid animations.
- Automated Reporting: Built-in PDF generation for production schedules and reports.

## Tech Stack

- Core: Python 3.12+
- GUI: PyQt6
- Database: pyodbc (MS SQL Server)
- API: LabelTraxx Integration
- Analytics: Pandas, Matplotlib
- Build: PyInstaller, Inno Setup

## Installation & Build

### Using the Installer
Locate the `ProductionPlannerSetup.exe` in the `InstallerOutput` directory and run it to install the application on Windows.

### Building from Source
1. Install dependencies:
   bash
   pip install -r requirements.txt

2. Run the application:
   bash
   python run_app.py

3. Build standalone executable:
   bash
   pyinstaller --clean production_planner.spec
  
4. Build Windows Setup:
   Compile `production_planner_setup.iss` using Inno Setup 6.

## Permissions Policy
- Administrator: Full access to all features and settings.
- Planner: Full planning and record access.
- Viewer: Read-only access. Tabs are strictly filtered based on assigned permissions. Completed jobs are hidden by default.


Created by Oomer Smart Applications - Author Mohamad Oomer Habib Moussa
