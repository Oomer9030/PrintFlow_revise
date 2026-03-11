import pyodbc
from typing import List, Dict, Tuple, Optional
import os
import copy
from datetime import datetime, timedelta

def get_safe_table_name(config: Dict, default: str = "Production_Planner_Export") -> str:
    """Helper to get a bracketed table name from config, falling back to default."""
    raw = config.get("table") or default
    return f"[{raw}]" if not str(raw).startswith("[") else str(raw)

def find_best_driver() :
    """Detects available ODBC drivers and picks the best modern one."""
    drivers = pyodbc.drivers()
    # print(f"SQL Service: Detected ODBC Drivers on this system: {drivers}")
    
    # Keyword-based search to avoid brace/naming variations
    keywords = ["Driver 18", "Driver 17", "Driver 13", "Driver 11", "SQL Server Native Client"]
    
    for kw in keywords:
        for d in drivers:
            if kw.lower() in d.lower():
                # print(f"SQL Service: Found matching modern driver: {d}")
                # Ensure it's wrapped in braces for the connection string
                return f"{{{d}}}" if not d.startswith("{") else d

    # Fallback to legacy if nothing modern found
    for d in drivers:
        if "SQL Server" in d:
            return f"{{{d}}}" if not d.startswith("{") else d
            
    return "{SQL Server}"

# CONFIGURATION & STATE
_LAST_SQL_FAILURE = None
_LAST_ERROR_MSG = "None"
SQL_OFFLINE_COOLDOWN = 15 # Seconds to wait before retrying after a hard failure

# Configuration for SQL Server
# HARDCODED PROD CONFIG
SQL_CONFIG = {
    "server": "192.168.1.11",
    "database": "awol_stagging",
    "driver": "{ODBC Driver 18 for SQL Server}",
    "user": "awol_reporting",
    "password": "awol@12345",
    "table": "Production_Planner_Export" # Default table from app context
}

COLUMN_MAPPING = {
    "Number": "pjc",
    "CustomerName": "customer",
    "GeneralDescr": "description",
    "Ship_by_Date": "deliveryDate",
    "OrderDate": "pjcIn",
    "ticQuantity": "qty",
    "EstFootage": "meters",
    "EstTime": "mcTime",
    "StockWidth2": "width",
    "JOBTYPE": "orderStatus",
    "NOCOLORS": "colValue",
    "COLORDESCR": "colorsVarnish",
    "Plate_ID": "plateId",
    "Customer_Total": "totalAmt",
    "MainTool": "dieCut",
    "ProdDeliveryDate": "prodDeliveryDate"
}

def get_connection(config: Dict, timeout: int = 5):
    global _LAST_SQL_FAILURE, _LAST_ERROR_MSG
    try:
        # Check for cooldown to avoid hanging the UI with repeated failed connections
        if _LAST_SQL_FAILURE:
            elapsed = (datetime.now() - _LAST_SQL_FAILURE).total_seconds()
            if elapsed < SQL_OFFLINE_COOLDOWN:
                # Still in cooldown, skip attempt
                return None

        server = config.get("server") or config.get("sqlServer")
        database = config.get("database") or config.get("sqlDatabase")
        user = (config.get("user") or config.get("sqlUser") or "").strip()
        password = (config.get("password") or config.get("sqlPassword") or "").strip()
        
        driver = config.get("driver") or config.get("sqlDriver")
        
        # Dynamic Driver Validation: If the specified driver isn't installed here, find the best one that IS.
        # This prevents "Data source name not found" when moving from PC with v17 to PC with v18.
        available_drivers = pyodbc.drivers()
        system_best_driver = find_best_driver()
        
        # Clean versions for comparison
        clean_driver = (driver or "").strip("{}").lower()
        clean_available = [d.lower() for d in available_drivers]
        
        # 1. If no driver specified or driver not installed, use system best
        if not driver or clean_driver not in clean_available:
            # print(f"SQL Service: Using discovered driver '{driver}' instead.")
            driver = system_best_driver
        
        # 2. Aggressive Upgrade: If legacy driver is specified but a modern one (17/18) is available, UPGRADE IT.
        # This fixes the issue on Primary PC where it has Driver 18 but something (config or fallback) is forcing "{SQL Server}"
        elif clean_driver == "sql server" and "odbc driver" in system_best_driver.lower():
            # print(f"SQL Service: Upgrading from legacy '{driver}' to modern system driver '{system_best_driver}' for better compatibility.")
            driver = system_best_driver
            
        # Port handling
        port = config.get("port") or config.get("sqlPort")
        server_str = f"{server},{port}" if port else server

        # Auth Handling: Use Trusted_Connection if UID is empty
        auth_part = f"UID={user};PWD={password}" if user else "Trusted_Connection=yes"

        clean_driver = driver.strip("{}").lower()
        if "driver 18" in clean_driver:
            conn_str = f"DRIVER={driver};SERVER={server_str};DATABASE={database};{auth_part};LoginTimeout={timeout};Encrypt=no;TrustServerCertificate=yes"
        elif "driver 17" in clean_driver or "driver 13" in clean_driver or "driver 11" in clean_driver:
            conn_str = f"DRIVER={driver};SERVER={server_str};DATABASE={database};{auth_part};LoginTimeout={timeout};Encrypt=no"
        elif "sql server" == clean_driver:
            # Legacy driver: absolutely NO extra attributes like LoginTimeout or Encrypt
            conn_str = f"DRIVER={driver};SERVER={server_str};DATABASE={database};{auth_part}"
        else:
            conn_str = f"DRIVER={driver};SERVER={server_str};DATABASE={database};{auth_part};LoginTimeout={timeout}"
        
        # print(f"SQL Service: Attempting connection with: {driver} to {server_str} (Auth: {'SQL' if user else 'Windows'})", flush=True)
        # print(f"SQL Service: Connection string: {conn_str}", flush=True)
        
        # Use a thread to enforce a strict timeout if pyodbc hangs
        import threading
        result = [None]
        error = [None]
        
        def connect_thread():
            try:
                result[0] = pyodbc.connect(conn_str)
            except Exception as e:
                error[0] = e
        
        t = threading.Thread(target=connect_thread, daemon=True)
        t.start()
        t.join(timeout + 2) # Give it 2 extra seconds for overhead
        
        if t.is_alive():
            return None
            
        if error[0]:
            print(f"Connection Error: {error[0]}", flush=True)
            _LAST_SQL_FAILURE = datetime.now()
            _LAST_ERROR_MSG = str(error[0])
            return None
            
        conn = result[0]
        _LAST_SQL_FAILURE = None # Reset on success
        return conn
    except Exception as e:
        _LAST_SQL_FAILURE = datetime.now()
        _LAST_ERROR_MSG = str(e)
        print(f"Connection Error: {e}")
        return None # Return None instead of raising to allow graceful fallback

