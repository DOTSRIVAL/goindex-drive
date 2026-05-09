import os, time, json, httpx
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# ── DRIVE STORE (persisted to drives.json) ────────────────────────────────────
DRIVES_FILE = Path("drives.json")
_drives: list[dict] = []          # [{id, name, client_id, client_secret, refresh_token}]
_token_cache: dict[str, dict] = {}  # {drive_id: {token, expiry}}

# ── DATABASE CONFIGURATION ──────────────────────────────────────────────────────
DB_URL = os.environ.get("DATABASE_URL")
postgres_conn = None
mongo_collection = None

if DB_URL:
    try:
        if DB_URL.startswith("postgres"):
            import psycopg2
            postgres_conn = psycopg2.connect(DB_URL)
            with postgres_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS drivebase_config (
                        id integer PRIMARY KEY,
                        drives_data text
                    )
                """)
                postgres_conn.commit()
            print("Connected to PostgreSQL successfully.")
            
        elif DB_URL.startswith("mongodb"):
            from pymongo import MongoClient
            client = MongoClient(DB_URL)
            db = client.get_default_database(default="drivebase")
            mongo_collection = db["config"]
            print("Connected to MongoDB successfully.")
    except Exception as e:
        print("Database connection failed:", e)

def load_db_drives():
    try:
        if postgres_conn:
            with postgres_conn.cursor() as cur:
                cur.execute("SELECT drives_data FROM drivebase_config WHERE id=1")
                row = cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
        elif mongo_collection is not None:
            doc = mongo_collection.find_one({"_id": "drives"})
            if doc and "data" in doc:
                return doc["data"]
    except Exception as e:
        print("Error loading from DB:", e)
    return None

def save_db_drives(drives_list):
    try:
        if postgres_conn:
            with postgres_conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO drivebase_config (id, drives_data) 
                    VALUES (1, %s)
                    ON CONFLICT (id) DO UPDATE SET drives_data = EXCLUDED.drives_data
                """, (json.dumps(drives_list),))
                postgres_conn.commit()
        elif mongo_collection is not None:
            mongo_collection.update_one(
                {"_id": "drives"},
                {"$set": {"data": drives_list}},
                upsert=True
            )
    except Exception as e:
        print("Error saving to DB:", e)

def load_drives():
    global _drives
    db_data = load_db_drives()
    if db_data is not None:
        _drives = db_data
    elif DRIVES_FILE.exists():
        try:
            _drives = json.loads(DRIVES_FILE.read_text())
        except:
            _drives = []
    # Also load from env for default drive
    cid = os.environ.get("CLIENT_ID")
    cs  = os.environ.get("CLIENT_SECRET")
    rt  = os.environ.get("REFRESH_TOKEN")
    if cid and cs and rt:
        exists = any(d["client_id"] == cid for d in _drives)
        if not exists:
            _drives.insert(0, {
                "id": "env-drive",
                "name": "My Drive (default)",
                "client_id": cid,
                "client_secret": cs,
                "refresh_token": rt,
            })
            
    for i in range(1, 20):
        prefix = f"DRIVE{i}_"
        did = f"env-drive-{i}"
        dname = os.environ.get(prefix + "NAME")
        dcid = os.environ.get(prefix + "CLIENT_ID")
        dcs = os.environ.get(prefix + "CLIENT_SECRET")
        drt = os.environ.get(prefix + "REFRESH_TOKEN")
        if dcid and dcs and drt:
            if not any(d["client_id"] == dcid for d in _drives):
                _drives.append({
                    "id": did,
                    "name": dname or f"ENV Drive {i}",
                    "client_id": dcid,
                    "client_secret": dcs,
                    "refresh_token": drt,
                })

