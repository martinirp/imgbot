import cv2
import numpy as np
import pyautogui
import time
import math
import os
from utils.screen import take_screenshot, crop_roi

pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = False

class MinimapWalker:
    def __init__(self, roi, waypoints=None, min_distance=6, walk_delay=0.08, use_arrows=True, sort_mode="clockwise", window_manager=None):
        """
        roi: [x, y, w, h] da janela do Minimap no Tibia
        waypoints: Lista de deslocamentos gravados (opcional)
        min_distance: distância em pixels do centro para considerar 'chegou' (6px)
        walk_delay: tempo entre passos de seta (0.08s = 80ms)
        use_arrows: True para usar setas direcionais (↑, ↓, ←, →)
        window_manager: Instância de WindowManager para modo background
        """
        self.roi = roi
        self.waypoints = waypoints or []
        self.min_distance = min_distance
        self.walk_delay = walk_delay
        self.use_arrows = use_arrows
        self.sort_mode = sort_mode
        self.window_manager = window_manager
        self.last_walk_click_time = 0
        self.last_pressed_keys = []
        self.current_state = "START"
        self.template_dir = "templates"
        self.last_state_change_time = 0

    def send_click(self, x, y):
        if self.window_manager:
            self.window_manager.send_click(x, y)
        else:
            pyautogui.click(x, y)


    def set_roi(self, roi):
        self.roi = roi

    def get_minimap_center(self):
        x, y, w, h = self.roi
        return (x + w // 2, y + h // 2)

    def get_minimap_frame(self, full_frame=None):
        if full_frame is None:
            full_frame = take_screenshot()
        return crop_roi(full_frame, self.roi)

    def find_all_templates(self, minimap_frame, filename, threshold=0.85):

        """
        Busca TODAS as ocorrências do ícone da Seta no minimap com ultra-alta precisão (threshold 0.85+).
        Retorna lista de dicionários ordenados pela distância do personagem.
        """
        path = os.path.join(self.template_dir, filename)
        if not os.path.exists(path):
            return []

        template = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if template is None:
            return []

        th, tw = template.shape[:2]
        mh, mw = minimap_frame.shape[:2]

        if th > mh or tw > mw:
            return []

        if template.ndim == 3 and template.shape[2] == 4:
            bgr_template = template[:, :, :3]
        else:
            bgr_template = template

        res = cv2.matchTemplate(minimap_frame, bgr_template, cv2.TM_CCOEFF_NORMED)
        locs = np.where(res >= threshold)
        
        matches = []
        center_roi_x = mw // 2
        center_roi_y = mh // 2

        for y, x in zip(*locs):
            val = res[y, x]
            cx = x + tw // 2
            cy = y + th // 2
            dx = cx - center_roi_x
            dy = cy - center_roi_y
            dist = math.hypot(dx, dy)

            # Evita duplicatas dentro de um raio de 6px
            is_dup = False
            for m in matches:
                if math.hypot(cx - m["roi_pos"][0], cy - m["roi_pos"][1]) < 6:
                    is_dup = True
                    break

            if not is_dup:
                screen_x = self.roi[0] + cx
                screen_y = self.roi[1] + cy
                matches.append({
                    "filename": filename,
                    "roi_pos": (cx, cy),
                    "screen_pos": (screen_x, screen_y),
                    "dx": dx,
                    "dy": dy,
                    "distance": dist,
                    "confidence": float(val)
                })

        matches.sort(key=lambda item: item["distance"])
        return matches

    def step_walk(self, full_frame=None):
        """
        Navegação Focada em Waypoint por Sentido Apontado pela Seta:
        1. Identifica a Seta Atual sob/próxima dos pés.
        2. Filtra candidatos no sentido exato para onde a Seta Atual aponta (dx > 5 p/ Direita, dy > 5 p/ Baixo, etc.).
        3. Clica diretamente na imagem da próxima seta à frente.
        """
        now = time.time()
        if now - self.last_walk_click_time < self.walk_delay:
            return False, "Aguardando cooldown de caminhada"

        minimap_frame = self.get_minimap_frame(full_frame)

        # 1. BUSCA TODAS AS SETAS SELECIONADAS E CADASTRADAS NO MINIMAP (Threshold >= 0.82)
        all_matches = []
        possible_files = [
            ("arrow_right.png", "RIGHT"),
            ("arrow_down.png", "DOWN"),
            ("arrow_left.png", "LEFT"),
            ("arrow_up.png", "UP"),
            ("arrow_mark.png", "ANY"),
            ("start_mark.png", "ANY")
        ]

        for fname, direction in possible_files:
            if os.path.exists(os.path.join(self.template_dir, fname)):
                matches = self.find_all_templates(minimap_frame, fname, threshold=0.82)
                for m in matches:
                    m["direction_type"] = direction
                    all_matches.append(m)

        if not all_matches:
            self.last_pressed_keys = []
            return False, "Buscando próxima Seta no Minimap (Confiança 82%+)..."

        # 2. IDENTIFICA A SETA MAIS PRÓXIMA DOS PÉS DO PERSONAGEM
        all_matches.sort(key=lambda item: item["distance"])
        current_arrow = all_matches[0]
        curr_dir = current_arrow.get("direction_type", "ANY")

        # 3. FILTRAGEM MATEMÁTICA PELO SENTIDO DA SETA ATUAL (WAYPOINT DIRECTION)
        forward_candidates = []

        for m in all_matches:
            if m["distance"] < 8:
                continue  # Ignora a própria seta sob os pés

            dx = m["dx"]
            dy = m["dy"]

            # Filtra candidatos no sentido para onde a seta atual aponta
            if curr_dir == "RIGHT" and dx > 5:
                forward_candidates.append(m)
            elif curr_dir == "DOWN" and dy > 5:
                forward_candidates.append(m)
            elif curr_dir == "LEFT" and dx < -5:
                forward_candidates.append(m)
            elif curr_dir == "UP" and dy < -5:
                forward_candidates.append(m)

        # Se houver setas no sentido correto apontado, escolhe a primeira no sentido!
        if forward_candidates:
            target_match = forward_candidates[0]
        else:
            # Fallback para curvas/quinas: escolhe a seta mais distante >10px para forçar o avanço
            valid_ahead = [m for m in all_matches if m["distance"] >= 10]
            target_match = valid_ahead[0] if valid_ahead else all_matches[-1]

        screen_x, screen_y = target_match["screen_pos"]
        dist = target_match["distance"]
        conf = target_match["confidence"]

        # Trava de segurança com Clamping para a borda interna do Minimap (4px)
        margin = 4
        min_x = self.roi[0] + margin
        max_x = self.roi[0] + self.roi[2] - margin
        min_y = self.roi[1] + margin
        max_y = self.roi[1] + self.roi[3] - margin

        safe_x = int(max(min_x, min(max_x, screen_x)))
        safe_y = int(max(min_y, min(max_y, screen_y)))

        # EXECUTA O CLIQUE DIRETO NA PRÓXIMA SETA APONTADA
        self.send_click(safe_x, safe_y)
        self.last_walk_click_time = now
        return True, f"Navegação Waypoint por Seta [{curr_dir}] | Clique Direto no Minimap ({safe_x}, {safe_y}) - Dist: {dist:.1f}px (Conf: {conf*100:.0f}%)"


    def draw_debug(self, frame):


        """
        Desenha a ROI do minimap, o estado atual das 4 marcas e os templates encontrados.
        """
        x, y, w, h = self.roi
        center_x, center_y = self.get_minimap_center()
        minimap_frame = self.get_minimap_frame(frame)

        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 0), 2)
        cv2.putText(frame, f"ESTADO ATUAL: [{self.current_state}]", (x, max(20, y - 8)), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

        cv2.circle(frame, (center_x, center_y), 4, (0, 0, 255), -1)

        # Busca e desenha os 4 templates na tela para validação visual
        templates = [
            ("start_mark.png", (0, 255, 0), "M1:INICIO"),
            ("step1_mark.png", (255, 255, 0), "M2:AND1"),
            ("step2_mark.png", (0, 165, 255), "M3:AND2"),
            ("end_mark.png", (0, 0, 255), "M4:FINAL")
        ]

        for fname, color, label in templates:
            match = self.find_template(minimap_frame, fname, threshold=0.65)
            if match:
                sx, sy = match["screen_pos"]
                conf = match["confidence"]
                cv2.circle(frame, (sx, sy), 6, color, 2)
                cv2.putText(frame, f"{label} ({conf*100:.0f}%)", (sx + 8, sy + 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        return frame
