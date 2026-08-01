"""
utils/coord_walker.py

Walker baseado em coordenadas absolutas do jogo (X, Y, Z).
Usa PositionTracker (template matching nos tiles do TibiaMaps) para
se localizar e clica no minimap em direcao ao proximo waypoint.

Rotas criadas pelo map_viewer.html (formato JSON):
  [{"x": 33238, "y": 31840, "z": 7}, {"x": 33250, "y": 31855, "z": 7}, ...]
"""

import math
import time
import json
import os
import threading
import pyautogui
from utils.position_tracker import PositionTracker

pyautogui.PAUSE    = 0.0
pyautogui.FAILSAFE = False


class CoordWalker:
    def __init__(self, minimap_roi, waypoints, floor=7,
                 walk_delay=2.5, min_distance=10,
                 window_manager=None,
                 map_server_url="http://localhost:8765"):
        """
        minimap_roi     : [x, y, w, h] da janela do minimap no jogo
        waypoints       : lista de dict {"x": int, "y": int, "z": int}
        floor           : floor inicial para o rastreio (Z)
        walk_delay      : segundos entre cliques no minimap
        min_distance    : distancia em tiles para considerar waypoint alcancado
        window_manager  : WindowManager para modo background
        map_server_url  : URL do map_server para enviar posicao ao vivo
        """
        self.roi             = minimap_roi
        self.waypoints       = waypoints or []
        self.current_floor   = floor
        self.walk_delay      = walk_delay
        self.min_distance    = min_distance
        self.window_manager  = window_manager
        self.map_server_url  = map_server_url

        self.tracker         = PositionTracker(minimap_roi)
        self.current_wp_idx  = 0
        self.current_pos     = None      # (x, y, z) ultima posicao conhecida
        self.last_walk_time  = 0.0
        self.last_track_time = 0.0
        self.track_interval  = 1.5       # segundos entre atualizacoes de posicao
        self._server_online  = True      # tenta push; desiste se falhar muito

        # pixels_per_tile: quantos pixels de tela = 1 tile do jogo no minimap
        # minimap_scale = 0.5 -> cliente zoomed in -> 1 tile = 2px na tela
        from utils.calibrator import load_config
        cfg = load_config()
        scale = float(cfg.get("minimap_scale", 1.0))
        self.pixels_per_tile = 1.0 / scale if scale > 0 else 1.0

    # ─────────────────────────────────────────────────────────
    #  Movimento por seta direcional
    # ─────────────────────────────────────────────────────────
    def _send_arrow(self, dx, dy):
        """
        Envia a seta direcional correta baseado em (dx, dy).
        Usa numpad para diagonais se disponivel.
        Retorna (delta_x, delta_y) real aplicado.
        """
        # Decide a direcao dominante (ou diagonal)
        use_diagonal = abs(dx) > 0 and abs(dy) > 0

        if use_diagonal:
            # Diagonal via numpad
            if dx > 0 and dy < 0:   key = 'kp_page_up'    # NE
            elif dx > 0 and dy > 0: key = 'kp_page_down'  # SE
            elif dx < 0 and dy < 0: key = 'kp_home'       # NO
            else:                   key = 'kp_end'         # SO
            step_x = 1 if dx > 0 else -1
            step_y = 1 if dy > 0 else -1
        else:
            if abs(dx) >= abs(dy):
                key    = 'right' if dx > 0 else 'left'
                step_x = 1 if dx > 0 else -1
                step_y = 0
            else:
                key    = 'down' if dy > 0 else 'up'
                step_x = 0
                step_y = 1 if dy > 0 else -1

        if self.window_manager:
            self.window_manager.send_key(key)
        else:
            import pyautogui
            pyautogui.press(key)

        return step_x, step_y

    # ─────────────────────────────────────────────────────────
    #  Click no minimap (mantido para compatibilidade)
    # ─────────────────────────────────────────────────────────
    def _send_click(self, x, y):
        if self.window_manager:
            self.window_manager.send_click(x, y)
        else:
            import pyautogui
            pyautogui.click(x, y)

    def _calc_minimap_click(self, char_x, char_y, target_x, target_y):
        """
        Converte coordenadas de destino em pixel de clique no minimap.
        Usa pixels_per_tile para corrigir o zoom do cliente.
        O minimap e centralizado no personagem.
        """
        rx, ry, rw, rh = self.roi
        cx_screen = rx + rw // 2
        cy_screen = ry + rh // 2

        dx = (target_x - char_x) * self.pixels_per_tile
        dy = (target_y - char_y) * self.pixels_per_tile

        # Limita ao raio seguro do minimap (com margem de 8px da borda)
        max_r = min(rw, rh) // 2 - 8
        dist  = math.hypot(dx, dy)
        if dist > max_r:
            scale = max_r / dist
            dx = int(dx * scale)
            dy = int(dy * scale)

        click_x = int(cx_screen + dx)
        click_y = int(cy_screen + dy)

        # Clamp final dentro do ROI
        click_x = max(rx + 4, min(rx + rw - 4, click_x))
        click_y = max(ry + 4, min(ry + rh - 4, click_y))

        return click_x, click_y

    # ─────────────────────────────────────────────────────────
    #  Push posicao para o Map Viewer (background)
    # ─────────────────────────────────────────────────────────
    def _push_position_async(self, x, y, z):
        if not self._server_online:
            return

        def _push():
            try:
                import urllib.request
                data = json.dumps({"x": x, "y": y, "z": z}).encode()
                req  = urllib.request.Request(
                    f"{self.map_server_url}/position",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=0.5)
            except Exception:
                pass  # Map server pode nao estar rodando; silencia

        threading.Thread(target=_push, daemon=True).start()

    # ─────────────────────────────────────────────────────────
    #  Step principal (chamado a cada ciclo do bot)
    # ─────────────────────────────────────────────────────────
    def step_walk(self, full_frame):
        """
        Executa um passo de navegacao por teclas direcionais (setas).
        Retorna (walked: bool, msg: str)
        """
        now = time.time()

        if not self.waypoints:
            return False, "Nenhum waypoint carregado"

        # 1. Atualiza posicao via template matching periodicamente
        if now - self.last_track_time >= self.track_interval or self.current_pos is None:
            result = self.tracker.locate(full_frame, floor=self.current_floor)
            self.last_track_time = now

            if result and result.get("found"):
                x, y, z = result["x"], result["y"], result["z"]
                self.current_pos   = (x, y, z)
                self.current_floor = z
                self._push_position_async(x, y, z)
            elif self.current_pos is None:
                conf = result["confidence"] if result else 0.0
                return False, f"Localizando personagem... ({conf*100:.0f}%)"

        if self.current_pos is None:
            return False, "Aguardando localizacao inicial..."

        cx, cy, cz = self.current_pos

        # 2. Verifica waypoint atual
        if self.current_wp_idx >= len(self.waypoints):
            self.current_wp_idx = 0
            return False, "Rota completa! Reiniciando do WP1..."

        wp   = self.waypoints[self.current_wp_idx]
        wp_x = int(wp.get("x", 0))
        wp_y = int(wp.get("y", 0))
        wp_z = int(wp.get("z", self.current_floor))

        # Floor diferente: pula waypoint
        if wp_z != cz:
            self.current_wp_idx += 1
            return False, f"Pulando WP (floor {wp_z} != atual {cz})"

        dx   = wp_x - cx
        dy   = wp_y - cy
        dist = math.hypot(dx, dy)

        # 3. Chegou ao waypoint?
        if dist <= self.min_distance:
            self.current_wp_idx = (self.current_wp_idx + 1) % len(self.waypoints)
            total = len(self.waypoints)
            nxt = self.waypoints[self.current_wp_idx]
            return True, (f"[WP alcancado] Proximo: WP{self.current_wp_idx+1}/{total} "
                          f"({nxt['x']},{nxt['y']})")

        # 4. Cooldown entre passos
        if now - self.last_walk_time < self.walk_delay:
            return False, (f"WP{self.current_wp_idx+1} ({wp_x},{wp_y}) "
                           f"dist={dist:.0f}t")

        # 5. Manda a seta e atualiza posicao estimada (dead reckoning)
        step_x, step_y = self._send_arrow(dx, dy)
        self.current_pos = (cx + step_x, cy + step_y, cz)
        self.last_walk_time = now

        total = len(self.waypoints)
        key_name = ''
        if step_x == 1  and step_y == 0:  key_name = 'RIGHT'
        elif step_x == -1 and step_y == 0: key_name = 'LEFT'
        elif step_x == 0  and step_y == 1: key_name = 'DOWN'
        elif step_x == 0  and step_y == -1: key_name = 'UP'
        else: key_name = f'DIAG({step_x:+d},{step_y:+d})'

        return True, (f"[{key_name}] WP{self.current_wp_idx+1}/{total} "
                      f"| ({cx},{cy})->({wp_x},{wp_y}) dist={dist:.0f}t")

    # ─────────────────────────────────────────────────────────
    #  Utilitarios
    # ─────────────────────────────────────────────────────────
    def get_current_pos(self):
        """Retorna (x, y, z) ou None."""
        return self.current_pos

    def get_progress(self):
        """Retorna (waypoint_atual, total_waypoints)."""
        return self.current_wp_idx, len(self.waypoints)

    def reset(self):
        """Reinicia o walker para o inicio da rota."""
        self.current_wp_idx  = 0
        self.current_pos     = None
        self.last_walk_time  = 0.0
        self.last_track_time = 0.0
        self.tracker.reset()

    @staticmethod
    def load_route_file(filepath):
        """
        Carrega uma rota JSON salva pelo map_viewer.html.
        Formato: [{"x": int, "y": int, "z": int}, ...]
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Arquivo de rota nao encontrado: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("Arquivo vazio ou formato invalido (esperado lista de waypoints)")
        # Valida que tem x, y, z
        for i, wp in enumerate(data):
            if not all(k in wp for k in ("x", "y", "z")):
                raise ValueError(f"Waypoint {i+1} invalido: faltam campos x, y ou z")
        return data

    @staticmethod
    def list_route_files(routes_dir="routes"):
        """Lista todos os arquivos de rota de coordenadas na pasta routes/."""
        if not os.path.isdir(routes_dir):
            return []
        files = []
        for fname in sorted(os.listdir(routes_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(routes_dir, fname)
            try:
                with open(fpath) as f:
                    data = json.load(f)
                # Distingue rota de coords de rota de offsets
                if isinstance(data, list) and data and isinstance(data[0], dict) and "x" in data[0]:
                    files.append((fname, fpath, len(data)))
            except Exception:
                pass
        return files