def save_drives():
    # Don't save the env drives
    to_save = [d for d in _drives if not d["id"].startswith("env-drive")]
    
    # Save to Database if configured
    if postgres_conn or mongo_collection is not None:
        save_db_drives(to_save)
        
    DRIVES_FILE.write_text(json.dumps(to_save, indent=2))
    
    hf_token = os.environ.get("HF_TOKEN")
    space_id = os.environ.get("SPACE_ID")
    if hf_token and space_id and not (postgres_conn or mongo_collection is not None):
        try:
            from huggingface_hub import HfApi
            api = HfApi(token=hf_token)
            api.upload_file(
                path_or_fileobj=str(DRIVES_FILE),
                path_in_repo="drives.json",
                repo_id=space_id,
                repo_type="space"
            )
            print("Successfully synced drives.json to Hugging Face Space")
        except Exception as e:
            print("Failed to sync drives.json to HF Space:", e)

load_drives()

# ── TOKEN REFRESH ─────────────────────────────────────────────────────────────
async def get_token(drive_id: str) -> str:
    cache = _token_cache.get(drive_id, {})
    if cache.get("token") and time.time() < cache.get("expiry", 0):
        return cache["token"]
    drive = next((d for d in _drives if d["id"] == drive_id), None)
    if not drive:
        raise Exception(f"Drive '{drive_id}' not found")
    async with httpx.AsyncClient() as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id":     drive["client_id"],
            "client_secret": drive["client_secret"],
            "refresh_token": drive["refresh_token"],
            "grant_type":    "refresh_token",
        })
        d = r.json()
        if "error" in d:
            raise Exception(d.get("error_description", d["error"]))
        _token_cache[drive_id] = {
            "token":  d["access_token"],
            "expiry": time.time() + d.get("expires_in", 3600) - 60,
        }
        return d["access_token"]

CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}

# ── GLOBAL SETTINGS & ANALYTICS ───────────────────────────────────────────────
_app_settings = {"chunk_size_mb": 2, "speed_limit_mb": 0, "direct_download_mode": False, "link_expiry_hours": 0}

import hashlib
import hmac
import uuid
# Unique secret for signing links, regenerates on container restart
_app_secret = str(uuid.uuid4())

# Format: {"YYYY-MM-DD": {"bytes": 0, "hits": 0, "ips": set()}}
_analytics = {}

def log_analytics_hit(ip: str):
    import datetime
    today = str(datetime.date.today())
    if today not in _analytics:
        _analytics[today] = {"bytes": 0, "hits": 0, "ips": set()}
    _analytics[today]["hits"] += 1
    if ip:
        _analytics[today]["ips"].add(ip)

def log_analytics_bytes(bytes_sent: int):
    import datetime
    today = str(datetime.date.today())
    if today not in _analytics:
        _analytics[today] = {"bytes": 0, "hits": 0, "ips": set()}
    _analytics[today]["bytes"] += bytes_sent

@app.get("/analytics")
async def get_analytics():
    import datetime
    today = str(datetime.date.today())
    data = _analytics.get(today, {"bytes": 0, "hits": 0, "ips": set()})
    
    return JSONResponse({
        "date": today,
        "total_bytes": data["bytes"],
        "total_hits": data["hits"],
        "unique_users": len(data["ips"])
    }, headers=CORS)

@app.get("/settings")
async def get_settings():
    return JSONResponse(_app_settings, headers=CORS)

class SettingsIn(BaseModel):
    chunk_size_mb: int
    speed_limit_mb: float
    direct_download_mode: bool = False
    link_expiry_hours: float = 0

@app.post("/settings")
async def update_settings(body: SettingsIn):
    _app_settings["chunk_size_mb"] = max(1, body.chunk_size_mb)
    _app_settings["speed_limit_mb"] = max(0.0, body.speed_limit_mb)
    _app_settings["direct_download_mode"] = body.direct_download_mode
    _app_settings["link_expiry_hours"] = max(0.0, body.link_expiry_hours)
    return JSONResponse(_app_settings, headers=CORS)

