import cv2
import numpy as np
import math

class ActionStatusOverlay:
    """
    Pequeno Overlay Flutuante (Status Badge) que exibe em tempo real 
    a ação exata que o bot está executando no momento.
    """
    def __init__(self, width=380, height=75):
        self.width = width
        self.height = height

    def render(self, is_paused, battle_frame, battle, walker, current_action=""):
        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        canvas[:] = (20, 22, 28) # Fundo escuro esportivo premium

        # Moldura externa em degradê/borda dourada
        cv2.rectangle(canvas, (0, 0), (self.width - 1, self.height - 1), (0, 255, 255), 2)

        if is_paused:
            badge_text = "[ ⏸️ PAUSADO ]"
            badge_color = (0, 165, 255) # Laranja
            detail = "Pressione PAUSE / F12 para Retomar"
        else:
            is_attacking = battle.is_attacking(battle_frame)
            has_creatures = battle.has_creatures(battle_frame)

            if is_attacking:
                badge_text = f"[ ⚔️ ATACANDO ({battle.attack_hotkey.upper()}) ]"
                badge_color = (0, 0, 255) # Vermelho
                detail = "Combate ativo no Battle List"
            elif has_creatures:
                badge_text = f"[ 🎯 ALVO ENCONTRADO ]"
                badge_color = (0, 255, 255) # Amarelo
                detail = "Disparando hotkey de combate..."
            elif getattr(battle, 'is_looting', False):
                badge_text = f"[ 🎒 AUTO-LOOT ({battle.loot_hotkey}) ]"
                badge_color = (0, 215, 255) # Dourado
                detail = "Coletando loot do corpo eliminado"
            else:
                state = getattr(walker, 'current_state', 'START')
                state_names = {
                    "START": "Bandeira (Início)",
                    "STEP1": "Andamento 1",
                    "STEP2": "Andamento 2",
                    "STEP3": "Andamento 3",
                    "END":   "Bandeira (Final)"
                }
                m_name = state_names.get(state, state)
                badge_text = "[ 🏃 CAMINHANDO ]"
                badge_color = (0, 255, 0) # Verde
                detail = current_action or f"Indo em direção à Marca {m_name}"

        # Cabeçalho
        cv2.putText(canvas, "TIBIA BOT - AÇÃO ATUAL", (12, 18), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        # Status Badge (Ação Principal)
        cv2.putText(canvas, badge_text, (12, 42), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, badge_color, 2)

        # Detalhe da Ação
        cv2.putText(canvas, detail, (12, 62), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

        return canvas


class NFSRadarOverlay:
    """
    Interface gráfica flutuante de HUD / Radar em tempo real estilo Need For Speed.
    Exibe a máquina de estados (Bandeira -> And1 -> And2 -> And3 -> Bandeira),
    setas ativas do teclado e o status do combate.
    """
    def __init__(self, size=240):
        self.size = size
        self.center = (size // 2, size // 2)

    def render(self, minimap_crop, walker, battle):
        """
        Gera o frame do Radar NFS com indicador do Estado Atual da Marca.
        """
        h, w = self.size + 150, self.size + 50
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        canvas[:] = (15, 18, 22) # Fundo escuro esportivo

        cx = w // 2
        cy = self.size // 2 + 40

        # 1. RADAR CIRCULAR NEED FOR SPEED
        cv2.circle(canvas, (cx, cy), self.size // 2 + 5, (0, 255, 255), 2)
        cv2.circle(canvas, (cx, cy), self.size // 2, (40, 40, 40), -1)
        cv2.circle(canvas, (cx, cy), self.size // 4, (60, 60, 60), 1)

        cv2.line(canvas, (cx - self.size // 2, cy), (cx + self.size // 2, cy), (80, 80, 80), 1)
        cv2.line(canvas, (cx, cy - self.size // 2), (cx, cy + self.size // 2), (80, 80, 80), 1)

        # Insere crop do minimap se disponível
        if minimap_crop is not None and minimap_crop.size > 0:
            try:
                resized_m = cv2.resize(minimap_crop, (self.size - 20, self.size - 20))
                mask = np.zeros((self.size - 20, self.size - 20), dtype=np.uint8)
                cv2.circle(mask, ((self.size - 20) // 2, (self.size - 20) // 2), (self.size - 20) // 2, 255, -1)
                
                x_offset = cx - (self.size - 20) // 2
                y_offset = cy - (self.size - 20) // 2
                
                img_bg = cv2.bitwise_and(resized_m, resized_m, mask=mask)
                canvas[y_offset:y_offset + self.size - 20, x_offset:x_offset + self.size - 20] = img_bg
            except Exception:
                pass

        # 2. STATUS DE COMBATE
        battle_frame = battle.get_battle_frame()
        is_attacking = battle.is_attacking(battle_frame)
        has_creatures = battle.has_creatures(battle_frame)

        if is_attacking:
            status_text = "ATACANDO (COMBATE)"
            status_color = (0, 0, 255)
        elif has_creatures:
            status_text = "CRIATURA VISTA"
            status_color = (0, 255, 255)
        else:
            status_text = "CAMINHANDO (LIVRE)"
            status_color = (0, 255, 0)

        # 3. ESTADO DA MÁQUINA DE MARCAS
        state = getattr(walker, 'current_state', 'START')
        state_map = {
            "START": ("BANDEIRA (INICIO)", (0, 255, 0)),
            "STEP1": ("ANDAMENTO 1", (255, 255, 0)),
            "STEP2": ("ANDAMENTO 2", (0, 165, 255)),
            "STEP3": ("ANDAMENTO 3", (255, 0, 255)),
            "END":   ("BANDEIRA (FINAL)", (0, 0, 255))
        }
        state_label, state_color = state_map.get(state, (f"ESTADO: {state}", (255, 255, 255)))

        cv2.putText(canvas, "TIBIA NFS RADAR", (15, 22), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(canvas, f"ALVO ATIVO: {state_label}", (15, 42), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, state_color, 2)
        cv2.putText(canvas, f"STATUS: {status_text}", (15, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, status_color, 1)

        cv2.putText(canvas, f"STATUS: {status_text}", (15, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, status_color, 1)


        # Centro do personagem
        cv2.circle(canvas, (cx, cy), 5, (0, 0, 255), -1)

        # 4. PAINEL DE TECLAS ATIVAS (↑ ↓ ← →)
        pressed_keys = getattr(walker, 'last_pressed_keys', [])
        k_up = (0, 255, 0) if 'up' in pressed_keys else (80, 80, 80)
        k_down = (0, 255, 0) if 'down' in pressed_keys else (80, 80, 80)
        k_left = (0, 255, 0) if 'left' in pressed_keys else (80, 80, 80)
        k_right = (0, 255, 0) if 'right' in pressed_keys else (80, 80, 80)

        panel_y = cy + self.size // 2 + 25
        cv2.putText(canvas, "SETAS [80ms]:", (15, panel_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        
        cv2.putText(canvas, "[^]", (cx - 10, panel_y - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, k_up, 2)
        cv2.putText(canvas, "[v]", (cx - 10, panel_y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, k_down, 2)
        cv2.putText(canvas, "[<]", (cx - 40, panel_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, k_left, 2)
        cv2.putText(canvas, "[>]", (cx + 20, panel_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, k_right, 2)

        loot_key = getattr(battle, 'loot_hotkey', '-').upper()
        cv2.putText(canvas, f"Ataque: [{battle.attack_hotkey.upper()}] | Loot: [{loot_key}]", (15, h - 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        return canvas
