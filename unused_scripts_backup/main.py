from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import asyncio
from typing import List, Dict, Optional
from pydantic import BaseModel
import sql_service

app = FastAPI(title="Production Planner Floor View API")

# Enable CORS for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to the shared planning data      
PLANNING_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "test_planning_100_jobs.json")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                # Remove stale connections
                pass

manager = ConnectionManager()

def load_data():
    if not os.path.exists(PLANNING_DATA_PATH):
        raise HTTPException(status_code=404, detail="Planning data file not found")
    with open(PLANNING_DATA_PATH, "r") as f:
        return json.load(f)

@app.get("/machines")
async def get_machines():
    """Returns a list of available machine names."""
    data = load_data()
    return list(data.get("machines", {}).keys())

@app.get("/machines/{machine_name}")
async def get_machine_data(machine_name: str):
    """Returns the jobs and columns for a specific machine."""
    data = load_data()
    machines = data.get("machines", {})
    if machine_name not in machines:
        raise HTTPException(status_code=404, detail=f"Machine '{machine_name}' not found")
    return {
        "machineName": machine_name,
        "jobs": machines[machine_name].get("jobs", []),
        "columns": machines[machine_name].get("columns", []),
        "appSettings": data.get("appSettings", {})
    }

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Just keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Notification Endpoint for PyQt
@app.post("/api/notify-update")
async def notify_update():
    """Broadcasts a refresh signal to all connected WebSocket clients."""
    await manager.broadcast("REFRESH")
    return {"status": "success", "message": "Broadcast sent"}

class SqlConfig(BaseModel):
    server: Optional[str] = ""
    database: Optional[str] = ""
    table: Optional[str] = ""
    user: Optional[str] = ""
    password: Optional[str] = ""

class BulkSyncRequest(BaseModel):
    pjc_list: List[str]
    config: Optional[SqlConfig] = None

@app.post("/api/sync-jobs/bulk")
async def sync_jobs_bulk(request: BulkSyncRequest):
    """
    Fetches job data for multiple PJCs from SQL Server.
    Returning mapping for each PJC.
    """
    try:
        # Pass config if provided
        config_dict = request.config.dict() if request.config else None
        data = sql_service.get_bulk_job_data(request.pjc_list, config_dict)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
