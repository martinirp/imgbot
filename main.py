import cv2
import time
import sys
import os
import threading
import keyboard
import pyautogui

try:
    from pynput import keyboard as pynput_keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = False

from utils.calibrator import load_config, save_config, calibrate_all, record_waypoints
from utils.screen import take_screenshot, crop_roi
from utils.overlay import NFSRadarOverlay, ActionStatusOverlay
from utils.window_manager import WindowManager
from modules.battle import BattleManager
from modules.walker import MinimapWalker

# CoordWalker (navegacao por coordenadas absolutas via Map Viewer)
try:
    from utils.coord_walker import CoordWalker
    COORD_WALKER_AVAILABLE = True
except ImportError:
    COORD_WALKER_AVAILABLE = False
from modules.healer import AutoHealer

# ==============================================================================
#                      CONFIGURAÇÃO PRINCIPAL DO BOT
# ==============================================================================
ATTACK_HOTKEY = "space"   # Hotkey padrão para atacar alvos no Battle List (ex: "space", "f1", etc)
LOOT_HOTKEY = "-"        # Hotkey padrão para recolher loot ao matar criaturas (ex: "-")

# Sensibilidade de detecção de alvos no Battle List:
MIN_HEALTH_PIXELS = 25   # Mínimo de pixels coloridos de barra de vida para considerar criatura
MIN_EDGE_PIXELS = 200    # Mínimo de variação de texto/bordas para considerar criatura

# Configuração da Caminhada no Minimap (Cliques + Verificação de Chegada):
WALK_DELAY = 2.5         # Delay máximo de aguardo de caminhada (2.5 segundos por clique)
USE_ARROWS = False       # False = Cliques diretos nas 4 marcas no Minimap, True = Setas (↑, ↓, ←, →)

# Atalhos Globais do teclado para controle do Bot:
KEY_TOGGLE_PAUSE = "pause" # Tecla física 'Pause / Break', 'F12' ou 'ESC' para Parar (Ctrl+C) o bot
KEY_EXIT = "esc"         # Tecla de emergência para encerrar o bot imediatamente
# ==============================================================================