def parse_sql_datetime(val):
    """Robust date parser for SQL export, supporting ISO, DD-MMM, and YYYY-MM-DD HH:MM:SS."""
    if isinstance(val, datetime):
        return val
    if not val or str(val).lower() in ["none", "nan", "null", ""]:
        return None
        
    v_str = str(val).strip()
    
    # 1. ISO format (e.g., 2026-02-26T07:59:21)
    try:
        return datetime.fromisoformat(v_str.replace("Z", ""))
    except:
        pass
        
    # 2. Planning DD-MMM format (e.g., 26-Feb)
    try:
        curr_year = datetime.now().year
        # Handle cases where year is already present
        if len(v_str.split('-')) == 3:
             return datetime.strptime(v_str, "%d-%b-%Y")
        return datetime.strptime(f"{v_str}-{curr_year}", "%d-%b-%Y")
    except:
        pass
        
    # 3. SQL Standard (e.g., 2026-02-26 07:59:21)
    try:
        return datetime.strptime(v_str, "%Y-%m-%d %H:%M:%S")
    except:
        pass
        
    # 4. Fallback for ISO strings with space instead of T
    try:
        return datetime.fromisoformat(v_str.replace(" ", "T"))
    except:
        pass
        
    return None

def get_bulk_job_data(job_numbers: List[str], config: Optional[Dict] = None) -> List[Dict]:
    """
    Fetches job data for multiple PJCs from SQL Server.
    If connection fails (expected in dev), returns empty list or logged error.
    """
    if not job_numbers:
        return []

    try:
        if not config or not config.get("server"):
            return []

        conn = get_connection(config)
        if not conn: return []
        cursor = conn.cursor()
        
        # Clean job numbers (remove whitespace)
        clean_job_numbers = [str(n).strip() for n in job_numbers]
        placeholders = ', '.join(['?' for _ in clean_job_numbers])
        table_name = config.get("table", "YourViewName")
        
        # Correctly escape schema-qualified names: dbo.Table.v0.2 -> [dbo].[Table.v0.2]
        if "." in table_name and not table_name.startswith("["):
            # Split only once at the first dot to separate schema from table
            parts = table_name.split(".", 1)
            safe_table = ".".join([f"[{p}]" for p in parts])
        elif not table_name.startswith("["):
            safe_table = f"[{table_name}]"
        # Discovery: Get column names to identify the ID column (PJC or Number)
        cursor.execute(f"SELECT TOP 0 * FROM {safe_table}")
        all_cols = [column[0] for column in cursor.description]
        
        # Identify the "PJC" or "Number" column
        id_col = "Number" # Default
        id_candidates = ["Number", "PJC", "Job_Number", "JobNumber", "TIC_Number", "TIC"]
        for cand in id_candidates:
            if cand in all_cols:
                id_col = cand
                break
            # Case-insensitive check
            found = False
            for real_col in all_cols:
                if cand.lower() == real_col.lower():
                    id_col = real_col
                    found = True
                    break
            if found: break

        # print(f"SQL Service: Using '{id_col}' as the ID column for PJC lookup.")
        
        # Robust query handling whitespace and type differences
        query = f"SELECT * FROM {safe_table} WHERE LTRIM(RTRIM(CAST({id_col} AS VARCHAR))) IN ({placeholders})"
        
        cursor.execute(query, clean_job_numbers)
        
        columns = [column[0] for column in cursor.description]
        results = []
        rows = cursor.fetchall()
        # print(f"SQL Service: Found {len(rows)} matching records.")
        
        for row in rows:
            row_dict = dict(zip(columns, row))
            mapped_job = {}
            row_keys_lower = {k.lower().replace("_", ""): k for k in row_dict.keys()}
            
            # LOGGING: Print all keys found to help debugging
            # if len(results) == 0:
            #     print(f"SQL Service: Found Keys: {list(row_dict.keys())}")

            for sql_pref, app_key in COLUMN_MAPPING.items():
                val = ""
                # Priority 1: Exact mapping
                if sql_pref in row_dict:
                    val = row_dict[sql_pref]
                else:
                    # Priority 2: Fuzzy mapping (case-insensitive, ignoring underscores)
                    clean_pref = sql_pref.lower().replace("_", "")
                    if clean_pref in row_keys_lower:
                        val = row_dict[row_keys_lower[clean_pref]]
                    else:
                        # Priority 3: Common alias hunting
                        aliases = []
                        if app_key == "customer": aliases = ["CustomerName", "CustName", "Customer", "Client"]
                        elif app_key == "description": aliases = ["GeneralDescr", "JobDescription", "Description", "Desc"]
                        elif app_key == "qty": aliases = ["ticQuantity", "Quantity", "Qty", "OrderQty"]
                        
                        for alias in aliases:
                            clean_alias = alias.lower().replace("_", "")
                            if clean_alias in row_keys_lower:
                                val = row_dict[row_keys_lower[clean_alias]]
                                break
                
                mapped_job[app_key] = str(val if val is not None else "").strip()
            
            # Explicitly handle status translation if present
            status_col = None
            for p in ["LastWorkOperation", "Status", "JobStatus", "CurrentStatus", "Operation", "LastOp"]:
                clean_p = p.lower()
                if clean_p in row_keys_lower:
                    status_col = row_keys_lower[clean_p]
                    break
                    
            if status_col:
                mapped_job["status"] = translate_sql_status(str(row_dict[status_col]))
                
            # Include priority for re-ordering
            mapped_job["priority"] = row.Priority if hasattr(row, 'Priority') else 0.0
            
            # Sanitize common string fields to avoid NoneType crashes
            for str_field in ["notes", "rowColor", "customer", "description", "orderStatus"]:
                if mapped_job.get(str_field) is None:
                    mapped_job[str_field] = ""

            results.append(mapped_job)
        
        conn.close()
        return results
        
    except Exception as e:
        return []

