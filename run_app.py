
import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication

# 1. Setup paths correctly
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add both root and py_planner to sys.path for maximum compatibility
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
py_planner_dir = os.path.join(current_dir, "py_planner")
if py_planner_dir not in sys.path:
    sys.path.insert(0, py_planner_dir)

# 2. Setup Global Error Logging (Simple console-only for debug)
def exception_hook(exctype, value, tb):
    error_msg = "".join(traceback.format_exception(exctype, value, tb))
    print(error_msg, file=sys.stderr)
    sys.exit(1)

sys.excepthook = exception_hook

# 3. Import and Run
try:
    from py_planner.main_window import MainWindow
    from py_planner.components.login_dialog import LoginDialog
    from py_planner.components.sql_config_wizard import SQLConfigWizard
    from py_planner.utils.planner_utils import load_planner_data
except ModuleNotFoundError:
    from main_window import MainWindow
    from components.login_dialog import LoginDialog
    from components.sql_config_wizard import SQLConfigWizard
    from utils.planner_utils import load_planner_data

def run_production_planner():
    app = QApplication(sys.argv)
    
    # 1. Resolve Data Path
    # ALWAYS use APPDATA as the writable location so writes never go to
    # Program Files (which is read-only for standard users on installed builds).
    import os
    import shutil
    appdata_root = os.path.join(os.environ["APPDATA"], "ProductionPlanning")
    os.makedirs(appdata_root, exist_ok=True)
    data_file = os.path.join(appdata_root, "test_planning_100_jobs.json")

    if not os.path.exists(data_file):
        # Bootstrap: copy the bundled default file from the internal/install dir into APPDATA
        # so all future reads AND writes use the writable APPDATA copy.
        bundled_candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "py_planner", "test_planning_100_jobs.json"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_planning_100_jobs.json"),
        ]
        for candidate in bundled_candidates:
            if os.path.exists(candidate):
                try:
                    shutil.copy2(candidate, data_file)
                    print(f"BOOTSTRAP: Copied default data file from {candidate} to {data_file}")
                except Exception as copy_err:
                    print(f"BOOTSTRAP WARNING: Could not copy bundled data file: {copy_err}")
                break
    
    data = load_planner_data(data_file)
    initial_settings = data.get("appSettings", {})
    
    # Create a container so we can update the reference dynamically
    data_container = {"current": data}
    
    # 1b. START API SERVER EARLY (So Floor View can connect even before login)
    try:
        from py_planner.api.api_server import start_api_server
        api_port = 8000 # Default port for Planning App
        # Use lambda to access the latest data in the container
        start_api_server(lambda: data_container["current"], port=api_port)
        print(f"API SERVER: Started on port {api_port} (Pre-Login Active)")
    except Exception as e:
        print(f"FAILED TO START API SERVER EARLY: {e}")
    
    # CLEANUP: Robustly extract SQL config (handle both nested and flat fields)
    s = initial_settings
    sql_config = s.get("sqlConfig", {})
    # Map flat fields if nested ones are missing (as used in newer SettingsView)
    if not sql_config.get("server"):
        sql_config["server"] = s.get("sqlServer")
        sql_config["database"] = s.get("sqlDatabase")
        sql_config["user"] = s.get("sqlUser")
        sql_config["password"] = s.get("sqlPassword")
        sql_config["driver"] = s.get("sqlDriver", "{ODBC Driver 17 for SQL Server}")

    # Normalize: always ensure table and driver are present in sql_config.
    # The first-run wizard saves nested sqlConfig without a "table" key; the Settings view
    # saves sqlTableView as a flat key. Merging here ensures PJC fetch works on first boot.
    if not sql_config.get("table") or sql_config.get("table") == "YourViewName":
        sql_config["table"] = s.get("sqlTableView", "")
    if not sql_config.get("driver"):
        sql_config["driver"] = s.get("sqlDriver", "{ODBC Driver 17 for SQL Server}")

    if sql_config.get("database") == "API_MODE":
        print("CLEANUP: Removing Floor View API settings from Main App SQL config...")
        data["appSettings"]["sqlConfig"] = {}
        data["appSettings"]["sqlServer"] = None
        sql_config = {}
        
        # We need to use the imported save function
        from py_planner.utils.planner_utils import save_planner_data
        save_planner_data(data_file, data)
        
        initial_settings = data["appSettings"]
        sql_config = {}
    
    # 2. Check for First-Run SQL Config
    # Inject hardcoded config if missing in local JSON
    from floor_view.api.sql_service import SQL_CONFIG
    if not sql_config.get("server") and SQL_CONFIG.get("server"):
        print("BOOTSTRAP: Injecting hardcoded SQL configuration...")
        if "sqlConfig" not in data["appSettings"]: 
            data["appSettings"]["sqlConfig"] = {}
        data["appSettings"]["sqlConfig"].update(SQL_CONFIG)
        sql_config = data["appSettings"]["sqlConfig"]

    # If STILL no server AND not explicitly marked offline, show wizard (should be skipped now)
    if not sql_config.get("server") and not sql_config.get("offline"):
        print("SQL NOT CONFIGURED. LAUNCHING SETUP WIZARD...")
        wizard = SQLConfigWizard(data_file, data, is_floor_view=False)
        if wizard.exec():
            # Reload data after wizard save
            data = load_planner_data(data_file)
            data_container["current"] = data
            sql_config = data.get("appSettings", {}).get("sqlConfig", {})
        else:
            print("SETUP CANCELLED. EXITING.")
            sys.exit(0)
    
    print(f"TRACE: Entering user fetch loop...", flush=True)
    while True:
        # 3. Fetch Users (Prioritize SQL, with fast fail) inside loop for real-time updates
        users = []
        sql_config = data.get("appSettings", {}).get("sqlConfig", {})
        if sql_config.get("server"):
            print(f"CONNECTING TO SQL: {sql_config.get('server')}...")
            try:
                from floor_view.api import sql_service
                users = sql_service.get_sql_users(sql_config, timeout=2)
                if users:
                    print(f"SQL SYNC: Retrieved {len(users)} users: {[u['name'] for u in users]}")
                    # Inject SQL users into the data object so UI sees them
                    if "appSettings" not in data: data["appSettings"] = {}
                    data["appSettings"]["users"] = users
                else:
                    print("SQL SYNC: No users retrieved from SQL database.")
            except Exception as e:
                print(f"SQL SYNC WARNING: Could not fetch users ({e}). Falling back to local.")

        if not users:
            users = data.get("appSettings", {}).get("users", [])
            if not users:
                users = [
                    {"name": "Admin", "role": "Administrator", "password": "admin", "permissions": "planner,finishing,packing,delivery,records,summary,settings,about"},
                    {"name": "Planner", "role": "Planner", "password": "pass", "permissions": "planner,finishing,packing,delivery,records,summary,about"}
                ]
            
        # DATA MIGRATION: Forced rename for all existing users and strip removed permissions
        removed_perms = {"dashboard", "efficiency", "financial", "strategic"}
        for u in users:
            if u.get("role") == "Plate Making":
                u["role"] = "Pre-Press Dep."
            
            # Clean up permissions and ensure primary ones are present
            current_perms = set(str(u.get("permissions", "")).lower().split(","))
            primary_perms = {"planner", "finishing", "packing", "delivery"}
            clean_perms = (current_perms - removed_perms) | primary_perms
            u["permissions"] = ",".join([p for p in clean_perms if p])
            
        # PROACTIVE INJECTION: Ensure "Pre-Press Dep." role exists even for existing/SQL installs
        if not any(u.get("role") == "Pre-Press Dep." for u in users):
            users.append({"name": "Pre-Press", "role": "Pre-Press Dep.", "password": "plate", "permissions": "planner,finishing,packing,delivery,about"})
            # Preserve in local data as fallback
            if "appSettings" not in data: data["appSettings"] = {}
            data["appSettings"]["users"] = users
            print("BOOTSTRAP: Injected 'Pre-Press Dep.' role into user list.")

        # 4. Show Login
        # 3. Show Login First
        login = LoginDialog(users)
        if login.exec():
            user = login.authorized_user
            print(f"AUTHENTICATED: {user['name']} ({user['role']})")
            
            # Update LastLogin in SQL if possible
            if sql_config.get("server"):
                try:
                    from floor_view.api import sql_service
                    sql_service.update_sql_user_login(user['name'], sql_config)
                except: pass

            try:
                window = MainWindow(user, data_container=data_container)
                window.showMaximized()
                app.exec()
                
                # Check if we should exit or restart the login loop
                if getattr(window, 'is_logging_out', False):
                    print(f"USER LOGGED OUT: {user['name']}. Restarting session...")
                    continue
                else:
                    print("APP CLOSED NORMALLY.")
                    break
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                error_title = "Critical Startup Error"
                error_text = f"The application failed to initialize:\n\n{str(e)}\n\n{traceback.format_exc()}"
                print(f"CRITICAL UI ERROR: {e}")
                traceback.print_exc()
                QMessageBox.critical(None, error_title, error_text)
                break
        else:
            print("LOGIN CANCELLED. EXITING.")
            break

if __name__ == "__main__":
    print("BOOTSTRAP: Starting Production Planner...", flush=True)
    run_production_planner()