class TibiaBot:
    def __init__(self, preview_mode=False):
        self.config = load_config()
        
        self.attack_hotkey = self.config.get("attack_hotkey", ATTACK_HOTKEY)
        self.loot_hotkey = self.config.get("loot_hotkey", LOOT_HOTKEY)
        self.pause_hotkey = self.config.get("pause_hotkey", KEY_TOGGLE_PAUSE)
        
        # Suporta a tecla configurada + teclas padrão de emergência (Pause/Break, F12, Esc)
        keys_set = set([self.pause_hotkey.lower(), "pause", "f12", "esc"])
        self.pause_hotkeys = list(keys_set)

        self.battle_roi = self.config["battle_roi"]
        self.minimap_roi = self.config["minimap_roi"]
        
        # Carrega a rota ativa se especificada
        active_route = self.config.get("active_route")
        if active_route:
            from utils.route_manager import load_route
            loaded_pts = load_route(active_route)
            if loaded_pts:
                self.waypoints = loaded_pts
            else:
                self.waypoints = self.config.get("waypoints", [])
        else:
            self.waypoints = self.config.get("waypoints", [])

        self.preview_mode = preview_mode
        self.is_paused = False
        self.is_running = True
        self._last_toggle_time = 0
        self._pause_key_held = False
        self.pynput_listener = None

        # Tenta conectar com a Janela do Tibia/OTServer para execução 100% em Background (Backend Mode)
        target_title = self.config.get("target_window_title", "Tibia")
        self.window_manager = WindowManager(target_title)
        if self.window_manager.win:
            print(f"[Backend Manager] 🚀 Janela do Tibia vinculada: '{self.window_manager.win_name}' (ID: {hex(self.window_manager.win_id)})")
            print(f"                ✅ MODO BACKEND ATIVADO: Captura de tela e disparos de cliques/hotkeys 100% em segundo plano.")
            print(f"                Você pode mover seu mouse livremente e alternar janelas sem atrapalhar a caça!\n")
        else:
            print(f"[Backend Manager] ⚠️ Janela 'Tibia' não encontrada diretamente. Usando modo de tela cheia padrão como fallback.\n")
            self.window_manager = None

        # Inicializa Gerenciadores repassando o window_manager (Backend Control)
        self.battle = BattleManager(self.battle_roi, 
                                    attack_hotkey=self.attack_hotkey,
                                    loot_hotkey=self.loot_hotkey,
                                    min_health_pixels=self.config.get("min_health_pixels", MIN_HEALTH_PIXELS),
                                    min_edge_pixels=self.config.get("min_edge_pixels", MIN_EDGE_PIXELS),
                                    window_manager=self.window_manager)
        
        self.walker = MinimapWalker(self.minimap_roi, 
                                   waypoints=self.waypoints,
                                   min_distance=self.config.get("min_mark_distance", 6),
                                   walk_delay=self.config.get("walk_delay", WALK_DELAY),
                                   use_arrows=USE_ARROWS,
                                   sort_mode=self.config.get("sort_mode", "clockwise"),
                                   window_manager=self.window_manager)

        # CoordWalker — carrega rota de coordenadas absolutas se configurada
        self.coord_walker = None
        coord_route = self.config.get("coord_route_file")
        if coord_route and os.path.exists(coord_route) and COORD_WALKER_AVAILABLE:
            try:
                wps   = CoordWalker.load_route_file(coord_route)
                floor = self.config.get("coord_floor", 7)
                self.coord_walker = CoordWalker(
                    self.minimap_roi, wps, floor=floor,
                    walk_delay=self.config.get("walk_delay", WALK_DELAY),
                    window_manager=self.window_manager
                )
                print(f"[CoordWalker] ✅ Rota '{os.path.basename(coord_route)}' carregada "
                      f"({len(wps)} waypoints) | Floor inicial: {floor}")
            except Exception as e:
                print(f"[CoordWalker] ⚠️  Erro ao carregar rota: {e}")
        
        self.healer = AutoHealer(self.config, window_manager=self.window_manager)

        self.radar_hud = NFSRadarOverlay(size=220)
        self.action_hud = ActionStatusOverlay(width=380, height=75)

    def setup_hotkeys(self):
        registered = []
        
        # 1. PYNPUT - Funciona no Linux (X11) sem precisar de sudo / root!
        if PYNPUT_AVAILABLE:
            def on_press(key):
                try:
                    # Checa teclas especiais do pynput
                    if key in (pynput_keyboard.Key.pause, pynput_keyboard.Key.f12, pynput_keyboard.Key.esc):
                        self.stop_bot()
                        return
                    
                    # Checa por nome ou caractere
                    k_str = ""
                    if hasattr(key, 'name') and key.name:
                        k_str = key.name.lower()
                    elif hasattr(key, 'char') and key.char:
                        k_str = str(key.char).lower()

                    if k_str in [k.lower() for k in self.pause_hotkeys]:
                        self.stop_bot()
                except Exception:
                    pass

            try:
                self.pynput_listener = pynput_keyboard.Listener(on_press=on_press)
                self.pynput_listener.daemon = True
                self.pynput_listener.start()
                registered.append("PYNPUT (Global)")
            except Exception:
                pass

        # 2. KEYBOARD (Fallback para quando rodar com sudo)
        for key in self.pause_hotkeys:
            try:
                keyboard.add_hotkey(key, self.stop_bot)
                if "KEYBOARD (Root)" not in registered:
                    registered.append("KEYBOARD (Root)")
            except Exception:
                pass
        
        keys_display = " / ".join([k.upper() for k in self.pause_hotkeys])
        if registered:
            print(f"[Keybind] Listener Global ativado ({', '.join(registered)}) para teclas: {keys_display}")
        else:
            print(f"[Keybind] ⚠️ Aviso: Não foi possível registrar os atalhos com teclado.")

    def stop_bot(self):
        now = time.time()
        if now - getattr(self, '_last_toggle_time', 0) < 0.4: # Cooldown de 400ms anti-repetição
            return
        self._last_toggle_time = now
        self.is_running = False
        print(f"\n==========================================")
        print(f"   [EMERGÊNCIA / PAUSE] Tecla acionada! Encerrando bot (Ctrl+C)...")
        print(f"==========================================")
        
        if getattr(self, 'pynput_listener', None):
            try:
                self.pynput_listener.stop()
            except Exception:
                pass

        try:
            import _thread
            _thread.interrupt_main()
        except Exception:
            import os, signal
            os.kill(os.getpid(), signal.SIGINT)

    def toggle_pause(self):
        self.stop_bot()

    def run(self):
        active_route_name = self.config.get("active_route", "Nenhuma (Default)")
        keys_display = " / ".join([k.upper() for k in self.pause_hotkeys])
        print("\n==================================================")
        print("     TIBIA BOT - MINIMAP CLICKER & ULTRA LOOT     ")
        print("==================================================")
        print(f" -> Hotkey de Ataque: '{self.attack_hotkey.upper()}'")
        print(f" -> Hotkey de Loot:   '{self.loot_hotkey.upper()}'")
        print(f" -> Magia de Cura HP: '{self.healer.spell_hp_hotkey.upper()}' (<{self.healer.spell_hp_percent:.0f}%)")
        print(f" -> Poção de Vida HP: '{self.healer.pot_hp_hotkey.upper()}' (<{self.healer.pot_hp_percent:.0f}%)")
        print(f" -> Poção de Mana:    '{self.healer.pot_mana_hotkey.upper()}' (<{self.healer.pot_mana_percent:.0f}%)")
        print(f" -> Atalhos de Parar (Ctrl+C): '{keys_display}'")
        print(f" -> Status Inicial:   🟢 EM EXECUÇÃO (Aperte {keys_display} para PARAR via Ctrl+C)")
        print("==================================================\n")

        self.setup_hotkeys()

        try:
            while self.is_running:
                # Checagem direta de segurança via biblioteca keyboard (se disponível)
                try:
                    any_pressed = False
                    for k in self.pause_hotkeys:
                        if keyboard.is_pressed(k):
                            any_pressed = True
                            break
                    if any_pressed and not self._pause_key_held:
                        self._pause_key_held = True
                        self.stop_bot()
                        break
                    elif not any_pressed:
                        self._pause_key_held = False
                except Exception:
                    pass

                full_frame = None
                if self.window_manager and self.window_manager.win:
                    full_frame = self.window_manager.get_screenshot()
                if full_frame is None:
                    full_frame = take_screenshot()
                battle_frame = self.battle.get_battle_frame(full_frame)
                walk_msg = ""

                if self.is_paused:
                    walk_msg = f"Pausado (Aperte {keys_display})"
                    time.sleep(0.1)

                else:
                    # 1. PROCESSAMENTO DE SOBREVIVÊNCIA (Food + Poção HP + Magia HP + Poção Mana)
                    survival_logs = self.healer.process_survival(full_frame)
                    for log_msg in survival_logs:
                        print(f"[{time.strftime('%H:%M:%S')}] {log_msg}")

                    # 2. VERIFICAÇÃO DO BATTLE (Prioridade de Ataque e Anti-Stuck de Parede)
                    has_creatures, is_attacking, pressed, is_looting, target_stuck = self.battle.execute_attack_if_needed(full_frame, cooldown=0.35)

                    if (has_creatures or is_attacking or is_looting) and not target_stuck:
                        if is_looting and not (has_creatures or is_attacking):
                            status_text = "COLETANDO LOOT"
                        else:
                            status_text = "EM COMBATE" if is_attacking else "PREPARANDO ATAQUE"
                        if pressed:
                            print(f"[{time.strftime('%H:%M:%S')}] [{status_text}] Hotkey '{self.attack_hotkey.upper()}' disparada!")
                    else:
                        # 3. MOVIMENTAÇÃO NO MINIMAP (Dispara se não estiver em combate ativo ou se o alvo estiver preso na parede)
                        if self.coord_walker:
                            walked, walk_msg = self.coord_walker.step_walk(full_frame)
                        else:
                            walked, walk_msg = self.walker.step_walk(full_frame)

                # IMPRIME LOGS DE CAMINHADA NO CONSOLE (SEM SPAM DE 'BUSCANDO')
                if not self.is_paused and walk_msg and "Buscando" not in walk_msg and "Aguardando" not in walk_msg:
                    print(f"[{time.strftime('%H:%M:%S')}] [Caminhada] {walk_msg}")

                # HUD PREVIEW Apenas se explicitamente solicitado com --preview
                if self.preview_mode:
                    win_radar = "Tibia Bot - NFS Radar HUD"
                    minimap_crop = crop_roi(full_frame, self.minimap_roi)
                    hud_frame = self.radar_hud.render(minimap_crop, self.walker, self.battle)
                    cv2.imshow(win_radar, hud_frame)
                    k = cv2.waitKey(1) & 0xFF
                    if k in (27, ord('q'), ord('p')): # ESC, Q ou P na janela de preview fecha o bot
                        self.stop_bot()
                        break

                time.sleep(0.005)

        except KeyboardInterrupt:
            print("\n[Bot] Interrompido pelo atalho de emergência (Ctrl+C).")
        finally:
            if getattr(self, 'pynput_listener', None):
                try:
                    self.pynput_listener.stop()
                except Exception:
                    pass
            try:
                keyboard.unhook_all()
            except Exception:
                pass
            cv2.destroyAllWindows()
            print("[Bot] Execução finalizada com segurança.")

