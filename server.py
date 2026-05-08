#!/usr/bin/env python3
"""
GoIndex Extended - Local Proxy Server
Handles Google Drive OAuth + file streaming via Authorization header.
Usage: py server.py
Then open: http://localhost:5500/preview.html
"""

import http.server
import urllib.request
import urllib.parse
import urllib.error
import json
import os
import sys
import time

# ── CONFIG ────────────────────────────────────────────────────────────────────
CLIENT_ID     = '808783209433-b4tr5r8giph7u8nl5umgdjuhskpsea6a.apps.googleusercontent.com'
CLIENT_SECRET = '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'
REFRESH_TOKEN = '1//0g615B_vz6ftLCgYIARAAGBASNwF-L9IretRCFrQ4pHVkzpQ_rnPOcgnyEuMHfShRbpSyjDdHdMQ8kDYXzcmJASusssSk1rFX0sk'
PORT          = 5600
SERVE_DIR     = os.path.dirname(os.path.abspath(__file__))

# ── TOKEN CACHE ───────────────────────────────────────────────────────────────
_token_cache = {'token': None, 'expiry': 0}

def get_access_token():
    if _token_cache['token'] and time.time() < _token_cache['expiry']:
        return _token_cache['token']
    data = urllib.parse.urlencode({
        'client_id':     CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': REFRESH_TOKEN,
        'grant_type':    'refresh_token'
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data,
                                  headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req) as r:
            d = json.loads(r.read())
            _token_cache['token']  = d['access_token']
            _token_cache['expiry'] = time.time() + d.get('expires_in', 3600) - 60
            print(f'[TOKEN] Refreshed OK (expires in {d.get("expires_in",3600)}s)')
            return _token_cache['token']
    except Exception as e:
        print(f'[TOKEN] Error: {e}')
        raise

# ── HANDLER ───────────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f'[{self.address_string()}] {fmt % args}')

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        path   = parsed.path

        # ── /api  (proxy for Google Drive API) ───────────────────────────────
        if path.startswith('/api'):
            api_path = path[4:]  # strip /api
            api_url  = 'https://www.googleapis.com' + api_path
            if parsed.query:
                api_url += '?' + parsed.query
            try:
                token = get_access_token()
                req   = urllib.request.Request(api_url,
                          headers={'Authorization': f'Bearer {token}'})
                with urllib.request.urlopen(req) as resp:
                    data = resp.read()
                    ct   = resp.headers.get('Content-Type', 'application/json')
                    self.send_response(200)
                    self.send_header('Content-Type', ct)
                    self.send_header('Content-Length', str(len(data)))
                    self.send_cors()
                    self.end_headers()
                    self.wfile.write(data)
            except urllib.error.HTTPError as e:
                body = e.read()
                self.send_response(e.code); self.send_cors(); self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500); self.send_cors(); self.end_headers()
                self.wfile.write(str(e).encode())
            return

        # ── /stream?id=FILE_ID&name=FILENAME ──────────────────────────────────
        if path == '/stream' or path == '/download':
            file_id   = params.get('id', '')
            file_name = params.get('name', 'file')
            is_dl     = path == '/download' or params.get('dl') == '1'

            if not file_id:
                self.send_response(400); self.end_headers()
                self.wfile.write(b'Missing id param'); return
            try:
                token   = get_access_token()
                api_url = f'https://www.googleapis.com/drive/v3/files/{file_id}?alt=media'
                # Handle range requests for streaming
                range_header = self.headers.get('Range', '')
                req_headers  = {'Authorization': f'Bearer {token}'}
                if range_header:
                    req_headers['Range'] = range_header
                req = urllib.request.Request(api_url, headers=req_headers)
                with urllib.request.urlopen(req) as resp:
                    status = resp.status
                    ct     = resp.headers.get('Content-Type', 'application/octet-stream')
                    cl     = resp.headers.get('Content-Length', '')
                    cr     = resp.headers.get('Content-Range', '')
                    self.send_response(206 if range_header else 200)
                    self.send_header('Content-Type', ct)
                    self.send_cors()
                    if cl: self.send_header('Content-Length', cl)
                    if cr: self.send_header('Content-Range', cr)
                    if is_dl:
                        safe = file_name.replace('"', '\\"')
                        self.send_header('Content-Disposition', f'attachment; filename="{safe}"')
                    else:
                        self.send_header('Accept-Ranges', 'bytes')
                    self.end_headers()
                    while True:
                        chunk = resp.read(65536)
                        if not chunk: break
                        self.wfile.write(chunk)
            except urllib.error.HTTPError as e:
                body = e.read()
                print(f'[STREAM] Drive error {e.code}: {body[:200]}')
                self.send_response(e.code); self.send_cors(); self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                print(f'[STREAM] Error: {e}')
                self.send_response(500); self.send_cors(); self.end_headers()
                self.wfile.write(str(e).encode())
            return

        # ── /token  (for JS to get current token) ─────────────────────────────
        if path == '/token':
            try:
                token = get_access_token()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_cors()
                self.end_headers()
                self.wfile.write(json.dumps({'access_token': token}).encode())
            except Exception as e:
                self.send_response(500); self.send_cors(); self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return

        # ── Static files ───────────────────────────────────────────────────────
        if path == '/' or path == '':
            path = '/preview.html'
        file_path = os.path.join(SERVE_DIR, path.lstrip('/'))
        if os.path.isfile(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            mime = {'.html':'text/html;charset=utf-8', '.css':'text/css',
                    '.js':'application/javascript', '.json':'application/json',
                    '.png':'image/png', '.jpg':'image/jpeg', '.svg':'image/svg+xml'
                    }.get(ext, 'application/octet-stream')
            with open(file_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_cors()
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404); self.end_headers()
            self.wfile.write(b'Not found')

if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'\n{"="*55}')
    print(f'  GoIndex Extended - Local Proxy Server')
    print(f'  http://localhost:{PORT}/preview.html')
    print(f'{"="*55}\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
        server.server_close()
