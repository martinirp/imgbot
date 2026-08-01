"""
utils/map_loader.py

Carrega e compoe os tiles PNG do TibiaMaps em um canvas numpy,
pronto para uso no template matching do position tracker.

Cada tile segue o padrao: Minimap_Color_{X}_{Y}_{Z}.png
  - X, Y = coordenada do canto superior-esquerdo em coords do jogo
  - Z     = floor (7 = surface, 8 = cave1, etc.)
  - 1 pixel = 1 tile do jogo
"""

import os
import re
import cv2
import numpy as np
from functools import lru_cache

MINIMAP_DIR = "minimap"
TILE_PX     = 256  # pixels por tile PNG (= tiles do jogo cobertos)


class MapLoader:
    def __init__(self, minimap_dir=MINIMAP_DIR):
        self.minimap_dir = minimap_dir
        self._index = {}     # { z: [(ox, oy, filepath), ...] }
        self._tile_cache = {}  # { (ox, oy, z): np.ndarray | None }
        self._scan()

    # ─────────────────────────────────────────────────────────
    #  Indexação
    # ─────────────────────────────────────────────────────────
    def _scan(self):
        pattern = re.compile(r"Minimap_Color_(\d+)_(\d+)_(\d+)\.png$")
        if not os.path.isdir(self.minimap_dir):
            print(f"[MapLoader] Pasta '{self.minimap_dir}' nao encontrada.")
            return

        for fname in os.listdir(self.minimap_dir):
            m = pattern.match(fname)
            if not m:
                continue
            ox, oy, z = int(m.group(1)), int(m.group(2)), int(m.group(3))
            self._index.setdefault(z, []).append((ox, oy, os.path.join(self.minimap_dir, fname)))

        floors = sorted(self._index.keys())
        total  = sum(len(v) for v in self._index.values())
        print(f"[MapLoader] {total} tiles indexados | Floors: {floors}")

    def available_floors(self):
        return sorted(self._index.keys())

    def floor_bounds(self, z):
        """Retorna (min_x, min_y, max_x, max_y) em coordenadas do jogo para o floor z."""
        tiles = self._index.get(z, [])
        if not tiles:
            return None
        min_x = min(ox for ox, oy, _ in tiles)
        min_y = min(oy for ox, oy, _ in tiles)
        max_x = max(ox for ox, oy, _ in tiles) + TILE_PX
        max_y = max(oy for ox, oy, _ in tiles) + TILE_PX
        return min_x, min_y, max_x, max_y

    def floor_center(self, z):
        """Coordenada central do floor z."""
        b = self.floor_bounds(z)
        if b is None:
            return None
        return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2

    # ─────────────────────────────────────────────────────────
    #  Carregamento de tile individual
    # ─────────────────────────────────────────────────────────
    def _load_tile(self, ox, oy, z):
        key = (ox, oy, z)
        if key in self._tile_cache:
            return self._tile_cache[key]
        fpath = os.path.join(self.minimap_dir, f"Minimap_Color_{ox}_{oy}_{z}.png")
        if not os.path.exists(fpath):
            self._tile_cache[key] = None
            return None
        img = cv2.imread(fpath, cv2.IMREAD_COLOR)
        if img is not None and img.shape[:2] != (TILE_PX, TILE_PX):
            img = cv2.resize(img, (TILE_PX, TILE_PX), interpolation=cv2.INTER_NEAREST)
        self._tile_cache[key] = img
        return img

    # ─────────────────────────────────────────────────────────
    #  Composição de canvas ao redor de uma posição
    # ─────────────────────────────────────────────────────────
    def get_composite(self, z, center_x, center_y, radius_world=512):
        """
        Monta um canvas numpy colorido (BGR) com todos os tiles
        dentro de 'radius_world' tiles ao redor de (center_x, center_y).

        Retorna:
            canvas   : np.ndarray BGR
            origin_x : coordenada X do pixel [0,0] do canvas em coords do jogo
            origin_y : coordenada Y do pixel [0,0] do canvas em coords do jogo

        Uso no template matching:
            world_x = origin_x + match_col
            world_y = origin_y + match_row
        """
        tiles = self._index.get(z, [])
        if not tiles:
            return None, None, None

        # Bounding box do canvas a compor
        left   = center_x - radius_world
        top    = center_y - radius_world
        right  = center_x + radius_world
        bottom = center_y + radius_world

        # Snap para grade de TILE_PX
        canvas_x0 = (left  // TILE_PX) * TILE_PX
        canvas_y0 = (top   // TILE_PX) * TILE_PX
        canvas_x1 = ((right  // TILE_PX) + 1) * TILE_PX
        canvas_y1 = ((bottom // TILE_PX) + 1) * TILE_PX

        canvas_w = canvas_x1 - canvas_x0
        canvas_h = canvas_y1 - canvas_y0

        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

        for ox, oy, _ in tiles:
            # Verifica se o tile está dentro do canvas solicitado
            if ox + TILE_PX <= canvas_x0 or ox >= canvas_x1:
                continue
            if oy + TILE_PX <= canvas_y0 or oy >= canvas_y1:
                continue

            img = self._load_tile(ox, oy, z)
            if img is None:
                continue

            # Posição do tile no canvas
            px = ox - canvas_x0
            py = oy - canvas_y0

            # Clipping (caso o tile ultrapasse a borda)
            x1s, y1s = max(px, 0), max(py, 0)
            x2s = min(px + TILE_PX, canvas_w)
            y2s = min(py + TILE_PX, canvas_h)

            x1t = x1s - px
            y1t = y1s - py
            x2t = x2s - px
            y2t = y2s - py

            if x2s > x1s and y2s > y1s:
                canvas[y1s:y2s, x1s:x2s] = img[y1t:y2t, x1t:x2t]

        return canvas, canvas_x0, canvas_y0

    def get_full_floor(self, z):
        """
        Retorna o mapa completo de um floor como canvas numpy.
        Util para primeira localização (busca global).
        """
        b = self.floor_bounds(z)
        if b is None:
            return None, None, None
        min_x, min_y, max_x, max_y = b
        cx = (min_x + max_x) // 2
        cy = (min_y + max_y) // 2
        radius = max(max_x - min_x, max_y - min_y) // 2 + TILE_PX
        return self.get_composite(z, cx, cy, radius)