def translate_sql_status(sql_val: str) -> str:
    """
    Maps SQL LastWorkOperation to internal app status.
    """
    if sql_val is None or str(sql_val).strip() == "" or str(sql_val).lower() == "none":
        return "not_started"
    
    val = str(sql_val).strip().lower()
    
    # Priority 1: Terminal/Completed States (Check these FIRST)
    if any(k in val for k in ["complete", "done", "finished", "washup", "wash up", "wash-up"]):
        return "completed"
        
    # Priority 2: In-Progress States
    if any(k in val for k in ["make ready", "preparing", "setup", "run", "process", "printing", "finishing", "active"]):
        return "in_progress"
        
    # Priority 3: Other States
    if any(k in val for k in ["hold", "paused"]):
        return "on_hold"
    if "cancel" in val:
        return "cancelled"
    
    return "not_started"

def get_live_job_statuses(job_numbers: List[str], config: Dict) -> Dict[str, str]:
    """
    Polled by the app to update statuses for specific PJCs.
    Uses ROW_NUMBER() to ensure we get the LAST entry if multiple exist in a view.
    """
    if not job_numbers or not config or not config.get("server"):
        return {}
    
    try:
        conn = get_connection(config)
        if not conn: return {}
        cursor = conn.cursor()
        
        clean_pjcs = [str(n).strip() for n in job_numbers]
        placeholders = ', '.join(['?' for _ in clean_pjcs])
        
        # Use specialized status view if provided, otherwise fallback to main table
        table_name = config.get("status_view") or config.get("table", "YourViewName")
        
        # Correctly escape table name
        if "." in table_name and not table_name.startswith("["):
            parts = table_name.split(".", 1)
            safe_table = ".".join([f"[{p}]" for p in parts])
        else:
            safe_table = table_name if table_name.startswith("[") else f"[{table_name}]"
        
        # Detect columns in the status view
        cursor.execute(f"SELECT TOP 1 * FROM {safe_table}")
        all_cols = [column[0] for column in cursor.description]
        
        # Identify the ID column (Number/PJC/etc)
        id_col = "Number" # Default
        id_candidates = ["Number", "PJC", "Job_Number", "JobNumber", "TIC_Number", "TIC"]
        for cand in id_candidates:
            if cand in all_cols:
                id_col = cand
                break
            # Case-insensitive check
            found = False
            for real_col in all_cols:
                if cand.lower() == real_col.lower():
                    id_col = real_col
                    found = True
                    break
            if found: break
            
        
        # Identify Status Column
        status_col = "LastWorkOperation" # Default
        status_candidates = ["LastWorkOperation", "Status", "JobStatus", "CurrentStatus", "Operation", "LastOp"]
        for cand in status_candidates:
            if cand in all_cols:
                status_col = cand
                break
            # Case-insensitive check
            found = False
            for real_col in all_cols:
                if cand.lower() == real_col.lower():
                    status_col = real_col
                    found = True
                    break
        
        # Optimized query: Partition by the detected ID column and sort by DateTime to get the latest row
        dt_col = config.get("status_dt_col", "DateTime")
        
        query = f"""
        SELECT {id_col}, {status_col} FROM (
            SELECT {id_col}, {status_col}, 
            ROW_NUMBER() OVER(PARTITION BY {id_col} ORDER BY {dt_col} DESC) as rn
            FROM {safe_table}
            WHERE LTRIM(RTRIM(CAST({id_col} AS VARCHAR))) IN ({placeholders})
        ) t WHERE rn = 1
        """
        
        try:
            cursor.execute(query, clean_pjcs)
        except Exception as e:
            # Fallback for tables without the assumed DateTime column or Window Function support
            if "DateTime" not in str(e):
                pass
            # Fetch * to allow fuzzy status detection in fallback too
            query = f"SELECT {id_col}, * FROM {safe_table} WHERE LTRIM(RTRIM(CAST({id_col} AS VARCHAR))) IN ({placeholders})"
            cursor.execute(query, clean_pjcs)
        
        columns = [column[0] for column in cursor.description]
        status_map = {}
        for row in cursor.fetchall():
            row_dict = dict(zip(columns, row))
            # Use the detected columns or fallback search
            pjc = str(row_dict.get(id_col) or row_dict.get("Number") or row_dict.get("pjc") or "").strip()
            if not pjc: continue
            
            # Detect status column if not already set
            status_val = str(row_dict.get(status_col) or "")
            if not status_val:
                for p in ["LastWorkOperation", "Status", "JobStatus", "CurrentStatus", "Operation", "LastOp"]:
                    found_key = next((k for k in row_dict.keys() if k.lower() == p.lower()), None)
                    if found_key:
                        status_val = str(row_dict[found_key])
                        break
            
            if status_val:
                translated = translate_sql_status(status_val)
                # Print debug info for all jobs to help pinpoint the issue
                print(f"DEBUG STATUS SYNC: Job {pjc} Raw: '{status_val}', Translated: '{translated}'")
                status_map[pjc] = translated
                
        conn.close()
        return status_map
    except Exception as e:
        return {}

def translate_sql_status(api_val: str) -> str:
    """
    Maps SQL Status View values to internal app status.
    """
    if not api_val or str(api_val).strip() == "":
        return "not_started"
    
    val = str(api_val).strip().lower()
    
    # "Wash Up" or "Complete" -> completed
    if "washup" in val or "wash up" in val or "wash-up" in val or "complete" in val:
        return "completed"
        
    # "Run", "Process", "Make Ready", "Preparing" -> in_progress
    if "make ready" in val or "preparing" in val or "run" in val or "process" in val:
        return "in_progress"
    
    # Default to not_started if unrecognized
    return "not_started"

