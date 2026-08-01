"""
map_server.py - Servidor local para o visualizador de mapa interativo do Tibia

Uso:
    python map_server.py

Acesse no navegador: http://localhost:8765

API disponivel para o bot Python:
    POST /position   { "x": 33238, "y": 31840, "z": 7 }
    GET  /stream     Server-Sent Events com posicao ao vivo
    GET  /history    Historico de posicoes como JSON
    GET  /waypoints  Waypoints ativos como JSON
"""

import os
import re
import json
import time
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote

MINIMAP_DIR = "minimap"
PORT        = 8765

# ─── Estado compartilhado (thread-safe via lock) ───────────────
_lock            = threading.Lock()
CURRENT_BOT_POS  = {}           # ultima posicao do bot
BOT_PATH_HISTORY = []           # trilha completa
ACTIVE_ROUTE     = []           # waypoints carregados
MAX_HISTORY      = 20_000       # max pontos na trilha


def update_bot_position(x, y, z):
    with _lock:
        CURRENT_BOT_POS.update({"x": int(x), "y": int(y), "z": int(z), "t": time.time()})
        entry = {"x": int(x), "y": int(y), "z": int(z)}
        BOT_PATH_HISTORY.append(entry)
        if len(BOT_PATH_HISTORY) > MAX_HISTORY:
            BOT_PATH_HISTORY.pop(0)


def get_current_pos():
    with _lock:
        return dict(CURRENT_BOT_POS) if CURRENT_BOT_POS else None


def get_history():
    with _lock:
        return list(BOT_PATH_HISTORY)


# ─── Indexacao de tiles ────────────────────────────────────────
def scan_tiles(minimap_dir):
    pattern = re.compile(r"Minimap_Color_(\d+)_(\d+)_(\d+)\.png$")
    floors  = {}
    if not os.path.isdir(minimap_dir):
        return {}
    for fname in os.listdir(minimap_dir):
        m = pattern.match(fname)
        if not m:
            continue
        ox, oy, z = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if z not in floors:
            floors[z] = {"min_x": ox, "min_y": oy, "max_x": ox+256, "max_y": oy+256, "tiles": set()}
        else:
            f = floors[z]
            f["min_x"] = min(f["min_x"], ox)
            f["min_y"] = min(f["min_y"], oy)
            f["max_x"] = max(f["max_x"], ox + 256)
            f["max_y"] = max(f["max_y"], oy + 256)
        floors[z]["tiles"].add(f"{ox}_{oy}")

    manifest = {}
    for z, data in floors.items():
        cx = (data["min_x"] + data["max_x"]) // 2
        cy = (data["min_y"] + data["max_y"]) // 2
        manifest[str(z)] = {
            "min_x": data["min_x"], "min_y": data["min_y"],
            "max_x": data["max_x"], "max_y": data["max_y"],
            "center_x": cx, "center_y": cy,
            "tile_count": len(data["tiles"]),
            "tiles": list(data["tiles"])
        }
    return manifest


print(f"[MapServer] Escaneando tiles em '{MINIMAP_DIR}'...")
MANIFEST = scan_tiles(MINIMAP_DIR)
FLOORS   = sorted(int(k) for k in MANIFEST.keys())
total    = sum(v["tile_count"] for v in MANIFEST.values())
print(f"[MapServer] {total} tiles | Floors: {FLOORS}")


# ─── Handler HTTP ──────────────────────────────────────────────
class MapHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass   # silencia logs

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = unquote(parsed.path)

        # ── HTML ──────────────────────────────────────────────
        if path in ("/", "/index.html"):
            html_path = os.path.join(os.path.dirname(__file__), "map_viewer.html")
            if not os.path.exists(html_path):
                self.send_error(404, "map_viewer.html nao encontrado")
                return
            with open(html_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        # ── Manifest ──────────────────────────────────────────
        elif path == "/manifest.json":
            data = json.dumps({"floors": FLOORS, "data": MANIFEST}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        # ── Historico da trilha ───────────────────────────────
        elif path == "/history":
            data = json.dumps(get_history()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        # ── Posicao atual ─────────────────────────────────────
        elif path == "/position":
            pos  = get_current_pos()
            data = json.dumps(pos or {}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        # ── SSE: stream ao vivo ───────────────────────────────
        elif path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type",  "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection",    "keep-alive")
            self._cors()
            self.end_headers()
            last = None
            try:
                while True:
                    pos = get_current_pos()
                    if pos != last:
                        payload = json.dumps(pos) if pos else "null"
                        msg = f"data: {payload}\n\n"
                        self.wfile.write(msg.encode())
                        self.wfile.flush()
                        last = dict(pos) if pos else None
                    time.sleep(0.25)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        # ── Tile PNG ──────────────────────────────────────────
        elif path.startswith("/minimap/"):
            fname = os.path.basename(path)
            fpath = os.path.join(MINIMAP_DIR, fname)
            if not os.path.exists(fpath):
                self.send_error(404)
                return
            with open(fpath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "public, max-age=86400")
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = unquote(parsed.path)

        # ── Recebe posicao do bot ─────────────────────────────
        if path == "/position":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length)
                data   = json.loads(body)
                update_bot_position(data["x"], data["y"], data["z"])
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())

        else:
            self.send_error(404)


# ─── Funcao publica para o bot usar diretamente ────────────────
def push_position(x, y, z):
    """
    Chamada pelo bot Python para registrar a posicao atual.
    Nao precisa de HTTP - acessa o estado em memoria diretamente.
    """
    update_bot_position(x, y, z)


# ─── Inicializacao ─────────────────────────────────────────────
def run():
    server = HTTPServer(("127.0.0.1", PORT), MapHandler)
    url    = f"http://localhost:{PORT}"
    print(f"\n{'='*50}")
    print(f"  Tibia Map Viewer: {url}")
    print(f"  API do bot:  POST {url}/position")
    print(f"  Ctrl+C para parar.")
    print(f"{'='*50}\n")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[MapServer] Servidor encerrado.")


if __name__ == "__main__":
    run()