def select_active_route():
    from utils.route_manager import list_routes, load_route
    routes = list_routes()
    if not routes:
        print("Nenhuma rota personalizada encontrada.")
        return False
    print("\nRotas disponíveis:")
    for idx, r in enumerate(routes, 1):
        print(f" {idx}. {r}")
    try:
        sel_idx = int(input("Escolha o número da rota: ")) - 1
        if 0 <= sel_idx < len(routes):
            selected = routes[sel_idx]
            waypoints = load_route(selected)
            config = load_config()
            config["waypoints"] = waypoints
            config["active_route"] = selected
            config.pop("coord_route_file", None) # desativa rota de coords
            save_config(config)
            print(f"[RouteManager] Rota '{selected}' ativada com sucesso! ({len(waypoints)} waypoints)")
            return True
    except ValueError:
        pass
    print("Opção inválida.")
    return False

from utils.calibrator import load_config, save_config, calibrate_all, record_waypoints, calibrate_mark_templates

def configure_hotkeys():
    config = load_config()
    sys.stdout.write("\n------------------------------------------------\n")
    sys.stdout.write("    CONFIGURAÇÃO DE HOTKEYS, CURA, MANA E LOOT  \n")
    sys.stdout.write("------------------------------------------------\n")
    sys.stdout.write("(Pressione ENTER sem digitar nada para manter o valor atual)\n\n")
    sys.stdout.flush()
    
    # 1. Ataque e Loot
    print(f"1. Hotkey de Ataque (Atual: '{config.get('attack_hotkey', 'space')}')")
    attack_k = input("   Digite a tecla de ataque (ex: space, f1): ").strip().lower() or config.get("attack_hotkey", "space")

    print(f"\n2. Hotkey de Auto-Loot (Atual: '{config.get('loot_hotkey', '-')}')")
    loot_k = input("   Digite a tecla de loot (ex: -): ").strip().lower() or config.get("loot_hotkey", "-")

    # 3. Magia de HP
    print(f"\n3. Hotkey da Magia de Cura HP (Atual: '{config.get('spell_hp_hotkey', 'f1')}')")
    spell_k = input("   Digite a tecla (ex: f1): ").strip().lower() or config.get("spell_hp_hotkey", "f1")
    
    print(f"   Porcentagem de HP para a Magia (Atual: {config.get('spell_hp_percent', 80)}%)")
    spell_pct = input("   Digite a % (ex: 80): ").strip() or str(config.get("spell_hp_percent", 80))
    
    # 4. Poção de HP (Emergência)
    print(f"\n4. Hotkey da Poção de Vida HP (Atual: '{config.get('pot_hp_hotkey', 'f2')}')")
    pot_hp_k = input("   Digite a tecla (ex: f2): ").strip().lower() or config.get("pot_hp_hotkey", "f2")
    
    print(f"   Porcentagem de HP para a Poção HP (Atual: {config.get('pot_hp_percent', 50)}%)")
    pot_hp_pct = input("   Digite a % (ex: 50): ").strip() or str(config.get("pot_hp_percent", 50))
    
    # 5. Poção de Mana
    print(f"\n5. Hotkey da Poção de Mana (Atual: '{config.get('pot_mana_hotkey', 'f3')}')")
    pot_mana_k = input("   Digite a tecla (ex: f3): ").strip().lower() or config.get("pot_mana_hotkey", "f3")
    
    print(f"   Porcentagem de Mana para a Poção (Atual: {config.get('pot_mana_percent', 60)}%)")
    pot_mana_pct = input("   Digite a % (ex: 60): ").strip() or str(config.get("pot_mana_percent", 60))
    
    # 6. Food
    print(f"\n6. Hotkey de Food (Atual: '{config.get('food_hotkey', 'f10')}')")
    food_k = input("   Digite a tecla de Food (ex: f10): ").strip().lower() or config.get("food_hotkey", "f10")
    
    print(f"   Intervalo do Food em segundos (Atual: {config.get('food_interval', 60.0)}s)")
    food_sec = input("   Digite os segundos (ex: 60): ").strip() or str(config.get("food_interval", 60.0))

    # 7. Pause
    print(f"\n7. Hotkey de Pausa/Retomar (Atual: '{config.get('pause_hotkey', 'pause')}')")
    pause_k = input("   Digite a tecla de pause (ex: pause, f12, p): ").strip().lower() or config.get("pause_hotkey", "pause")

    config["attack_hotkey"] = attack_k
    config["loot_hotkey"] = loot_k
    config["spell_hp_hotkey"] = spell_k
    config["pot_hp_hotkey"] = pot_hp_k
    config["pot_mana_hotkey"] = pot_mana_k
    config["food_hotkey"] = food_k
    config["pause_hotkey"] = pause_k

    try:
        config["spell_hp_percent"] = float(spell_pct)
        config["pot_hp_percent"] = float(pot_hp_pct)
        config["pot_mana_percent"] = float(pot_mana_pct)
        config["food_interval"] = float(food_sec)
    except ValueError:
        pass

    save_config(config)
    print("\n✅ Configurações de Hotkeys, Cura e Loot atualizadas com sucesso!")