def ensure_app_state_table_exists(config: Dict):
    """Stores machines, appSettings, and overall environment state."""
    try:
        if not config or not config.get("server"): return
        conn = get_connection(config)
        if not conn: return
        cursor = conn.cursor()
        
        # Table for global settings/machines as a JSON blob or structured
        # For simplicity and flexibility, we'll store the 'appSettings' and 'machines' list here
        table_name = "Production_Planner_State"
        cursor.execute(f"""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{table_name}' AND xtype='U')
            CREATE TABLE {table_name} (
                KeyName NVARCHAR(100) PRIMARY KEY,
                ValueData NVARCHAR(MAX),
                LastUpdated DATETIME DEFAULT GETDATE()
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def load_full_plan_from_sql(config: Dict) -> Optional[Dict]:
    """Retrieves the entire application state (machines + jobs) from SQL."""
    try:
        if not config or not config.get("server"): return None
        ensure_app_state_table_exists(config)
        ensure_export_table_exists(config)
        
        conn = get_connection(config)
        if not conn: return None
        cursor = conn.cursor()
        
        # 1. Load State (Settings & Machine List)
        cursor.execute("SELECT KeyName, ValueData FROM Production_Planner_State")
        state_rows = cursor.fetchall()
        import json
        
        state = {}
        for row in state_rows:
            key, val = row[0], row[1]
            try:
                state[key] = json.loads(val)
            except json.JSONDecodeError:
                # Ignore non-JSON values like 'LastGlobalChange' signals
                state[key] = val
        
        if not state: 
            conn.close()
            return None
            
        settings = state.get("appSettings", {})
        machine_list = state.get("machineList", [])
        machines_metadata = state.get("machinesMetadata", {})
        
        # 2. Load Jobs for each machine
        full_data = {"appSettings": settings, "machines": {}}
        
        export_table = get_safe_table_name(config)
        cursor.execute(f"SELECT * FROM {export_table} ORDER BY Priority ASC, LastUpdated ASC")
        columns = [column[0] for column in cursor.description]
        job_rows = cursor.fetchall()
        
        # Group jobs by machine
        import copy
        for m in machine_list:
            if m in machines_metadata:
                full_data["machines"][m] = copy.deepcopy(machines_metadata[m])
                full_data["machines"][m]["jobs"] = []
            else:
                full_data["machines"][m] = {"jobs": []}
            
        for row in job_rows:
            raw_job = dict(zip(columns, row))
            m_name = raw_job.get("MachineName")
            if m_name not in full_data["machines"]:
                full_data["machines"][m_name] = {"jobs": []}
            
            # Map SQL columns back to App Logic expected format
            # This is effectively the inverse of sync_planner_to_sql
            status = raw_job["Status"]
            job_obj = {
                "id": raw_job["RowID"],
                "pjc": raw_job["PJC"],
                "customer": raw_job["Customer"],
                "description": raw_job["Description"],
                "deliveryDate": raw_job["DeliveryDate"].isoformat() if raw_job["DeliveryDate"] else None,
                "pjcIn": raw_job["OrderDate"].isoformat() if raw_job["OrderDate"] else None,
                "qty": raw_job["Quantity"],
                "gearTeeth": raw_job["GearTeeth"],
                "meters": raw_job["Meters"],
                "mcTime": raw_job["McTime"],
                "width": raw_job["Width"],
                "orderStatus": raw_job["OrderStatus"],
                "colValue": raw_job["NumColors"],
                "colorsVarnish": raw_job["ColorsVarnish"],
                "plateId": raw_job["PlateID"],
                "plateReady": bool(raw_job.get("PlateReady", False)),
                "inkReady": bool(raw_job.get("InkReady", False)),
                "totalAmt": raw_job["TotalAmt"],
                "dieCut": raw_job.get("DieCut"),
                "status": status,
                "progress": raw_job["ProgressPercent"],
                "startedAt": raw_job["StartedAt"].isoformat() if raw_job["StartedAt"] else None,
                "completedAt": raw_job["CompletedAt"].isoformat() if raw_job["CompletedAt"] else None,
                "notes": raw_job["Notes"],
                "rowColor": raw_job.get("RowColor"),
                "prodDeliveryDate": raw_job["ProdDeliveryDate"].isoformat() if raw_job.get("ProdDeliveryDate") else None,
                "finishingMachine": raw_job.get("FinishingMachine"),
                "packingMachine": raw_job.get("PackingMachine"),
                "priority": raw_job.get("Priority", 0.0),
                "visible": str(status).lower() != "completed",
                "schedule": {} 
            }
            # Parse ScheduleSummary back into a dict if needed, 
            # but usually logic re-calculates it on load
            full_data["machines"][m_name]["jobs"].append(job_obj)
            
        conn.close()
        return full_data
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

def save_full_state_to_sql(data: Dict, config: Dict):
    """Persists the non-job settings and machine list to SQL."""
    try:
        if not config or not config.get("server"): return
        ensure_users_table_exists(config)
        ensure_app_state_table_exists(config)
        
        conn = get_connection(config)
        if not conn: return
        cursor = conn.cursor()
        import json
        
        app_settings = data.get("appSettings", {})
        
        # Crucial fix: Store the full machine configurations (including column definitions)
        # but strip out the 'jobs' list to avoid giant blobs in the state table.
        # Jobs are handled separately by sync_planner_to_sql.
        machines_metadata = {}
        for m_name, m_data in data.get("machines", {}).items():
            meta = copy.deepcopy(m_data)
            if "jobs" in meta: meta["jobs"] = []
            machines_metadata[m_name] = meta
            
        to_save = {
            "appSettings": json.dumps(app_settings),
            "machineList": json.dumps(list(machines_metadata.keys())),
            "machinesMetadata": json.dumps(machines_metadata)
        }
        
        for key, val in to_save.items():
            query = """
            MERGE INTO Production_Planner_State AS target
            USING (SELECT ? AS KeyName) AS source
            ON (target.KeyName = source.KeyName)
            WHEN MATCHED THEN
                UPDATE SET ValueData = ?, LastUpdated = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (KeyName, ValueData) VALUES (?, ?);
            """
            cursor.execute(query, (key, val, key, val))
            
        conn.commit()
        conn.close()
        # After any state change, update the global change timestamp
        update_global_change_timestamp(config)
    except Exception as e:
        pass

def update_global_change_timestamp(config: Dict):
    """Updates the global change timestamp to signal all instances to reload."""
    try:
        if not config or not config.get("server"): return
        conn = get_connection(config)
        if not conn: return
        cursor = conn.cursor()
        
        query = """
            MERGE INTO Production_Planner_State AS target
            USING (SELECT 'LastGlobalChange' AS KeyName) AS source
            ON (target.KeyName = source.KeyName)
            WHEN MATCHED THEN
                UPDATE SET LastUpdated = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (KeyName, ValueData, LastUpdated) VALUES ('LastGlobalChange', 'SIGNAL', GETDATE());
        """
        cursor.execute(query)
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def get_last_global_change(config: Dict) -> Optional[str]:
    """Returns the ISO timestamp of the last global change signal."""
    try:
        if not config or not config.get("server"): return None
        conn = get_connection(config)
        if not conn: return None
        cursor = conn.cursor()
        cursor.execute("SELECT LastUpdated FROM Production_Planner_State WHERE KeyName = 'LastGlobalChange'")
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0].isoformat()
        return None
    except Exception as e:
        # print(f"SQL Check Signal Error: {e}")
        return None

def ensure_export_table_exists(config: Dict):
    """
    Creates the Production_Planner_Export table if it doesn't exist.
    """
    try:
        if not config or not config.get("server"): return
        
        conn = get_connection(config)
        if not conn: return
        cursor = conn.cursor()
        
        table_name = get_safe_table_name(config)
        
        # Check if we need to migrate from PJC as PK TO RowID as PK
        # If RowID column doesn't exist, we drop and recreate (simplest for a mirror table)
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'RowID') "
                       f"IF EXISTS (SELECT * FROM sysobjects WHERE name='{table_name}' AND xtype='U') "
                       f"DROP TABLE {table_name}")
        
        # Check if table exists
        check_query = f"""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{table_name}' AND xtype='U')
        CREATE TABLE {table_name} (
            RowID NVARCHAR(100) PRIMARY KEY,
            PJC NVARCHAR(50),
            MachineName NVARCHAR(100),
            Customer NVARCHAR(255),
            Description NVARCHAR(MAX),
            DeliveryDate DATETIME,
            OrderDate DATETIME,
            Quantity NVARCHAR(50),
            GearTeeth NVARCHAR(50),
            Meters FLOAT,
            McTime FLOAT,
            Width NVARCHAR(50),
            OrderStatus NVARCHAR(100),
            NumColors NVARCHAR(50),
            ColorsVarnish NVARCHAR(MAX),
            PlateID NVARCHAR(100),
            TotalAmt FLOAT,
            DieCut NVARCHAR(100),
            Status NVARCHAR(50),
            ProgressPercent NVARCHAR(10),
            StartedAt DATETIME,
            CompletedAt DATETIME,
            Notes NVARCHAR(MAX),
            ScheduleSummary NVARCHAR(MAX),
            Priority FLOAT,
            LastUpdated DATETIME DEFAULT GETDATE()
        )
        """
        
        cursor.execute(check_query)
        
        # Migration: Add RowColor column if it doesn't exist
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'RowColor') "
                       f"ALTER TABLE {table_name} ADD RowColor NVARCHAR(20)")
        
        # Migration: Add ModifiedBy column if it doesn't exist
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'ModifiedBy') "
                       f"ALTER TABLE {table_name} ADD ModifiedBy NVARCHAR(100)")
        
        # Migration: Add ProdDeliveryDate column if it doesn't exist
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'ProdDeliveryDate') "
                       f"ALTER TABLE {table_name} ADD ProdDeliveryDate DATETIME")
        
                       
        # Migration: Add Priority column if it doesn't exist
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'Priority') "
                       f"ALTER TABLE {table_name} ADD Priority FLOAT")
        
        # Migration: Add PlateReady column if it doesn't exist
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'PlateReady') "
                       f"ALTER TABLE {table_name} ADD PlateReady BIT DEFAULT 0")
        
        # Migration: Add InkReady column if it doesn't exist
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'InkReady') "
                       f"ALTER TABLE {table_name} ADD InkReady BIT DEFAULT 0")
        
        # Migration: Add FinishingMachine column if it doesn't exist
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'FinishingMachine') "
                       f"ALTER TABLE {table_name} ADD FinishingMachine NVARCHAR(100)")
                       
        # Migration: Add PackingMachine column if it doesn't exist
        cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'PackingMachine') "
                       f"ALTER TABLE {table_name} ADD PackingMachine NVARCHAR(100)")
        
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def ensure_users_table_exists(config: Dict, timeout: int = 5):
    """
    Creates the Production_Planner_Users table if it doesn't exist.
    """
    try:
        if not config or not config.get("server"): return
        # print(f"SQL Service: Ensuring Users table exists on {config.get('server') or config.get('sqlServer')}...", flush=True)
        
        conn = get_connection(config, timeout=timeout)
        if not conn: return
        cursor = conn.cursor()
        
        table_name = "Production_Planner_Users"
        
        check_query = f"""
        if NOT EXISTS (SELECT * FROM sysobjects WHERE name='{table_name}' AND xtype='U')
        CREATE TABLE {table_name} (
            Username NVARCHAR(100) PRIMARY KEY,
            Password NVARCHAR(100),
            Role NVARCHAR(50),
            Permissions NVARCHAR(MAX),
            LastLogin DATETIME
        );
        -- Migration: Add Permissions column if it doesn't exist (version control)
        IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('{table_name}') AND name = 'Permissions')
        BEGIN
            ALTER TABLE {table_name} ADD Permissions NVARCHAR(MAX);
        END
        """
        cursor.execute(check_query)
        
        # Add default admin if empty
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        if cursor.fetchone()[0] == 0:
            all_tabs = "planner,dashboard,records,efficiency,financial,strategic,settings,about"
            cursor.execute(f"INSERT INTO {table_name} (Username, Password, Role, Permissions) VALUES (?, ?, ?, ?)", 
                         ("Admin", "admin", "Administrator", all_tabs))
            planner_tabs = "planner,dashboard,records,efficiency,financial,strategic,about"
            cursor.execute(f"INSERT INTO {table_name} (Username, Password, Role, Permissions) VALUES (?, ?, ?, ?)", 
                         ("Planner", "pass", "Planner", planner_tabs))
                         
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def get_sql_users(config: Dict, timeout: int = 5) -> List[Dict]:
    """Fetches all users from SQL."""
    try:
        # print(f"SQL Service: get_sql_users started...", flush=True)
        ensure_users_table_exists(config, timeout=timeout)
        # print(f"SQL Service: get_sql_users connecting...", flush=True)
        conn = get_connection(config, timeout=timeout)
        if not conn: return []
        cursor = conn.cursor()
        cursor.execute("SELECT Username, Role, Password, Permissions FROM Production_Planner_Users")
        users = []
        for row in cursor.fetchall():
            users.append({
                "name": str(row[0]), 
                "role": str(row[1]), 
                "password": str(row[2]),
                "permissions": str(row[3]) if row[3] else ""
            })
        conn.close()
        return users
    except:
        return []

def save_sql_user(user_data: Dict, config: Dict):
    """Adds or updates a user in SQL."""
    try:
        ensure_users_table_exists(config)
        conn = get_connection(config)
        if not conn: return
        cursor = conn.cursor()
        name = user_data["name"]
        role = user_data["role"]
        pwd = user_data["password"]
        perms = user_data.get("permissions", "")
        
        query = """
        MERGE INTO Production_Planner_Users AS target
        USING (SELECT ? AS Username) AS source
        ON (target.Username = source.Username)
        WHEN MATCHED THEN
            UPDATE SET Role = ?, Password = ?, Permissions = ?
        WHEN NOT MATCHED THEN
            INSERT (Username, Role, Password, Permissions)
            VALUES (?, ?, ?, ?);
        """
        cursor.execute(query, (name, role, pwd, perms, name, role, pwd, perms))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def delete_sql_user(username: str, config: Dict):
    """Deletes a user from SQL."""
    try:
        ensure_users_table_exists(config)
        conn = get_connection(config)
        if not conn: return
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Production_Planner_Users WHERE Username = ?", (username,))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def delete_job_from_sql(job_id: str, config: Dict):
    """Deletes a single job row from SQL by RowID."""
    try:
        if not config or (not config.get("server") and not config.get("sqlServer")):
            return
        if not job_id:
            return
            
        table_name = get_safe_table_name(config)
        conn = get_connection(config)
        if not conn:
            from . import api_service
            api_service.log_to_file(f"SQL Delete Error: Could not connect to SQL server for job {job_id}")
            return
            
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM {table_name} WHERE RowID = ?",
            (str(job_id),)
        )
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        from . import api_service
        if affected > 0:
            api_service.log_to_file(f"SQL DELETE SUCCESS: Removed {affected} row(s) for ID {job_id} from {table_name}")
        else:
            api_service.log_to_file(f"SQL DELETE WARNING: No rows found matching ID {job_id} in {table_name}")
        
        # Signal global change so other instances reload
        update_global_change_timestamp(config)
    except Exception as e:
        from . import api_service
        api_service.log_to_file(f"SQL Delete Error for job {job_id}: {e}")

def update_sql_user_login(username: str, config: Dict):
    """Updates the LastLogin timestamp for a user in SQL."""
    try:
        if not config or not config.get("server"): return
        conn = get_connection(config)
        if not conn: return
        cursor = conn.cursor()
        cursor.execute("UPDATE Production_Planner_Users SET LastLogin = GETDATE() WHERE Username = ?", (username,))
        conn.commit()
        conn.close()
    except Exception as e:
        pass

def sync_planner_to_sql(all_machines_data: Dict, config: Dict):
    """
    Syncs all jobs from all machines into the SQL Server table.
    Uses a MERGE (UPSERT) approach with RowID (Job ID) as PK.
    """
    try:
        if not config or not config.get("server"): return
        
        ensure_export_table_exists(config)
        
        conn = get_connection(config)
        if not conn: return
        cursor = conn.cursor()
        from . import api_service
        api_service.log_to_file("SQL SYNC [Full]: Starting bulk synchronization of all machines.")

        
        table_name = get_safe_table_name(config)
        
        for m_name, mc in all_machines_data.items():
            jobs = mc.get("jobs", [])
            for idx, job in enumerate(jobs):
                # Prepare data
                job_id = str(job.get("id", ""))
                pjc = str(job.get("pjc", "")).strip()
                if not job_id or not pjc or pjc == "NEW": continue
                
                # Format schedule as simple string
                sched = job.get("schedule", {})
                sched_str = ", ".join([f"{d}: {h}h" for d, h in sched.items()]) if sched else ""
                
                # Helper logic handled by top-level parse_sql_datetime

                # MERGE Query (UPSERT) using RowID
                merge_query = f"""
                MERGE INTO {table_name} AS target
                USING (SELECT ? AS RowID) AS source
                ON (target.RowID = source.RowID)
                WHEN MATCHED THEN
                    UPDATE SET 
                        PJC = ?, MachineName = ?, Customer = ?, Description = ?, 
                        DeliveryDate = ?, OrderDate = ?, Quantity = ?, GearTeeth = ?, 
                        Meters = ?, McTime = ?, Width = ?, OrderStatus = ?, 
                        NumColors = ?, ColorsVarnish = ?, InkReady = ?, PlateID = ?, PlateReady = ?, TotalAmt = ?, 
                        DieCut = ?, Status = ?, ProgressPercent = ?, StartedAt = ?, 
                        CompletedAt = ?, Notes = ?, ScheduleSummary = ?, 
                        RowColor = ?, ProdDeliveryDate = ?, Priority = ?, ModifiedBy = ?, 
                        FinishingMachine = ?, PackingMachine = ?, LastUpdated = GETDATE()
                WHEN NOT MATCHED THEN
                    INSERT (RowID, PJC, MachineName, Customer, Description, 
                            DeliveryDate, OrderDate, Quantity, GearTeeth, 
                            Meters, McTime, Width, OrderStatus, NumColors, 
                            ColorsVarnish, InkReady, PlateID, PlateReady, TotalAmt, DieCut, Status, 
                            ProgressPercent, StartedAt, CompletedAt, 
                            Notes, ScheduleSummary, RowColor, ProdDeliveryDate, Priority, ModifiedBy,
                            FinishingMachine, PackingMachine)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """
                
                v = {
                    "id": job_id,
                    "pjc": pjc,
                    "machine": m_name,
                    "customer": job.get("customer"),
                    "desc": job.get("description"),
                    "deliv": parse_sql_datetime(job.get("deliveryDate")),
                    "order": parse_sql_datetime(job.get("pjcIn")),
                    "qty": str(job.get("qty", "")),
                    "gear": str(job.get("gearTeeth", "")),
                    "meters": job.get("meters"),
                    "mctime": job.get("mcTime"),
                    "width": str(job.get("width", "")),
                    "o_status": job.get("orderStatus"),
                    "colors": str(job.get("colValue", "")),
                    "cv": job.get("colorsVarnish"),
                    "ink_ready": 1 if job.get("inkReady") else 0,
                    "plate": job.get("plateId"),
                    "plate_ready": 1 if job.get("plateReady") else 0,
                    "amt": job.get("totalAmt"),
                    "status": job.get("status"),
                    "prog": job.get("progress"),
                    "start": parse_sql_datetime(job.get("startedAt")),
                    "comp": parse_sql_datetime(job.get("completedAt")),
                    "notes": job.get("notes"),
                    "sched": sched_str,
                    "dieCut": job.get("dieCut"),
                    "pdd": parse_sql_datetime(job.get("prodDeliveryDate")),
                    "finishing_mc": job.get("finishingMachine"),
                    "packing_mc": job.get("packingMachine")
                }

                params = [
                    v["id"], # source selector
                    
                    # UPDATE part
                    v["pjc"], v["machine"], v["customer"], v["desc"], v["deliv"],
                    v["order"], v["qty"], v["gear"], v["meters"],
                    v["mctime"], v["width"], v["o_status"], v["colors"],
                    v["cv"], v["ink_ready"], v["plate"], v["plate_ready"], v["amt"], v["dieCut"], v["status"],
                    v["prog"], v["start"], v["comp"], 
                    v["notes"], v["sched"], job.get("rowColor"), v["pdd"], float(idx), "System",
                    v["finishing_mc"], v["packing_mc"],
                    
                    # INSERT part
                    v["id"], v["pjc"], v["machine"], v["customer"], v["desc"], 
                    v["deliv"], v["order"], v["qty"], v["gear"], v["meters"], 
                    v["mctime"], v["width"], v["o_status"], v["colors"], 
                    v["cv"], v["ink_ready"], v["plate"], v["plate_ready"], v["amt"], v["dieCut"], v["status"], v["prog"], 
                    v["start"], v["comp"], v["notes"], v["sched"], job.get("rowColor"),
                    v["pdd"], float(idx), "System", v["finishing_mc"], v["packing_mc"]
                ]
                
                try:
                    cursor.execute(merge_query, params)
                except Exception as e:
                    import traceback
                    from . import api_service
                    api_service.log_to_file(f"SQL SYNC ERROR for Job {pjc} on {m_name}: {e}")
                    # Optional: detailed trace if needed
                    # api_service.log_to_file(traceback.format_exc())
        
        conn.commit()
        
        # DELETION PERSISTENCE: Remove rows from SQL that are no longer in the app
        # Collect all active job IDs
        active_ids = []
        for m_name, mc in all_machines_data.items():
            for job in mc.get("jobs", []):
                jid = str(job.get("id", ""))
                if jid: active_ids.append(jid)
        
        conn.commit()
        # Signal a global change after syncing jobs
        update_global_change_timestamp(config)

        cursor.close()
        conn.close()
        from . import api_service
        api_service.log_to_file("SQL SYNC [Full]: Completed successfully.")
        
    except Exception as e:
        import traceback
        traceback.print_exc()

def save_single_job_to_sql(job: Dict, machine_name: str, config: Dict, user_name: str = "Unknown"):
    """
    Granularly saves a single job record to SQL. 
    Enables concurrent multi-user editing without overwriting the whole machine.
    """
    try:
        if not config:
            return
        if not config.get("server") and not config.get("sqlServer"):
            return
            
        conn = get_connection(config)
        if not conn:
            from .sql_service import _LAST_ERROR_MSG
            return
        cursor = conn.cursor()
        
        table_name = get_safe_table_name(config)
        from . import api_service
        api_service.log_to_file(f"SQL SYNC [Granular]: Saving Job {job.get('pjc')} (Source: {user_name})")
        
        job_id = str(job.get("id", ""))
        pjc = str(job.get("pjc", "")).strip()
        # Section: Executive Notes
        notes = (job.get('notes') or '').strip()
        
        if not job_id or not pjc or pjc == "NEW": return

        # Format schedule as simple string
        sched = job.get("schedule", {})
        sched_str = ", ".join([f"{d}: {h}h" for d, h in sched.items()]) if sched else ""
        
        # Helper logic handled by top-level parse_sql_datetime

        def _sn(val, is_num=False):
            "Returns None if val is empty/null, else returns sanitized string or float"
            if val is None or str(val).strip().lower() in ["", "none", "nan", "null"]: return None
            s = str(val).strip()
            if is_num:
                try:
                    # Keep only digits, decimal point, and minus sign
                    clean = "".join([c for c in s if c.isdigit() or c in ".-"])
                    return float(clean) if clean else None
                except: return None
            return s

        v = {
            "id": job_id, "pjc": pjc, "machine": machine_name,
            "customer": _sn(job.get("customer")), "desc": _sn(job.get("description")),
            "deliv": parse_sql_datetime(job.get("deliveryDate")), "order": parse_sql_datetime(job.get("pjcIn")),
            "qty": _sn(job.get("qty")), "gear": _sn(job.get("gearTeeth")),
            "meters": _sn(job.get("meters"), is_num=True), "mctime": _sn(job.get("mcTime"), is_num=True),
            "width": _sn(job.get("width")), "o_status": _sn(job.get("orderStatus")),
            "colors": _sn(job.get("colValue")), "cv": _sn(job.get("colorsVarnish")),
            "ink_ready": 1 if job.get("inkReady") else 0,
            "plate": _sn(job.get("plateId")), "plate_ready": 1 if job.get("plateReady") else 0,
            "amt": _sn(job.get("totalAmt"), is_num=True),
            "status": _sn(job.get("status")), "prog": _sn(job.get("progress")),
            "start": parse_sql_datetime(job.get("startedAt")), "comp": parse_sql_datetime(job.get("completedAt")),
            "notes": _sn(job.get("notes")), "sched": _sn(sched_str), "color": _sn(job.get("rowColor")),
            "dieCut": _sn(job.get("dieCut")), "user": _sn(user_name),
            "pdd": parse_sql_datetime(job.get("prodDeliveryDate")),
            "finishing_mc": _sn(job.get("finishingMachine")),
            "packing_mc": _sn(job.get("packingMachine"))
        }

        merge_query = f"""
        MERGE INTO {table_name} AS target
        USING (SELECT ? AS RowID) AS source
        ON (target.RowID = source.RowID)
        WHEN MATCHED THEN
            UPDATE SET 
                PJC = ?, MachineName = ?, Customer = ?, Description = ?, 
                DeliveryDate = ?, OrderDate = ?, Quantity = ?, GearTeeth = ?, 
                Meters = ?, McTime = ?, Width = ?, OrderStatus = ?, 
                NumColors = ?, ColorsVarnish = ?, InkReady = ?, PlateID = ?, PlateReady = ?, TotalAmt = ?, 
                DieCut = ?, Status = ?, ProgressPercent = ?, StartedAt = ?, 
                CompletedAt = ?, Notes = ?, ScheduleSummary = ?, 
                RowColor = ?, ProdDeliveryDate = ?, Priority = ?, ModifiedBy = ?, 
                FinishingMachine = ?, PackingMachine = ?, LastUpdated = GETDATE()
        WHEN NOT MATCHED THEN
            INSERT (RowID, PJC, MachineName, Customer, Description, 
                    DeliveryDate, OrderDate, Quantity, GearTeeth, 
                    Meters, McTime, Width, OrderStatus, NumColors, 
                    ColorsVarnish, InkReady, PlateID, PlateReady, TotalAmt, DieCut, Status, 
                    ProgressPercent, StartedAt, CompletedAt, 
                    Notes, ScheduleSummary, RowColor, ProdDeliveryDate, Priority, ModifiedBy,
                    FinishingMachine, PackingMachine)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        params = [
            v["id"], 
            v["pjc"], v["machine"], v["customer"], v["desc"], v["deliv"],
            v["order"], v["qty"], v["gear"], v["meters"], v["mctime"], 
            v["width"], v["o_status"], v["colors"], v["cv"], v["ink_ready"], v["plate"], v["plate_ready"],
            v["amt"], v["dieCut"], v["status"], v["prog"], v["start"], 
            v["comp"], v["notes"], v["sched"], v["color"], v["pdd"], job.get("priority", 0.0), v["user"],
            v["finishing_mc"], v["packing_mc"],
            v["id"], v["pjc"], v["machine"], v["customer"], v["desc"], 
            v["deliv"], v["order"], v["qty"], v["gear"], v["meters"], 
            v["mctime"], v["width"], v["o_status"], v["colors"], v["cv"], 
            v["ink_ready"], v["plate"], v["plate_ready"], v["amt"], v["dieCut"], v["status"], v["prog"], 
            v["start"], v["comp"], v["notes"], v["sched"], v["color"], v["pdd"], job.get("priority", 0.0), v["user"],
            v["finishing_mc"], v["packing_mc"]
        ]
        
        cursor.execute(merge_query, params)
        conn.commit()
        conn.close()
        # Signal a global change after saving a single job
        update_global_change_timestamp(config)
    except Exception as e:
        import traceback
        from . import api_service
        api_service.log_to_file(f"SQL Save Job Error for {job.get('pjc')}: {e}")
        # api_service.log_to_file(traceback.format_exc())

