import cv2
import numpy as np
import pyautogui
import time
from utils.screen import take_screenshot, crop_roi

pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = False

class BattleManager:
    def __init__(self, roi, attack_hotkey="space", loot_hotkey="-", min_health_pixels=25, min_edge_pixels=200, window_manager=None, attack_timeout=5.0):
        """
        roi: [x, y, w, h] da região do Battle List
        attack_hotkey: tecla a ser pressionada para atacar (ex: 'space', 'f1', etc)
        loot_hotkey: tecla a ser pressionada ao matar a criatura para abrir o loot (ex: '-')
        min_health_pixels: quantidade mínima de pixels de barra de vida para considerar criatura
        min_edge_pixels: quantidade mínima de pixels de borda/texto para considerar conteúdo
        window_manager: instância de WindowManager para modo background
        attack_timeout: tempo máximo em segundos tentando atacar um alvo sem matar antes de liberar a caminhada (ex: 5.0s)
        """
        self.roi = roi
        self.attack_hotkey = attack_hotkey
        self.loot_hotkey = loot_hotkey
        self.min_health_pixels = min_health_pixels
        self.min_edge_pixels = min_edge_pixels
        self.window_manager = window_manager
        self.attack_timeout = float(attack_timeout)
        self.last_attack_time = 0
        self.last_loot_time = 0
        self.last_kill_time = 0
        self.last_periodic_loot_time = 0
        self.last_stuck_log_time = 0
        self.combat_start_time = 0
        self.last_creature_count = 0
        self.was_in_combat = False
        self.was_attacking = False
        self.loot_burst_remaining = 0
        self.is_looting = False
        self.target_stuck = False

    def send_key(self, key):
        if self.window_manager:
            self.window_manager.send_key(key)
        else:
            pyautogui.press(key)

    def set_hotkey(self, hotkey):
        self.attack_hotkey = hotkey

    def set_loot_hotkey(self, hotkey):
        self.loot_hotkey = hotkey

    def set_roi(self, roi):
        self.roi = roi

    def get_battle_frame(self, full_frame=None):
        if full_frame is None:
            full_frame = take_screenshot()
        roi = self.window_manager.adjust_roi(self.roi) if self.window_manager else self.roi
        cropped = crop_roi(full_frame, roi)
        
        # Se a ROI tiver mais de 25px de altura, ignora os primeiros 15px (cabeçalho da palavra 'Battle')
        h, w = cropped.shape[:2]
        if h > 25:
            cropped = cropped[15:, :]
        return cropped

    def is_attacking(self, battle_frame):
        """
        Verifica se há um alvo em combate (quadro/moldura vermelha de alvo no Battle List).
        No Tibia, o alvo selecionado ganha um contorno/moldura vermelho vivo.
        """
        hsv = cv2.cvtColor(battle_frame, cv2.COLOR_BGR2HSV)
        
        # Intervalos para a cor vermelha em HSV
        lower_red1 = np.array([0, 160, 160])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 160, 160])
        upper_red2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        red_pixel_count = np.count_nonzero(red_mask)
        return red_pixel_count >= 20

    def get_battle_metrics(self, battle_frame):
        """
        Retorna a contagem de pixels de barra de vida e o número de barras de vida horizontais encontradas.
        """
        hsv = cv2.cvtColor(battle_frame, cv2.COLOR_BGR2HSV)
        
        # Barras de vida no Tibia (Cores vibrantes de HP: Verde, Amarelo, Vermelho)
        lower_green = np.array([35, 120, 120])
        upper_green = np.array([85, 255, 255])
        
        lower_yellow = np.array([15, 140, 140])
        upper_yellow = np.array([32, 255, 255])

        lower_red1 = np.array([0, 150, 150])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 150, 150])
        upper_red2 = np.array([180, 255, 255])

        mask_g = cv2.inRange(hsv, lower_green, upper_green)
        mask_y = cv2.inRange(hsv, lower_yellow, upper_yellow)
        mask_r = cv2.bitwise_or(
            cv2.inRange(hsv, lower_red1, upper_red1),
            cv2.inRange(hsv, lower_red2, upper_red2)
        )

        health_mask = cv2.bitwise_or(mask_g, cv2.bitwise_or(mask_y, mask_r))
        health_pixels = np.count_nonzero(health_mask)

        contours, _ = cv2.findContours(health_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        health_bars = 0
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w >= 8 and h >= 2 and (w / max(1, h) >= 1.5):
                health_bars += 1

        return health_pixels, health_bars

    def has_creatures(self, battle_frame):
        """
        Verifica se existem criaturas na lista de Batalha buscando por barras de vida de criaturas.
        """
        health_pixels, health_bars = self.get_battle_metrics(battle_frame)
        return (health_bars >= 1) or (health_pixels >= self.min_health_pixels)

    def trigger_loot_burst(self, reason="Criatura eliminada!"):
        """
        Dispara imediatamente a hotkey de loot no frame exato da morte
        e programa uma rajada ultra-rápida (burst) de 6 toques a cada 25ms.
        """
        now = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] [Auto-Loot Ultra-Rápido] {reason} -> Disparando loot: '{self.loot_hotkey}'")
        self.send_key(self.loot_hotkey)
        self.last_loot_time = now
        self.last_kill_time = now
        self.loot_burst_remaining = 6  # 6 toques rápidos em rajada para garantir

    def execute_attack_if_needed(self, full_frame=None, cooldown=0.35):
        """
        Verifica o estado do battle em tempo real com detecção instantânea de morte e anti-stuck de parede:
        1. Triggers de Morte: Moldura vermelha sumiu, contagem reduziu ou battle limpou.
        2. Disparo imediato de loot + rajada ultra-rápida de 6 toques (burst).
        3. Prioridade de Loot: segura passos do walker por ~0.50s para não caminhar antes de coletar o corpo.
        4. Auto-Loot Periódico: a cada 0.8s enquanto houver criaturas no Battle.
        5. Anti-Stuck de Parede Inteligente: se houver criatura no Battle mas sem caixa vermelha de alvo (não acessível) por >4s, libera a caminhada. NUNCA abandona alvos que estão sendo atacados ativamente (is_attacking=True).
        Retorna tupla: (has_creatures, is_attacking, pressed, is_looting, target_stuck)
        """
        battle_frame = self.get_battle_frame(full_frame)
        health_pixels, health_bars = self.get_battle_metrics(battle_frame)
        
        current_count = health_bars if health_bars > 0 else (1 if health_pixels >= self.min_health_pixels else 0)
        attacking = self.is_attacking(battle_frame)
        creatures = (current_count > 0)
        pressed = False
        now = time.time()

        # RASTREAMENTO DE ALVO ATRÁS DA PAREDE (SOMENTE QUANDO HÁ CRIATURA MAS SEM CAIXA VERMELHA DE SELEÇÃO)
        if creatures and not attacking:
            if getattr(self, 'no_target_box_start_time', 0) == 0:
                self.no_target_box_start_time = now
        else:
            # Se o alvo está sendo atacado ativamente (caixa vermelha ON) ou não há criaturas, reseta o timer de stuck
            self.no_target_box_start_time = 0
            self.target_stuck = False

        # DETECÇÃO ULTRA-SENSÍVEL DE MORTE (3 SINAIS INDEPENDENTES):
        # - Target morreu: estava atacando com caixa vermelha e a caixa vermelha sumiu!
        # - Contador reduziu: tínhamos N criaturas e agora temos menos de N!
        # - Limpeza total: tínhamos combate ativo e o battle zerou!
        target_died = (self.was_attacking and not attacking)
        count_decreased = (self.last_creature_count > 0 and current_count < self.last_creature_count)
        combat_cleared = (self.was_in_combat and not creatures)

        if target_died or count_decreased or combat_cleared:
            self.no_target_box_start_time = 0 # Reinicia timer de stuck ao matar monstro
            self.target_stuck = False
            if now - self.last_kill_time >= 0.12:
                reason_parts = []
                if target_died: reason_parts.append("Alvo eliminado")
                if count_decreased: reason_parts.append(f"Contador {self.last_creature_count}->{current_count}")
                if combat_cleared: reason_parts.append("Battle limpo")
                reason_str = ", ".join(reason_parts)
                self.trigger_loot_burst(reason_str)

        # ALVO PRESO ATRÁS DA PAREDE: Criatura na lista por > 4.0s mas NUNCA ganha a caixa vermelha de ataque
        target_stuck = False
        if creatures and not attacking and getattr(self, 'no_target_box_start_time', 0) > 0:
            elapsed_unreachable = now - self.no_target_box_start_time
            if elapsed_unreachable >= 4.0:
                target_stuck = True
                self.target_stuck = True
                if now - getattr(self, 'last_stuck_log_time', 0) >= 3.0:
                    print(f"[{time.strftime('%H:%M:%S')}] [Anti-Stuck Parede] ⚠️ Criatura atrás da parede ({elapsed_unreachable:.1f}s sem linha de visão) -> Liberando caminhada!")
                    self.last_stuck_log_time = now

        # EXECUÇÃO DO BURST DE LOOT ULTRA-RÁPIDO (Toques adicionais espaçados a cada ~25ms)
        if self.loot_burst_remaining > 0 and (now - self.last_loot_time >= 0.025):
            self.send_key(self.loot_hotkey)
            self.last_loot_time = now
            self.loot_burst_remaining -= 1

        # Atualiza os históricos de estado para o próximo frame
        self.last_creature_count = current_count
        self.was_attacking = attacking
        self.was_in_combat = creatures

        # Janela ativa de loot: 0.50s após a morte ou enquanto houver rajadas pendentes para garantir a abertura dos corpos
        is_looting = (self.loot_burst_remaining > 0) or (now - self.last_kill_time < 0.50)
        self.is_looting = is_looting

        if creatures and not target_stuck:
            # AUTO-LOOT PERIÓDICO EM COMBATE: dispara a hotkey de loot a cada 0.8s enquanto houver criatura no Battle
            if now - self.last_periodic_loot_time >= 0.8:
                self.send_key(self.loot_hotkey)
                self.last_periodic_loot_time = now

            # DISPARO DE ATAQUE E PERSEGUIÇÃO CONSTANTE (CHASE):
            # - Se não estiver atacando: dispara a hotkey de ataque imediatamente.
            # - Se já estiver atacando: re-dispara a hotkey a cada 1.2s para forçar o Tibia a perseguir o monstro fugindo!
            if not attacking and (now - self.last_attack_time >= cooldown):
                print(f"[{time.strftime('%H:%M:%S')}] [Battle] Alvo detectado no Battle! Disparando hotkey de ataque: '{self.attack_hotkey}'")
                self.send_key(self.attack_hotkey)
                self.last_attack_time = now
                pressed = True
            elif attacking and (now - self.last_attack_time >= 1.2):
                print(f"[{time.strftime('%H:%M:%S')}] [Battle Chase] Re-disparando '{self.attack_hotkey}' para perseguir monstro em fuga!")
                self.send_key(self.attack_hotkey)
                self.last_attack_time = now
                pressed = True

        return creatures, attacking, pressed, is_looting, target_stuck

    def draw_debug(self, frame):
        """
        Desenha a ROI do Battle e exibe métricas em tempo real no modo preview para calibração de confiança.
        """
        x, y, w, h = self.roi
        battle_frame = self.get_battle_frame(frame)
        health_px, health_bars = self.get_battle_metrics(battle_frame)
        creatures = self.has_creatures(battle_frame)
        attacking = self.is_attacking(battle_frame)

        if attacking:
            color = (0, 0, 255) # Vermelho: Atacando
            status = f"ATACANDO ({self.attack_hotkey.upper()})"
        elif creatures:
            color = (0, 255, 255) # Amarelo: Criatura vista
            status = f"CRIATURA VISTA"
        elif getattr(self, 'is_looting', False):
            color = (0, 215, 255) # Dourado: Coletando Loot
            status = f"COLETANDO LOOT ({self.loot_hotkey.upper()})"
        else:
            color = (0, 255, 0) # Verde: Limpo
            status = "BATTLE LIMPO"

        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        # Mostra o status e as métricas de barras de vida na tela
        cv2.putText(frame, f"Battle: {status}", (x, max(20, y - 20)), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)
        cv2.putText(frame, f"HP_Bars: {health_bars} | HP_px: {health_px}/{self.min_health_pixels}", 
                    (x, max(35, y - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        return frame