@app.get("/sign")
async def sign_link(drive_id: str, id: str):
    # This endpoint signs a link dynamically for the UI if expiry is enabled
    hours = _app_settings.get("link_expiry_hours", 0)
    if hours <= 0:
        return JSONResponse({"exp": 0, "sig": ""}, headers=CORS)
        
    exp = int(time.time() + (hours * 3600))
    msg = f"{drive_id}:{id}:{exp}"
    sig = hmac.new(_app_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return JSONResponse({"exp": exp, "sig": sig}, headers=CORS)

# ── DRIVES API ────────────────────────────────────────────────────────────────
class DriveIn(BaseModel):
    name: str
    client_id: str
    client_secret: str
    refresh_token: str

@app.get("/drives")
async def list_drives():
    return JSONResponse(_drives, headers=CORS)

@app.post("/drives")
async def add_drive(body: DriveIn):
    import uuid
    drive_id = str(uuid.uuid4())[:8]
    drive = {"id": drive_id, "name": body.name, "client_id": body.client_id,
             "client_secret": body.client_secret, "refresh_token": body.refresh_token}
    # Validate token before saving
    try:
        _drives.append(drive)
        await get_token(drive_id)
        save_drives()
        return JSONResponse({"id": drive_id, "name": body.name}, headers=CORS)
    except Exception as e:
        _drives.remove(drive)
        return JSONResponse({"error": str(e)}, status_code=400, headers=CORS)

@app.put("/drives/{drive_id}")
async def update_drive(drive_id: str, body: DriveIn):
    if drive_id == "env-drive":
        return JSONResponse({"error": "Cannot edit ENV default drive"}, status_code=400, headers=CORS)
    
    for d in _drives:
        if d["id"] == drive_id:
            old_drive = dict(d)
            if body.name.strip(): d["name"] = body.name
            if body.client_id.strip(): d["client_id"] = body.client_id
            if body.client_secret.strip(): d["client_secret"] = body.client_secret
            if body.refresh_token.strip(): d["refresh_token"] = body.refresh_token
            
            try:
                _token_cache.pop(drive_id, None)
                await get_token(drive_id)
                save_drives()
                return JSONResponse({"id": drive_id, "name": d["name"]}, headers=CORS)
            except Exception as e:
                d.update(old_drive)
                _token_cache.pop(drive_id, None)
                return JSONResponse({"error": str(e)}, status_code=400, headers=CORS)
    return JSONResponse({"error": "Drive not found"}, status_code=404, headers=CORS)

@app.delete("/drives/{drive_id}")
async def delete_drive(drive_id: str):
    global _drives
    _drives = [d for d in _drives if d["id"] != drive_id]
    _token_cache.pop(drive_id, None)
    save_drives()
    return JSONResponse({"ok": True}, headers=CORS)

# ── TOKEN ENDPOINT ────────────────────────────────────────────────────────────
@app.get("/token/{drive_id}")
async def token_ep(drive_id: str):
    try:
        tok = await get_token(drive_id)
        return JSONResponse({"access_token": tok}, headers=CORS)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400, headers=CORS)

# ── DRIVE API PROXY ───────────────────────────────────────────────────────────
@app.get("/api/{drive_id}/{path:path}")
async def api_proxy(drive_id: str, path: str, request: Request):
    try:
        token   = await get_token(drive_id)
        api_url = f"https://www.googleapis.com/{path}"
        if request.query_params:
            api_url += "?" + str(request.query_params)
        async with httpx.AsyncClient() as client:
            r = await client.get(api_url, headers={"Authorization": f"Bearer {token}"})
        return Response(content=r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type", "application/json"),
                        headers=CORS)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500, headers=CORS)

@app.get("/ping/{drive_id}")
async def ping_drive(drive_id: str):
    start = time.time()
    try:
        token = await get_token(drive_id)
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get("https://www.googleapis.com/drive/v3/about?fields=user", headers={"Authorization": f"Bearer {token}"})
        ms = int((time.time() - start) * 1000)
        return JSONResponse({"ms": ms, "status": "ok" if r.status_code == 200 else "error"}, headers=CORS)
    except Exception as e:
        ms = int((time.time() - start) * 1000)
        return JSONResponse({"ms": ms, "status": "error", "error": str(e)}, status_code=500, headers=CORS)

