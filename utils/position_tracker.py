"""
utils/position_tracker.py

Localiza o personagem no mapa do jogo usando template matching
entre o minimap capturado da tela e os tiles do TibiaMaps.

Pipeline:
  1. Captura minimap_crop (pedaco da tela do jogo)
  2. Monta canvas composto dos tiles ao redor da ultima posicao conhecida
  3. cv2.matchTemplate(canvas, minimap_crop) -> posicao com melhor score
  4. Converte posicao do match -> coordenadas do jogo (X, Y, Z)

O minimap do Tibia usa 1 pixel = 1 tile, igual aos PNGs do TibiaMaps,
entao o matching funciona sem necessidade de redimensionamento.
"""

import cv2
import numpy as np
import time
from utils.map_loader import MapLoader

# Limiar minimo de confianca para aceitar um match
CONFIDENCE_THRESHOLD = 0.55

# Raio de busca ao redor da ultima posicao (em tiles do jogo)
SEARCH_RADIUS_NEAR = 400   # busca rapida quando temos posicao anterior
SEARCH_RADIUS_WIDE = 1500  # busca ampla na primeira localizacao

# Distancia maxima entre frames para considerar valido (anti-teleporte)
MAX_JUMP_TILES = 250


class PositionTracker:
    def __init__(self, minimap_roi, minimap_dir="minimap"):
        """
        minimap_roi: [x, y, w, h] da regiao do minimap na tela do jogo
        """
        self.roi = minimap_roi
        self.loader = MapLoader(minimap_dir)

        # Escala do minimap: 1.0 = 1px por tile (padrao).
        # Se o zoom do cliente for diferente, ajustar no config.json (minimap_scale)
        from utils.calibrator import load_config
        cfg = load_config()
        self.scale = float(cfg.get("minimap_scale", 1.0))
        if self.scale != 1.0:
            print(f"[PositionTracker] Escala do minimap: {self.scale}x")

        self.last_pos = None          # (x, y, z) ultima posicao conhecida
        self.last_confidence = 0.0
        self.last_update_time = 0
        self._locating = False
        self._debug_result = None     # para visualizacao

    # ─────────────────────────────────────────────────────────
    #  Metodo principal
    # ─────────────────────────────────────────────────────────
    def locate(self, full_frame, floor=None):
        """
        Tenta localizar o personagem no mapa.

        Args:
            full_frame : captura completa da tela (numpy BGR)
            floor      : floor atual (int). Se None, usa o da ultima posicao ou tenta todos.

        Returns:
            dict com:
              x, y, z       : coordenadas do jogo
              confidence    : 0.0 - 1.0
              found         : True/False
            ou None se falhar
        """
        # 1. Extrai o minimap do jogo
        minimap_crop = self._extract_minimap(full_frame)
        if minimap_crop is None:
            return None

        # 2. Determina floor a buscar
        floors_to_try = self._floors_to_search(floor)
        if not floors_to_try:
            return None

        # 3. Template matching
        best = None
        for z in floors_to_try:
            result = self._match_on_floor(minimap_crop, z)
            if result and (best is None or result["confidence"] > best["confidence"]):
                best = result

        if best is None or best["confidence"] < CONFIDENCE_THRESHOLD:
            return {"found": False, "confidence": best["confidence"] if best else 0.0}

        # 4. Valida salto entre frames
        if self.last_pos is not None:
            lx, ly, lz = self.last_pos
            dist = np.hypot(best["x"] - lx, best["y"] - ly)
            if lz == best["z"] and dist > MAX_JUMP_TILES:
                # Posicao suspeita: muito longe da anterior em um frame
                # Aceita apenas se confianca for muito alta
                if best["confidence"] < 0.75:
                    return {"found": False, "confidence": best["confidence"]}

        # 5. Atualiza estado
        self.last_pos        = (best["x"], best["y"], best["z"])
        self.last_confidence = best["confidence"]
        self.last_update_time = time.time()
        self._debug_result   = best

        return {**best, "found": True}

    # ─────────────────────────────────────────────────────────
    #  Extracao do minimap
    # ─────────────────────────────────────────────────────────
    def _extract_minimap(self, full_frame):
        """Recorta a area do minimap da tela, converte para BGR e aplica escala se necessario."""
        if full_frame is None:
            return None
        x, y, w, h = self.roi
        crop = full_frame[y:y+h, x:x+w]
        if crop.size == 0:
            return None
        # Converte para BGR se necessario
        if len(crop.shape) == 2:
            crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        # Aplica fator de escala para corrigir zoom do cliente
        if self.scale != 1.0:
            nw = max(1, int(crop.shape[1] * self.scale))
            nh = max(1, int(crop.shape[0] * self.scale))
            crop = cv2.resize(crop, (nw, nh), interpolation=cv2.INTER_AREA)
        return crop.copy()

    # ─────────────────────────────────────────────────────────
    #  Template matching
    # ─────────────────────────────────────────────────────────
    def _match_on_floor(self, minimap_crop, z):
        """
        Faz template matching do minimap_crop contra o canvas do floor z.
        Retorna dict com resultado ou None.
        """
        th, tw = minimap_crop.shape[:2]

        # Define raio de busca
        if self.last_pos and self.last_pos[2] == z:
            cx, cy = self.last_pos[0], self.last_pos[1]
            radius = SEARCH_RADIUS_NEAR
        else:
            center = self.loader.floor_center(z)
            if center is None:
                return None
            cx, cy = center
            radius = SEARCH_RADIUS_WIDE

        # Compoe canvas ao redor da posicao estimada
        canvas, origin_x, origin_y = self.loader.get_composite(z, cx, cy, radius)
        if canvas is None:
            return None

        ch, cw = canvas.shape[:2]

        # Canvas precisa ser maior que o template
        if ch < th or cw < tw:
            return None

        # Template matching (normalizado = robusto a brilho/contraste)
        result = cv2.matchTemplate(canvas, minimap_crop, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        # O match_loc e o canto superior-esquerdo do template no canvas
        match_col, match_row = max_loc

        # Centro do personagem = centro do template no canvas
        char_col = match_col + tw // 2
        char_row = match_row + th // 2

        # Converte para coordenadas do jogo
        world_x = origin_x + char_col
        world_y = origin_y + char_row

        return {
            "x": world_x,
            "y": world_y,
            "z": z,
            "confidence": float(max_val),
            "match_loc": max_loc,
            "canvas": canvas,
            "origin_x": origin_x,
            "origin_y": origin_y,
        }

    # ─────────────────────────────────────────────────────────
    #  Floors a tentar
    # ─────────────────────────────────────────────────────────
    def _floors_to_search(self, floor_hint):
        available = self.loader.available_floors()
        if not available:
            return []

        if floor_hint is not None and floor_hint in available:
            return [floor_hint]

        if self.last_pos is not None:
            lz = self.last_pos[2]
            # Tenta floor atual e adjacentes
            candidates = [lz, lz-1, lz+1]
            return [z for z in candidates if z in available]

        # Primeira vez: comeca pelo floor 7 (surface) se disponivel
        if 7 in available:
            return [7] + [z for z in available if z != 7]
        return available

    # ─────────────────────────────────────────────────────────
    #  Utilitarios
    # ─────────────────────────────────────────────────────────
    def get_last_pos(self):
        return self.last_pos

    def reset(self):
        """Esquece a ultima posicao (forca busca global no proximo frame)."""
        self.last_pos = None
        self.last_confidence = 0.0

    def draw_debug(self, frame):
        """
        Sobrepoe informacoes de debug no frame da tela:
        - Destaca a area do minimap
        - Mostra coordenadas e confianca
        """
        if not self._debug_result:
            return frame

        r = self._debug_result
        x, y, w, h = self.roi

        # Borda ao redor do minimap
        color = (0, 255, 80) if r["confidence"] >= CONFIDENCE_THRESHOLD else (0, 80, 255)
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)

        # Texto de coordenadas
        label = f"X:{r['x']}  Y:{r['y']}  Z:{r['z']}  ({r['confidence']*100:.0f}%)"
        cv2.putText(frame, label, (x, max(y-8, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        return frame