def fetch_delta_updates(last_sync: datetime, exclude_user: str, config: Dict) -> List[Dict]:
    """
    Fetches only jobs modified by others since the last sync time.
    """
    try:
        if not config or not config.get("server"): return []
        conn = get_connection(config)
        if not conn: return []
        cursor = conn.cursor()
        
        # Safety Margin: Subtract 1 minute to account for clock drift between PC and SQL Server
        sync_threshold = last_sync - timedelta(minutes=1)
        
        table_name = get_safe_table_name(config)
        query = f"SELECT * FROM {table_name} WHERE LastUpdated > ? AND (ModifiedBy != ? OR ModifiedBy IS NULL)"
        cursor.execute(query, (sync_threshold, exclude_user))
        
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            raw = dict(zip(columns, row))
            # Reverse mapping to app object format (similar to load_full_plan)
            results.append({
                "id": raw["RowID"], "pjc": raw["PJC"], "machine": raw["MachineName"],
                "customer": raw["Customer"], "description": raw["Description"],
                "deliveryDate": raw["DeliveryDate"].isoformat() if raw["DeliveryDate"] else None,
                "pjcIn": raw["OrderDate"].isoformat() if raw["OrderDate"] else None,
                "qty": raw["Quantity"], "gearTeeth": raw["GearTeeth"],
                "meters": raw["Meters"], "mcTime": raw["McTime"],
                "width": raw["Width"], "orderStatus": raw["OrderStatus"],
                "colValue": raw["NumColors"], "colorsVarnish": raw["ColorsVarnish"],
                "inkReady": bool(raw.get("InkReady", False)),
                "plateId": raw["PlateID"], "plateReady": bool(raw.get("PlateReady", False)),
                "totalAmt": raw["TotalAmt"],
                "dieCut": raw.get("DieCut"), "status": raw["Status"],
                "progress": raw["ProgressPercent"],
                "startedAt": raw["StartedAt"].isoformat() if raw["StartedAt"] else None,
                "completedAt": raw["CompletedAt"].isoformat() if raw["CompletedAt"] else None,
                "notes": raw["Notes"], "rowColor": raw.get("RowColor"),
                "prodDeliveryDate": raw["ProdDeliveryDate"].isoformat() if raw.get("ProdDeliveryDate") else None,
                "modifiedBy": raw.get("ModifiedBy"),
                "deletedAt": raw.get("DeletedAt").isoformat() if raw.get("DeletedAt") else None,
                "priority": raw.get("Priority", 0.0)
            })
            
            # Sanitize strings in delta updates too
            for str_field in ["notes", "rowColor", "customer", "description", "orderStatus"]:
                if results[-1].get(str_field) is None:
                    results[-1][str_field] = ""
        conn.close()
        return results
    except Exception as e:
        return []