# ── STREAM / DOWNLOAD ─────────────────────────────────────────────────────────
@app.get("/stream")
@app.get("/download")
async def stream_file(request: Request, drive_id: str, id: str, name: str = "file", exp: int = 0, sig: str = ""):
    is_dl = request.url.path == "/download"
    
    # Verify signature if expiry is provided
    if exp > 0:
        if time.time() > exp:
            return JSONResponse({"error": "This link has expired."}, status_code=403, headers=CORS)
        expected_sig = hmac.new(_app_secret.encode(), f"{drive_id}:{id}:{exp}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return JSONResponse({"error": "Invalid link signature."}, status_code=403, headers=CORS)
    else:
        # If no expiry was provided but global settings require it, deny access
        if _app_settings.get("link_expiry_hours", 0) > 0:
            return JSONResponse({"error": "This file requires a signed expiring link. Generate a new link from Drive Base."}, status_code=403, headers=CORS)

    try:
        token   = await get_token(drive_id)
        
        # 302 Direct Download Mode (Max Speed, bypasses proxy)
        if _app_settings.get("direct_download_mode", False):
            direct_url = f"https://www.googleapis.com/drive/v3/files/{id}?alt=media&acknowledgeAbuse=true&access_token={token}"
            return Response(status_code=302, headers={"Location": direct_url})
            
        api_url = f"https://www.googleapis.com/drive/v3/files/{id}?alt=media&acknowledgeAbuse=true"
        hdrs    = {"Authorization": f"Bearer {token}"}
        rng     = request.headers.get("range")
        if rng: hdrs["Range"] = rng
        import aiohttp
        session = aiohttp.ClientSession()
        r = await session.get(api_url, headers=hdrs)

        async def gen():
            import asyncio
            chunk_bytes = _app_settings.get("chunk_size_mb", 2) * 1024 * 1024
            speed_limit = _app_settings.get("speed_limit_mb", 0) * 1024 * 1024
            
            try:
                start_time = time.time()
                bytes_sent = 0
                
                client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
                if "," in client_ip:
                    client_ip = client_ip.split(",")[0].strip()
                log_analytics_hit(client_ip)
                
                async for chunk in r.content.iter_chunked(chunk_bytes):
                    yield chunk
                    chunk_len = len(chunk)
                    bytes_sent += chunk_len
                    log_analytics_bytes(chunk_len)  # Real-time traffic update
                    
                    if speed_limit > 0:
                        expected_time = bytes_sent / speed_limit
                        elapsed_time = time.time() - start_time
                        if elapsed_time < expected_time:
                            await asyncio.sleep(expected_time - elapsed_time)
            finally:
                r.close()
                await session.close()

        resp_h = {**CORS, "Accept-Ranges": "bytes"}
        ct = r.headers.get("content-type", "application/octet-stream")
        
        if "content-length" in r.headers:
            resp_h["Content-Length"] = str(r.headers["content-length"])
        if "content-range" in r.headers:
            resp_h["Content-Range"] = str(r.headers["content-range"])

        if is_dl:
            resp_h["Content-Disposition"] = f'attachment; filename="{name}"'
        else:
            resp_h["Content-Disposition"] = f'inline; filename="{name}"'

        return StreamingResponse(gen(), status_code=r.status,
                                 headers=resp_h, media_type=ct)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ── SERVE FRONTEND ────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
@app.get("/preview.html", response_class=HTMLResponse)
async def index():
    return HTMLResponse(Path("preview.html").read_text(encoding="utf-8"))

@app.options("/{rest:path}")
async def options_handler():
    return Response(headers={**CORS, "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS"})

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=False)