def select_target_window():
    wm = WindowManager()
    windows = wm.list_all_windows()
    if not windows:
        print("\nNenhuma janela aberta foi detectada pelo X11.")
        return False

    print("\n------------------------------------------------")
    print("      SELEÇÃO DE JANELA ALVO PARA MODO BACKEND  ")
    print("------------------------------------------------")
    for idx, (win_obj, title, win_id) in enumerate(windows, 1):
        print(f" {idx}. [{hex(win_id)}] {title}")
    print("------------------------------------------------")

    try:
        sel = int(input("Escolha o número da janela do jogo: ")) - 1
        if 0 <= sel < len(windows):
            _, chosen_title, _ = windows[sel]
            config = load_config()
            config["target_window_title"] = chosen_title
            save_config(config)
            print(f"\n✅ Janela alvo salva com sucesso: '{chosen_title}'")
            return True
    except ValueError:
        pass
    print("\nOpção inválida.")
    return False


def select_coord_route():
    """Seleciona uma rota de coordenadas absolutas (criada no Map Viewer)."""
    if not COORD_WALKER_AVAILABLE:
        print("\n[CoordWalker] Modulo nao disponivel. Verifique utils/coord_walker.py")
        return False

    # Busca rotas na pasta routes/
    routes = CoordWalker.list_route_files("routes")

    # Tambem busca na raiz do projeto (rotas salvas pelo browser)
    import glob
    for fpath in sorted(glob.glob("route_*.json")):
        try:
            import json as _json
            with open(fpath) as f:
                data = _json.load(f)
            if isinstance(data, list) and data and isinstance(data[0], dict) and "x" in data[0]:
                fname = os.path.basename(fpath)
                if not any(r[0] == fname for r in routes):
                    routes.append((fname, fpath, len(data)))
        except Exception:
            pass

    if not routes:
        print("\nNenhuma rota de coordenadas encontrada.")
        print("Abra o Map Viewer, desenhe uma rota e salve o arquivo JSON.")
        return False

    print("\n------------------------------------------------")
    print("      ROTAS DE COORDENADAS DISPONIVEIS          ")
    print("------------------------------------------------")
    for idx, (fname, fpath, count) in enumerate(routes, 1):
        print(f" {idx}. {fname}  ({count} waypoints)")
    print("------------------------------------------------")

    try:
        sel = int(input("Escolha o numero da rota (0 para cancelar): ")) - 1
        if sel < 0:
            return False
        if 0 <= sel < len(routes):
            fname, fpath, count = routes[sel]

            floor_input = input(f"Floor inicial (7=surface, ENTER para 7): ").strip()
            floor = int(floor_input) if floor_input.isdigit() else 7

            config = load_config()
            config["coord_route_file"] = fpath
            config["coord_floor"]      = floor
            config["active_route"]     = "Nenhuma" # desativa rota de setas
            save_config(config)
            print(f"\n✅ Rota de coordenadas '{fname}' ativa! ({count} waypoints | Floor {floor})")
            return True
    except (ValueError, IndexError):
        pass
    print("Opcao invalida.")
    return False