def fetch_state_updates(last_sync_time: datetime, config: Dict) -> Dict:
    """Checks for updates in the Production_Planner_State table since last_sync_time."""
    try:
        if not config or not config.get("server"): return {}
        conn = get_connection(config)
        if not conn: return {}
        cursor = conn.cursor()
        
        # Safety Margin: Subtract 1 minute to account for clock drift
        sync_threshold = last_sync_time - timedelta(minutes=1)
        
        query = "SELECT KeyName, ValueData FROM Production_Planner_State WHERE LastUpdated > ?"
        cursor.execute(query, (sync_threshold,))
        rows = cursor.fetchall()
        
        if rows:
            pass
        
        import json
        updates = {}
        for row in rows:
            try:
                updates[row[0]] = json.loads(row[1])
            except:
                updates[row[0]] = row[1]
                
        conn.close()
        return updates
    except Exception as e:
        return {}

def test_connection(config: Dict) -> tuple[bool, str]:
    """
    Tests the basic connection to SQL Server and returns (success, message).
    Optimized to avoid recursive table checks during testing to provide fast feedback.
    """
    global _LAST_ERROR_MSG
    try:
        # Use a short 3-second timeout for the "Test" button
        conn = get_connection(config, timeout=3)
        if not conn: 
            return False, f"SQL Connection Failed: {_LAST_ERROR_MSG}"
        conn.close()
        return True, "Connection successful!"
    except Exception as e:
        return False, f"Fatal Error: {str(e)}"

def get_job_data(job_number: str) -> Optional[Dict]:
    results = get_bulk_job_data([job_number])
    return results[0] if results else None
