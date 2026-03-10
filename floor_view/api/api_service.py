import requests
from typing import Dict,List,Optional

# Dummy log
def log_to_file(msg):
    print(f"DEBUG: {msg}")


# API config
API_BASE_URL = "http://192.168.1.11:8000/api/v1"
API_KEY = "AWOL202602261946$@#"
TIMEOUT = 12

def _headers() -> Dict:
    return{
        "Accept": "application/json",
        "api_key": API_KEY
    }

#Test API connection and error message according to HTTP codes
def _get(endpoint: str) -> Dict:

    url = f"{API_BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, headers=_headers(), timeout=TIMEOUT)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(f"Server unreachable at {url}. Check that the API server is running.")
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Request to {url} timed out after {TIMEOUT}s.")

    if response.status_code == 200:
        return response.json()
    
    if response.status_code == 401:
        raise RuntimeError("Authentication failed. Verify the API key is correct.")
    
    if response.status_code == 404:
        raise RuntimeError(f"Endpoint not found: {url}")

    raise RuntimeError(f"Unexpected response {response.status_code} from {url}: {response.text[:200]}")


# API functions

def fetch_ticket(pjc: str) -> Optional[Dict]:
    if not pjc or not str(pjc).strip():
        raise ValueError("PJC must not be empty!")
    
    try:
        data = _get(f"getTicketStatus?ticketNumber={pjc.strip()}")
    except RuntimeError as e:
        if "404" in str(e):
            return None
        raise

    raw = data.get("data") if isinstance(data, dict) else data
    if not raw:
        return None
    
    job = raw[0] if isinstance(raw, list) else raw
    return map_api_job_to_internal(job)


# Data mapping
_FIELD_MAP = {
    "number":              "pjc",
    "customername":        "customer",
    "generaldescr":        "description",
    "ship_by_date":        "deliveryDate",
    "orderdate":           "pjcIn",
    "ticquantity":         "qty",
    "estfootage":          "meters",
    "esttime":             "mcTime",
    "stockwidth2":         "width",
    "jobtype":             "orderStatus",
    "nocolors":            "colValue",
    "colordescr":          "colorsVarnish",
    "plate_id":            "plateId",
    "customer_total":      "totalAmt",
    "maintool":            "dieCut",
    "pressno":             "machine",
    "workoperation":       "status",
    "updatetimedatestamp": "apiTimestamp",
}

def translate_api_status(api_val: str) -> str:
    if not api_val or str(api_val).strip().lower() in ("", "none"):
        return "not_started"

    val = str(api_val).strip().lower()

    if any(k in val for k in ["complete", "done", "finished", "washup", "wash up", "wash-up"]):
        return "completed"
    if any(k in val for k in ["make ready", "preparing", "setup", "run", "process", "printing", "finishing", "active"]):
        return "in_progress"
    if any(k in val for k in ["hold", "paused"]):
        return "on_hold"

    return "not_started"


#wrappers
def get_job_from_api(pjc: str, config: Dict) -> Optional[Dict]:
    return fetch_ticket(str(pjc).strip())


def get_bulk_jobs_from_api(pjc_list: List[str], config: Dict) -> List[Dict]:
    results = []
    for pjc in pjc_list:
        try:
            job = fetch_ticket(str(pjc).strip())
            if job:
                results.append(job)
        except RuntimeError:
            continue
    return results


def get_live_job_statuses(pjc_list: List[str], config: Dict) -> Dict[str, Dict]:
    statuses: Dict[str, Dict] = {}
    for pjc in pjc_list:
        try:
            job = fetch_ticket(str(pjc).strip())
            if job:
                statuses[pjc] = {
                    "status":    job.get("status", "not_started"),
                    "timestamp": job.get("apiTimestamp"),
                }
        except RuntimeError:
            continue
    return statuses


def map_api_job_to_internal(api_job: Dict) -> Dict:
    api_lower = {str(k).lower(): v for k, v in api_job.items()}

    pjc_val = str(api_lower.get("number", "UNKNOWN")).strip()

    mapped: Dict = {}
    for api_key, internal_key in _FIELD_MAP.items():
        val = api_lower.get(api_key)

        if internal_key == "pjc":
            val = pjc_val
            
        elif internal_key == "qty":
            val = str(val) if val is not None else ""

        elif internal_key == "status":
            val = translate_api_status(str(val))

        mapped[internal_key] = val

    return mapped   