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

def load_drives():
    global _drives
    if DRIVES_FILE.exists():
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
    DRIVES_FILE.write_text(json.dumps(to_save, indent=2))
    hf_token = os.environ.get("HF_TOKEN")
    space_id = os.environ.get("SPACE_ID")
    if hf_token and space_id:
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
async def stream_file(request: Request, drive_id: str, id: str, name: str = "file"):
    is_dl = request.url.path == "/download"
    try:
        token   = await get_token(drive_id)
        api_url = f"https://www.googleapis.com/drive/v3/files/{id}?alt=media"
        hdrs    = {"Authorization": f"Bearer {token}"}
        rng     = request.headers.get("range")
        if rng: hdrs["Range"] = rng

        client = httpx.AsyncClient(timeout=None)
        req = client.build_request("GET", api_url, headers=hdrs)
        r = await client.send(req, stream=True)

        async def gen():
            try:
                async for chunk in r.aiter_bytes(65536):
                    yield chunk
            finally:
                await r.aclose()
                await client.aclose()

        resp_h = {**CORS, "Accept-Ranges": "bytes"}
        ct = r.headers.get("content-type", "application/octet-stream")
        
        if "content-length" in r.headers:
            resp_h["Content-Length"] = r.headers["content-length"]
        if "content-range" in r.headers:
            resp_h["Content-Range"] = r.headers["content-range"]

        if is_dl:
            resp_h["Content-Disposition"] = f'attachment; filename="{name}"'
        else:
            resp_h["Content-Disposition"] = f'inline; filename="{name}"'

        return StreamingResponse(gen(), status_code=r.status_code,
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
