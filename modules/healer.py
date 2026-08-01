import time
import pyautogui
import cv2
import numpy as np

pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = False

class AutoHealer:
    def __init__(self, config=None, window_manager=None):
        if config is None:
            config = {}
        self.config = config
        self.window_manager = window_manager

        # 1. Configurações de Auto-Food
        self.food_enabled = config.get("food_enabled", True)
        self.food_hotkey = config.get("food_hotkey", "f10")
        self.food_interval = float(config.get("food_interval", 60.0))
        self.last_food_time = 0

        # 2. Configurações de Magia de Cura HP (Spell)
        self.spell_hp_enabled = config.get("spell_hp_enabled", True)
        self.spell_hp_hotkey = config.get("spell_hp_hotkey", "f1")
        self.spell_hp_percent = float(config.get("spell_hp_percent", 80))
        self.spell_hp_cooldown = float(config.get("spell_hp_cooldown", 1.0))
        self.last_spell_hp_time = 0

        # 3. Configurações de Poção de Vida (Health Potion - Emergência)
        self.pot_hp_enabled = config.get("pot_hp_enabled", True)
        self.pot_hp_hotkey = config.get("pot_hp_hotkey", "f2")
        self.pot_hp_percent = float(config.get("pot_hp_percent", 50))
        self.pot_hp_cooldown = float(config.get("pot_hp_cooldown", 1.0))
        self.last_pot_hp_time = 0

        # 4. Configurações de Poção de Mana (Mana Potion)
        self.pot_mana_enabled = config.get("pot_mana_enabled", True)
        self.pot_mana_hotkey = config.get("pot_mana_hotkey", "f3")
        self.pot_mana_percent = float(config.get("pot_mana_percent", 60))
        self.pot_mana_cooldown = float(config.get("pot_mana_cooldown", 1.0))
        self.last_pot_mana_time = 0

        # ROIs da Barra de HP e Barra de Mana
        self.hp_roi = config.get("hp_roi", None)
        self.mana_roi = config.get("mana_roi", None)

    def send_key(self, key):
        if self.window_manager:
            self.window_manager.send_key(key)
        else:
            pyautogui.press(key)

    def check_and_eat_food(self):
        """Verifica o intervalo decorrido e dispara a hotkey de Food."""
        if not self.food_enabled:
            return False, ""

        now = time.time()
        if self.last_food_time == 0 or (now - self.last_food_time >= self.food_interval):
            self.send_key(self.food_hotkey)
            self.last_food_time = now
            return True, f"Auto-Food | Hotkey '{self.food_hotkey.upper()}' disparada!"
        return False, ""

    def get_hp_percentage(self, full_frame):
        """Calcula a porcentagem exata da barra de vida (HP) por visão computacional."""
        if not self.hp_roi:
            return 100.0
        x, y, w, h = self.hp_roi
        crop = full_frame[y:y+h, x:x+w]
        if crop.size == 0:
            return 100.0

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, (35, 60, 60), (85, 255, 255))
        yellow_mask = cv2.inRange(hsv, (15, 60, 60), (34, 255, 255))
        red_mask1 = cv2.inRange(hsv, (0, 60, 60), (14, 255, 255))
        red_mask2 = cv2.inRange(hsv, (165, 60, 60), (180, 255, 255))

        hp_mask = green_mask | yellow_mask | red_mask1 | red_mask2
        col_counts = cv2.reduce(hp_mask, 0, cv2.REDUCE_MAX)
        active_cols = cv2.countNonZero(col_counts)
        percent = (active_cols / max(1, w)) * 100.0
        return min(100.0, max(0.0, percent))

    def get_mana_percentage(self, full_frame):
        """Calcula a porcentagem exata da barra de Mana por visão computacional."""
        if not self.mana_roi:
            return 100.0
        x, y, w, h = self.mana_roi
        crop = full_frame[y:y+h, x:x+w]
        if crop.size == 0:
            return 100.0

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        blue_mask = cv2.inRange(hsv, (90, 60, 60), (135, 255, 255))
        col_counts = cv2.reduce(blue_mask, 0, cv2.REDUCE_MAX)
        active_cols = cv2.countNonZero(col_counts)
        percent = (active_cols / max(1, w)) * 100.0
        return min(100.0, max(0.0, percent))

    def process_survival(self, full_frame):
        """
        Processa todas as regras de sobrevivência por ordem de prioridade:
        1. Auto-Food (Intervalo de tempo)
        2. Poção de Vida HP (Emergência)
        3. Magia de Cura HP
        4. Poção de Mana
        """
        now = time.time()
        logs = []

        # 1. AUTO-FOOD
        ate_food, food_msg = self.check_and_eat_food()
        if ate_food:
            logs.append(food_msg)

        if full_frame is None or (not self.hp_roi and not self.mana_roi):
            return logs

        # Medição de porcentagem em tempo real
        hp_pct = self.get_hp_percentage(full_frame)
        mana_pct = self.get_mana_percentage(full_frame)

        # 2. EMERGENCY HEALTH POTION (HP < pot_hp_percent)
        if self.pot_hp_enabled and self.hp_roi and (now - self.last_pot_hp_time >= self.pot_hp_cooldown):
            if hp_pct < self.pot_hp_percent:
                self.send_key(self.pot_hp_hotkey)
                self.last_pot_hp_time = now
                logs.append(f"Auto-Potion HP (EMERGÊNCIA) | HP {hp_pct:.0f}% < {self.pot_hp_percent:.0f}% -> Hotkey '{self.pot_hp_hotkey.upper()}' disparada!")

        # 3. HEALING SPELL (HP < spell_hp_percent)
        if self.spell_hp_enabled and self.hp_roi and (now - self.last_spell_hp_time >= self.spell_hp_cooldown):
            if hp_pct < self.spell_hp_percent:
                self.send_key(self.spell_hp_hotkey)
                self.last_spell_hp_time = now
                logs.append(f"Auto-Magia HP | HP {hp_pct:.0f}% < {self.spell_hp_percent:.0f}% -> Hotkey '{self.spell_hp_hotkey.upper()}' disparada!")

        # 4. MANA POTION (Mana < pot_mana_percent)
        if self.pot_mana_enabled and self.mana_roi and (now - self.last_pot_mana_time >= self.pot_mana_cooldown):
            if mana_pct < self.pot_mana_percent:
                self.send_key(self.pot_mana_hotkey)
                self.last_pot_mana_time = now
                logs.append(f"Auto-Potion Mana | Mana {mana_pct:.0f}% < {self.pot_mana_percent:.0f}% -> Hotkey '{self.pot_mana_hotkey.upper()}' disparada!")

        return logs
