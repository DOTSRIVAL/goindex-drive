import os, time, json, httpx, secrets, hashlib, hmac, uuid, asyncio
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# ── CONFIG ────────────────────────────────────────────────────────────────────
DRIVES_FILE   = Path("drives.json")
DB_URL        = os.environ.get("DATABASE_URL", "")
ADMIN_USER    = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS    = os.environ.get("ADMIN_PASS", "admin123")

_drives:      list[dict] = []
_token_cache: dict       = {}
_users:       dict       = {}  # {username: {password, display_name, role}}
_app_settings = {"chunk_size_mb": 2, "speed_limit_mb": 0.0, "direct_download_mode": False, "link_expiry_hours": 0.0}
_app_secret   = str(uuid.uuid4())
_analytics:   dict       = {}

CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*"}

# ── DATABASE SETUP ────────────────────────────────────────────────────────────
postgres_conn    = None
mongo_col_drives = None
mongo_col_users  = None

if DB_URL:
    try:
        if "postgres" in DB_URL:
            import psycopg2
            postgres_conn = psycopg2.connect(DB_URL, connect_timeout=5)
            with postgres_conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS drivebase_config (
                        id integer PRIMARY KEY,
                        drives_data text
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS drivebase_users (
                        username TEXT PRIMARY KEY,
                        password TEXT,
                        display_name TEXT,
                        role TEXT
                    )
                """)
                # Safe migration - add column if missing
                cur.execute("""
                    ALTER TABLE drivebase_users
                    ADD COLUMN IF NOT EXISTS display_name TEXT
                """)
                postgres_conn.commit()
            print("[DB] Connected to PostgreSQL")

        elif "mongodb" in DB_URL:
            from pymongo import MongoClient
            _mc = MongoClient(DB_URL)
            # Get the database from the URL path, fallback to 'drivebase'
            db_name = DB_URL.split("/")[-1].split("?")[0] or "drivebase"
            _mdb = _mc[db_name]
            mongo_col_drives = _mdb["config"]
            mongo_col_users  = _mdb["users"]
            print("[DB] Connected to MongoDB:", db_name)

    except Exception as e:
        print("[DB] Connection failed:", e)

# ── USER PERSISTENCE ──────────────────────────────────────────────────────────
def load_users():
    global _users
    try:
        if postgres_conn:
            with postgres_conn.cursor() as cur:
                cur.execute("SELECT username, password, display_name, role FROM drivebase_users")
                rows = cur.fetchall()
                _users = {r[0]: {"password": r[1], "display_name": r[2] or r[0], "role": r[3]} for r in rows}
        elif mongo_col_users is not None:
            for doc in mongo_col_users.find():
                _users[doc["username"]] = {
                    "password":     doc["password"],
                    "display_name": doc.get("display_name", doc["username"]),
                    "role":         doc["role"]
                }
    except Exception as e:
        print("[Users] Load failed:", e)

def save_user(username: str, password: str, display_name: str, role: str):
    _users[username] = {"password": password, "display_name": display_name, "role": role}
    try:
        if postgres_conn:
            with postgres_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO drivebase_users (username, password, display_name, role) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (username) DO UPDATE SET "
                    "password=EXCLUDED.password, display_name=EXCLUDED.display_name, role=EXCLUDED.role",
                    (username, password, display_name, role)
                )
            postgres_conn.commit()
        elif mongo_col_users is not None:
            mongo_col_users.update_one(
                {"username": username},
                {"$set": {"password": password, "display_name": display_name, "role": role}},
                upsert=True
            )
    except Exception as e:
        print("[Users] Save failed:", e)

load_users()

# ── DRIVE PERSISTENCE ─────────────────────────────────────────────────────────
def load_db_drives():
    try:
        if postgres_conn:
            with postgres_conn.cursor() as cur:
                cur.execute("SELECT drives_data FROM drivebase_config WHERE id=1")
                row = cur.fetchone()
                if row:
                    return json.loads(row[0]) if row[0] else []
        elif mongo_col_drives is not None:
            doc = mongo_col_drives.find_one({"_id": "drives"})
            if doc:
                return doc.get("data", [])
    except Exception as e:
        print(f"[DB] Error loading drives: {e}")
    return None

def save_db_drives(drives_list):
    try:
        if postgres_conn:
            with postgres_conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO drivebase_config (id, drives_data) VALUES (1, %s) "
                    "ON CONFLICT (id) DO UPDATE SET drives_data = EXCLUDED.drives_data",
                    (json.dumps(drives_list),)
                )
            postgres_conn.commit()
            print(f"[DB] Successfully saved {len(drives_list)} drives to Postgres")
        elif mongo_col_drives is not None:
            mongo_col_drives.update_one({"_id": "drives"}, {"$set": {"data": drives_list}}, upsert=True)
            print(f"[DB] Successfully saved {len(drives_list)} drives to MongoDB")
    except Exception as e:
        print(f"[DB] Error saving drives: {e}")

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
    # Load from env vars
    cid = os.environ.get("CLIENT_ID")
    cs  = os.environ.get("CLIENT_SECRET")
    rt  = os.environ.get("REFRESH_TOKEN")
    if cid and cs and rt and not any(d.get("client_id") == cid for d in _drives):
        _drives.insert(0, {"id": "env-drive", "name": "My Drive (default)", "client_id": cid, "client_secret": cs, "refresh_token": rt})
    for i in range(1, 20):
        pre = f"DRIVE{i}_"
        dcid = os.environ.get(pre + "CLIENT_ID")
        dcs  = os.environ.get(pre + "CLIENT_SECRET")
        drt  = os.environ.get(pre + "REFRESH_TOKEN")
        if dcid and dcs and drt and not any(d.get("client_id") == dcid for d in _drives):
            _drives.append({"id": f"env-drive-{i}", "name": os.environ.get(pre + "NAME", f"Drive {i}"),
                            "client_id": dcid, "client_secret": dcs, "refresh_token": drt})

def save_drives():
    to_save = [d for d in _drives if not d["id"].startswith("env-drive")]
    if postgres_conn or mongo_col_drives is not None:
        save_db_drives(to_save)
    DRIVES_FILE.write_text(json.dumps(to_save, indent=2))

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
        _token_cache[drive_id] = {"token": d["access_token"], "expiry": time.time() + d.get("expires_in", 3600) - 60}
        return d["access_token"]

# ── ANALYTICS ─────────────────────────────────────────────────────────────────
def log_analytics_hit(ip: str):
    import datetime
    today = str(datetime.date.today())
    if today not in _analytics:
        _analytics[today] = {"bytes": 0, "hits": 0, "ips": set()}
    _analytics[today]["hits"] += 1
    if ip:
        _analytics[today]["ips"].add(ip)

def log_analytics_bytes(b: int):
    import datetime
    today = str(datetime.date.today())
    if today not in _analytics:
        _analytics[today] = {"bytes": 0, "hits": 0, "ips": set()}
    _analytics[today]["bytes"] += b

@app.get("/analytics")
async def get_analytics():
    import datetime
    today = str(datetime.date.today())
    data = _analytics.get(today, {"bytes": 0, "hits": 0, "ips": set()})
    return JSONResponse({"date": today, "total_bytes": data["bytes"], "total_hits": data["hits"], "unique_users": len(data["ips"])}, headers=CORS)

# ── AUTH ENDPOINTS ────────────────────────────────────────────────────────────
class LoginIn(BaseModel):
    username: str
    password: str
    display_name: str = ""

@app.post("/register")
async def register(body: LoginIn):
    if body.username in _users:
        return JSONResponse({"error": "User already exists"}, status_code=400, headers=CORS)
    save_user(body.username, body.password, body.display_name or body.username, "user")
    return JSONResponse({"message": "Registered successfully"}, headers=CORS)

@app.post("/login")
async def login(body: LoginIn):
    # Admin check
    if body.username == ADMIN_USER and body.password == ADMIN_PASS:
        token = secrets.token_hex(16)
        return JSONResponse({"token": token, "username": ADMIN_USER, "display_name": "Admin", "role": "admin"}, headers=CORS)
    # Normal user check
    u = _users.get(body.username)
    if u and u["password"] == body.password:
        token = secrets.token_hex(16)
        return JSONResponse({"token": token, "username": body.username, "display_name": u.get("display_name", body.username), "role": u["role"]}, headers=CORS)
    return JSONResponse({"error": "Invalid credentials"}, status_code=401, headers=CORS)

@app.get("/users")
async def list_users(admin_pass: str = ""):
    if admin_pass != ADMIN_PASS:
        return JSONResponse({"error": "Unauthorized"}, status_code=403, headers=CORS)
    return JSONResponse([{"username": u, "display_name": d["display_name"], "role": d["role"]} for u, d in _users.items()], headers=CORS)

# ── SETTINGS ENDPOINTS ────────────────────────────────────────────────────────
@app.get("/settings")
async def get_settings():
    return JSONResponse(_app_settings, headers=CORS)

class SettingsIn(BaseModel):
    chunk_size_mb: int = 2
    speed_limit_mb: float = 0.0
    direct_download_mode: bool = False
    link_expiry_hours: float = 0.0

@app.post("/settings")
async def update_settings(body: SettingsIn, admin_pass: str = ""):
    if admin_pass != ADMIN_PASS:
        return JSONResponse({"error": "Unauthorized"}, status_code=403, headers=CORS)
    _app_settings["chunk_size_mb"]        = max(1, body.chunk_size_mb)
    _app_settings["speed_limit_mb"]       = max(0.0, body.speed_limit_mb)
    _app_settings["direct_download_mode"] = body.direct_download_mode
    _app_settings["link_expiry_hours"]    = max(0.0, body.link_expiry_hours)
    return JSONResponse(_app_settings, headers=CORS)

# ── DRIVES ENDPOINTS ──────────────────────────────────────────────────────────
@app.get("/drives")
async def get_drives():
    return JSONResponse([{"id": d["id"], "name": d["name"]} for d in _drives], headers=CORS)

class DriveIn(BaseModel):
    name: str
    client_id: str
    client_secret: str
    refresh_token: str

@app.post("/drives")
async def add_drive(body: DriveIn, admin_pass: str = ""):
    if admin_pass != ADMIN_PASS:
        return JSONResponse({"error": "Unauthorized"}, status_code=403, headers=CORS)
    drive_id = str(uuid.uuid4())[:8]
    drive = {"id": drive_id, "name": body.name, "client_id": body.client_id, "client_secret": body.client_secret, "refresh_token": body.refresh_token}
    _drives.append(drive)
    save_drives()
    return JSONResponse({"message": "Drive added", "id": drive_id}, headers=CORS)

@app.put("/drives/{drive_id}")
async def update_drive(drive_id: str, body: DriveIn, admin_pass: str = ""):
    if admin_pass != ADMIN_PASS:
        return JSONResponse({"error": "Unauthorized"}, status_code=403, headers=CORS)
    for i, d in enumerate(_drives):
        if d["id"] == drive_id:
            _drives[i] = {"id": drive_id, "name": body.name, "client_id": body.client_id, "client_secret": body.client_secret, "refresh_token": body.refresh_token}
            save_drives()
            return JSONResponse({"message": "Drive updated"}, headers=CORS)
    return JSONResponse({"error": "Drive not found"}, status_code=404, headers=CORS)

@app.delete("/drives/{drive_id}")
async def delete_drive(drive_id: str, admin_pass: str = ""):
    if admin_pass != ADMIN_PASS:
        return JSONResponse({"error": "Unauthorized"}, status_code=403, headers=CORS)
    global _drives
    _drives = [d for d in _drives if d["id"] != drive_id]
    save_drives()
    return JSONResponse({"message": "Drive deleted"}, headers=CORS)

# ── FILE LISTING ──────────────────────────────────────────────────────────────
@app.get("/list")
async def list_files(drive_id: str, folder_id: str = "root"):
    try:
        token = await get_token(drive_id)
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                params={"q": f"'{folder_id}' in parents and trashed=false",
                        "fields": "files(id,name,mimeType,size,modifiedTime)",
                        "pageSize": "1000", "supportsAllDrives": "true",
                        "includeItemsFromAllDrives": "true"},
                headers={"Authorization": f"Bearer {token}"}
            )
            return JSONResponse(r.json(), headers=CORS)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500, headers=CORS)

# ── FILE STREAMING ────────────────────────────────────────────────────────────
@app.get("/stream/{drive_id}/{file_id}")
@app.get("/dl/{drive_id}/{file_id}")
async def stream_file(drive_id: str, file_id: str, request: Request, name: str = "file"):
    is_dl = "/dl/" in str(request.url)
    ip = request.client.host if request.client else ""
    log_analytics_hit(ip)

    # Check signed link expiry
    expiry_hours = _app_settings.get("link_expiry_hours", 0)
    if expiry_hours and expiry_hours > 0:
        sig  = request.query_params.get("sig", "")
        exp  = request.query_params.get("exp", "")
        if not sig or not exp:
            return JSONResponse({"error": "Link expired or invalid"}, status_code=403)
        expected = hmac.HMAC(_app_secret.encode(), f"{file_id}:{exp}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return JSONResponse({"error": "Invalid signature"}, status_code=403)
        if time.time() > float(exp):
            return JSONResponse({"error": "Link has expired"}, status_code=403)

    try:
        token = await get_token(drive_id)
        chunk_mb    = _app_settings.get("chunk_size_mb", 2)
        speed_limit = _app_settings.get("speed_limit_mb", 0)
        direct_mode = _app_settings.get("direct_download_mode", False)

        range_header = request.headers.get("range", "")

        if direct_mode:
            redirect_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&acknowledgeAbuse=true"
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=redirect_url, headers={"Authorization": f"Bearer {token}"})

        params = {"alt": "media", "acknowledgeAbuse": "true", "supportsAllDrives": "true"}
        req_headers = {"Authorization": f"Bearer {token}"}
        if range_header:
            req_headers["Range"] = range_header

        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.get(f"https://www.googleapis.com/drive/v3/files/{file_id}",
                                 params=params, headers=req_headers, follow_redirects=True)
            ct = r.headers.get("content-type", "application/octet-stream")

            async def gen():
                chunk_size = chunk_mb * 1024 * 1024
                async for chunk in r.aiter_bytes(chunk_size):
                    log_analytics_bytes(len(chunk))
                    if speed_limit and speed_limit > 0:
                        await asyncio.sleep(len(chunk) / (speed_limit * 1024 * 1024))
                    yield chunk

            resp_h = {**CORS}
            resp_h["Accept-Ranges"] = "bytes"
            if "content-length" in r.headers:
                resp_h["Content-Length"] = str(r.headers["content-length"])
            if "content-range" in r.headers:
                resp_h["Content-Range"] = str(r.headers["content-range"])
            resp_h["Content-Disposition"] = f'{"attachment" if is_dl else "inline"}; filename="{name}"'

            return StreamingResponse(gen(), status_code=r.status_code, headers=resp_h, media_type=ct)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# ── FRONTEND ──────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
@app.get("/preview.html", response_class=HTMLResponse)
async def index():
    return HTMLResponse(Path("preview.html").read_text(encoding="utf-8"))

@app.options("/{rest:path}")
async def options_handler():
    return Response(headers={**CORS, "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"})

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=False)
