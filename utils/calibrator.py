import json
import os
import cv2
import numpy as np
from utils.screen import take_screenshot

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "attack_hotkey": "space",
    "battle_roi": [100, 100, 180, 200],
    "minimap_roi": [1000, 50, 150, 150],
    "minimap_scale": 1.0,
    "min_health_pixels": 25,
    "min_edge_pixels": 200,
    "walk_delay": 0.8,
    "battle_check_delay": 0.3,
    "min_mark_distance": 6,
    "sort_mode": "clockwise"
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge com defaults se faltar alguma chave
                for k, v in DEFAULT_CONFIG.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception as e:
            print(f"[Calibrator] Erro ao carregar '{CONFIG_FILE}': {e}")
    return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print(f"[Calibrator] Configuração salva com sucesso em '{CONFIG_FILE}'.")
    except Exception as e:
        print(f"[Calibrator] Erro ao salvar configuração: {e}")

def get_calibrator_frame():
    """
    Obtém a captura da tela inteira (Desktop), mas tenta trazer a janela do jogo
    para a frente (primeiro plano) antes de capturar, garantindo que o jogo não
    fique escondido atrás do terminal.
    As coordenadas SEMPRE serão absolutas em relação à tela, pois o bot usa 
    coordenadas absolutas.
    """
    import time
    config = load_config()
    target_title = config.get("target_window_title", "Tibia")
    win_name = "Tela Cheia (Desktop)"
    
    try:
        from utils.window_manager import WindowManager
        wm = WindowManager(target_title)
        if wm.win:
            wm.raise_window()
            win_name = f"Tela Cheia c/ Janela '{wm.win_name}'"
            time.sleep(0.5) # Dá tempo do SO desenhar a janela na frente
    except Exception:
        pass
        
    return take_screenshot(), win_name