def open_map_viewer():
    """Abre o Map Viewer no navegador (inicia map_server.py se nao estiver rodando)."""
    import subprocess, webbrowser
    server_path = os.path.join(os.path.dirname(__file__), "map_server.py")
    if not os.path.exists(server_path):
        print("\n[MapViewer] map_server.py nao encontrado!")
        return
    print("\n[MapViewer] Iniciando servidor do mapa...")
    subprocess.Popen([sys.executable, server_path],
                     creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
    import time as _t; _t.sleep(1.0)
    webbrowser.open("http://localhost:8765")
    print("[MapViewer] Aberto em http://localhost:8765")


def show_menu():
    config    = load_config()
    active_r  = config.get("active_route", "Nenhuma")
    coord_r   = config.get("coord_route_file", None)
    coord_lbl = os.path.basename(coord_r) if coord_r else "Nenhuma"
    target_win = config.get("target_window_title", "Tibia")
    print("\n------------------------------------------------")
    print("       PAINEL DE CONTROLE DE AUTOMAÇÃO         ")
    print("------------------------------------------------")
    print(f" Janela Alvo:   [{target_win}]")
    print(f" Rota (Setas):  [{active_r}]")
    print(f" Rota (Coords): [{coord_lbl}]  ← Floor {config.get('coord_floor', 7)}")
    print(f" Magia HP: '{config.get('spell_hp_hotkey', 'f1').upper()}' (<{config.get('spell_hp_percent', 80)}%) | Pot HP: '{config.get('pot_hp_hotkey', 'f2').upper()}' (<{config.get('pot_hp_percent', 50)}%)")
    print(f" Pot Mana: '{config.get('pot_mana_hotkey', 'f3').upper()}' (<{config.get('pot_mana_percent', 60)}%) | Food: '{config.get('food_hotkey', 'f10').upper()}' ({config.get('food_interval', 60.0)}s)")
    print("------------------------------------------------")
    print(" 1. Iniciar Bot (Caça + Auto-Loot + Food + Cura)")
    print(" 2. Iniciar Bot com HUD Overlay (--preview)")
    print(" 3. Calibrar Ícones das Setas do Minimap")
    print(" 4. Calibrar Regiões da Tela (Battle, Minimap, HP, Mana)")
    print(" 5. Configurar Hotkeys e Porcentagens de Cura")
    print(" 6. Gravar Nova Rota de Waypoints no Minimap (sistema antigo)")
    print(" 7. Selecionar Rota de Setas (sistema antigo)")
    print(" 8. Selecionar Janela Alvo do Jogo (Tibia / OTServer)")
    print("------------------------------------------------")
    print(" 9. Selecionar Rota de Coordenadas (Map Viewer) ← NOVO")
    print("10. Abrir Map Viewer no Navegador               ← NOVO")
    print("------------------------------------------------")
    print("11. Sair")
    print("------------------------------------------------")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--start" in args or "-s" in args:
        bot = TibiaBot(preview_mode=False)
        bot.run()
        sys.exit(0)

    if "--calibrate-marks" in args or "--marks" in args or "-m" in args:
        calibrate_mark_templates()
        sys.exit(0)

    if "--record" in args or "-r" in args:
        record_waypoints()
        sys.exit(0)

    if "--calibrate" in args or "-c" in args or "--reset" in args:
        calibrate_all()
        sys.exit(0)

    if "--preview" in args or "-p" in args or "--debug" in args:
        bot = TibiaBot(preview_mode=True)
        bot.run()
        sys.exit(0)

    # MENU CLI INTERATIVO PADRÃO
    while True:
        show_menu()
        opcao = input("Escolha uma opção (1-11): ").strip()
        if opcao == "1":
            bot = TibiaBot(preview_mode=False)
            bot.run()
            break
        elif opcao == "2":
            bot = TibiaBot(preview_mode=True)
            bot.run()
            break
        elif opcao == "3":
            calibrate_mark_templates()
        elif opcao == "4":
            calibrate_all()
        elif opcao == "5":
            configure_hotkeys()
        elif opcao == "6":
            record_waypoints()
        elif opcao == "7":
            select_active_route()
        elif opcao == "8":
            select_target_window()
        elif opcao == "9":
            select_coord_route()
        elif opcao == "10":
            open_map_viewer()
        elif opcao == "11":
            print("Saindo...")
            break
        else:
            print("Opcao invalida.")