def select_region(title="Selecione a Regiao"):
    frame, win_name = get_calibrator_frame()
    h, w = frame.shape[:2]
    print(f"\n==================================================")
    print(f"[Calibrator] 📸 Captura obtida DIRETO da janela do jogo: '{win_name}' ({w}x{h}px)")
    print(f"            Selecione a área para: '{title}'")
    print("Instruções: Desenhe um retângulo na área desejada e aperte ENTER ou ESPAÇO. (ESC para cancelar).")
    print(f"==================================================\n")
    
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    roi = cv2.selectROI(title, frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(title)
    
    x, y, w, h = [int(v) for v in roi]
    if w > 0 and h > 0:
        return [x, y, w, h]
    return None

def record_waypoints():
    """
    Interface gráfica interativa para gravar Waypoints clicando no Minimap.
    Salva os deslocamentos (dx, dy) relativos ao centro do minimap no config.json.
    """
    config = load_config()
    m_roi = config.get("minimap_roi")
    
    if not m_roi or m_roi[2] == 0 or m_roi[3] == 0:
        print("[Gravador] Minimap ROI não configurado. Execute a calibração primeiro.")
        return

    print("\n==================================================")
    print("      GRAVADOR INTERATIVO DE WAYPOINTS            ")
    print("==================================================")
    print(" -> Clique com o botão ESQUERDO no minimap para ADICIONAR um Waypoint.")
    print(" -> Pressione 'c' para LIMPAR todos os waypoints.")
    print(" -> Pressione ENTER ou ESPAÇO para SALVAR e SAIR.")
    print(" -> Pressione ESC para CANCELAR.")
    print("==================================================\n")

    frame, _ = get_calibrator_frame()
    x, y, w, h = m_roi
    minimap_crop = frame[y:y+h, x:x+w].copy()

    center_x = w // 2
    center_y = h // 2

    # Waypoints armazenados como deslocamentos [dx, dy] a partir do centro
    waypoints = config.get("waypoints", [])
    
    # Prepara cópia para desenhar
    display_img = minimap_crop.copy()

    def mouse_callback(event, mx, my, flags, param):
        nonlocal waypoints, display_img
        if event == cv2.EVENT_LBUTTONDOWN:
            dx = mx - center_x
            dy = my - center_y
            waypoints.append([dx, dy])
            print(f"[Gravador] Waypoint {len(waypoints)} adicionado: Offset (dx={dx}, dy={dy})")

    cv2.namedWindow("Gravador de Waypoints (Clique no Mapa)", cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback("Gravador de Waypoints (Clique no Mapa)", mouse_callback)

    while True:
        canvas = minimap_crop.copy()
        # Desenha o centro (personagem em vermelho)
        cv2.circle(canvas, (center_x, center_y), 4, (0, 0, 255), -1)

        # Desenha os waypoints e linhas conectando a rota
        pts = []
        for idx, (dx, dy) in enumerate(waypoints):
            wx = center_x + dx
            wy = center_y + dy
            pts.append((wx, wy))
            cv2.circle(canvas, (wx, wy), 4, (0, 255, 0), -1)
            cv2.putText(canvas, f"W{idx+1}", (wx + 4, wy - 4), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        # Desenha linhas fechando o circuito
        if len(pts) > 1:
            for i in range(len(pts)):
                p1 = pts[i]
                p2 = pts[(i + 1) % len(pts)]
                cv2.line(canvas, p1, p2, (255, 255, 0), 1)

        cv2.imshow("Gravador de Waypoints (Clique no Mapa)", canvas)
        key = cv2.waitKey(30) & 0xFF

        if key == 13 or key == 32: # ENTER ou ESPAÇO
            cv2.destroyAllWindows()
            if waypoints:
                route_name = input("\n[Gravador] Digite um nome para salvar este arquivo de rota (ex: 'rotworms', 'trolls'): ").strip()
                if not route_name:
                    route_name = "default"
                
                from utils.route_manager import save_route
                save_route(route_name, waypoints)
                
                config["active_route"] = route_name if route_name.endswith(".json") else route_name + ".json"
                config["waypoints"] = waypoints
                save_config(config)
                print(f"[Gravador] {len(waypoints)} waypoints salvos na rota '{route_name}'!")
            break
        elif key == ord('c'): # 'c' limpa waypoints
            waypoints = []
            print("[Gravador] Todos os waypoints foram limpos.")
        elif key == 27: # ESC
            cv2.destroyAllWindows()
            print("[Gravador] Gravação cancelada.")
            break


def calibrate_mark_templates():
    """
    Ferramenta interativa de Calibração ao Vivo com Lupa Magnificada (Zoom 3x):
    Captura o minimap da tela em tempo real, permite clicar no ícone do minimap
    e exibe a imagem ampliada antes de salvar com ENTER.
    """
    config = load_config()
    m_roi = config.get("minimap_roi")
    
    if not m_roi or m_roi[2] == 0 or m_roi[3] == 0:
        print("[Calibrador] Minimap ROI não configurado. Execute a opção 6 (Calibrar Regiões) primeiro.")
        return

    os.makedirs("templates", exist_ok=True)
    x, y, w, h = m_roi

    marks = [
        ("arrow_right.png", "1. Seta para DIREITA (➔ Leste)"),
        ("arrow_down.png", "2. Seta para BAIXO (⬇ Sul)"),
        ("arrow_left.png", "3. Seta para ESQUERDA (⬅ Oeste)"),
        ("arrow_up.png", "4. Seta para CIMA (⬆ Norte)")
    ]

    print("\n==================================================")
    print("   CALIBRAÇÃO AO VIVO DAS 4 SETAS DIRECIONAIS    ")
    print("==================================================")





    print(" -> CLIQUE COM O MOUSE em cima do ícone no Minimap.")
    print(" -> A Lupa ao lado mostrará o ícone ampliado.")
    print(" -> Pressione ENTER ou ESPAÇO para confirmar a captura.")
    print(" -> Pressione ESC para cancelar.")
    print("==================================================\n")

    template_paths = {}
    win_title = "Calibrador de Icones (Lupa 3x)"

    target_pos = [w // 2, h // 2]
    crop_radius = 4  # Raio padrão ajustado para 4px (diâmetro de 8px, elimina bordas pretas)

    def mouse_click(event, mx, my, flags, param):
        nonlocal target_pos
        if event == cv2.EVENT_LBUTTONDOWN:
            if 0 <= mx < w and 0 <= my < h:
                target_pos[0] = mx
                target_pos[1] = my

    cv2.namedWindow(win_title, cv2.WINDOW_AUTOSIZE)
    dummy_panel = np.zeros((max(h, 160), w + 180, 3), dtype=np.uint8)
    cv2.imshow(win_title, dummy_panel)
    cv2.waitKey(1)
    cv2.setMouseCallback(win_title, mouse_click)

    print("\n==================================================")
    print("   MIRA CIRCULAR DE CALIBRAÇÃO DOS 4 ÍCONES       ")
    print("==================================================")
    print(" -> CLIQUE COM O MOUSE em cima do ícone no Minimap.")
    print(" -> Use '+' ou '-' para AUMENTAR/DIMINUIR o tamanho do círculo.")
    print(" -> Pressione ENTER ou ESPAÇO para salvar a captura.")
    print("==================================================\n")

    for filename, title in marks:
        target_pos[0] = w // 2
        target_pos[1] = h // 2

        print(f"\n -> Recortando: '{title}'... (Clique no ícone e aperte ENTER)")

        while True:
            full_frame, _ = get_calibrator_frame()
            minimap_crop = full_frame[y:y+h, x:x+w].copy()

            cx, cy = target_pos
            cx = max(crop_radius, min(w - crop_radius, cx))
            cy = max(crop_radius, min(h - crop_radius, cy))

            # Desenha o RETÂNGULO DE MIRA no minimap
            display_map = minimap_crop.copy()
            cv2.rectangle(display_map, (cx - crop_radius, cy - crop_radius), (cx + crop_radius, cy + crop_radius), (0, 255, 255), 1)
            cv2.circle(display_map, (cx, cy), 1, (0, 255, 0), -1)

            # Recorta a região focada do ícone limpa
            x1, y1 = cx - crop_radius, cy - crop_radius
            x2, y2 = cx + crop_radius, cy + crop_radius
            focused_snippet = minimap_crop[y1:y2, x1:x2].copy()

            # Painel com dimensões separadas (Sem sobreposição de texto no Zoom)
            panel_h = max(h + 75, 250)
            panel_w = w + 240
            panel = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
            panel[:] = (20, 22, 26)  # Fundo dark clean

            # 1. Desenha o Minimap no canto superior esquerdo
            panel[0:h, 0:w] = display_map
            cv2.rectangle(panel, (0, 0), (w - 1, h - 1), (60, 60, 60), 1)

            # 2. Desenha o Zoom HD da Lupa na coluna da direita
            if focused_snippet.size > 0:
                zoom_snippet = cv2.resize(focused_snippet, (180, 180), interpolation=cv2.INTER_NEAREST)
                cv2.rectangle(zoom_snippet, (0, 0), (179, 179), (0, 255, 255), 2)
                # Mira vermelha central no Zoom
                cv2.line(zoom_snippet, (82, 90), (98, 90), (0, 0, 255), 1)
                cv2.line(zoom_snippet, (90, 82), (90, 98), (0, 0, 255), 1)
                panel[30:210, w + 30:w + 210] = zoom_snippet

            cv2.putText(panel, "LUPA DE AMPLIACAO (HD)", (w + 32, 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

            # 3. Rodapé dedicado para informações e objetivos (Abaixo do minimap)
            cv2.putText(panel, f"OBJETIVO: {title}", (15, h + 28), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            cv2.putText(panel, f"Tamanho: {crop_radius*2}x{crop_radius*2}px  (+/- Ajustar)  [ENTER Salvar]", (15, h + 55), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)

            cv2.imshow(win_title, panel)
            key = cv2.waitKey(30) & 0xFF

            if key == ord('+') or key == ord('='):
                crop_radius = min(20, crop_radius + 1)
                print(f"    [Tamanho da Mira] Aumentado para {crop_radius}px")
            elif key == ord('-') or key == ord('_'):
                crop_radius = max(3, crop_radius - 1)
                print(f"    [Tamanho da Mira] Reduzido para {crop_radius}px")
            elif key == 13 or key == 32: # ENTER ou ESPAÇO
                if focused_snippet.size > 0:
                    save_path = os.path.join("templates", filename)
                    cv2.imwrite(save_path, focused_snippet)
                    template_paths[filename.replace(".png", "")] = save_path
                    print(f"    ✅ Ícone de '{title}' capturado em Alta Definição! ({focused_snippet.shape[1]}x{focused_snippet.shape[0]}px salvo em '{save_path}')")
                break
            elif key == 27: # ESC
                print(f"    ⚠️ Seleção de '{title}' cancelada.")
                break

    cv2.destroyAllWindows()
    config["template_marks"] = template_paths
    save_config(config)
    print("\n[Calibrador] Calibração dos Ícones concluída com sucesso em Alta Definição!")






def calibrate_all():
    config = load_config()
    print("\n==========================================")
    print("      PASSO 1: SELEÇÃO DA REGIÃO DO BATTLE ")
    print("==========================================")
    print("Selecione a janela/lista do Battle onde aparecem as criaturas.")
    b_roi = select_region("1. Selecione o BATTLE LIST")
    if b_roi:
        config["battle_roi"] = b_roi
        print(f"Battle ROI salvo: {b_roi}")
    
    print("\n==========================================")
    print("      PASSO 2: SELEÇÃO DA REGIÃO DO MINIMAP ")
    print("==========================================")
    print("Selecione a janela inteira do Minimap no Tibia.")
    m_roi = select_region("2. Selecione o MINIMAP")
    if m_roi:
        config["minimap_roi"] = m_roi
        print(f"Minimap ROI salvo: {m_roi}")

    print("\n==========================================")
    print("      PASSO 3: SELEÇÃO DA BARRA DE HP (VIDA) ")
    print("==========================================")
    print("Desenhe um retângulo em cima da sua BARRA DE VIDA (HP).")
    hp_roi = select_region("3. Selecione a BARRA DE HP (Vida)")
    if hp_roi:
        config["hp_roi"] = hp_roi
        print(f"Barra de HP ROI salva: {hp_roi}")

    print("\n==========================================")
    print("      PASSO 4: SELEÇÃO DA BARRA DE MANA ")
    print("==========================================")
    print("Desenhe um retângulo em cima da sua BARRA DE MANA.")
    mana_roi = select_region("4. Selecione a BARRA DE MANA")
    if mana_roi:
        config["mana_roi"] = mana_roi
        print(f"Barra de Mana ROI salva: {mana_roi}")

    save_config(config)
    
    resp = input("\nDeseja calibrar os ícones das Setas do Minimap agora? (s/n): ").strip().lower()
    if resp == 's':
        calibrate_mark_templates()

    return config




