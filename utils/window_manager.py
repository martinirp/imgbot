import time
import numpy as np
from Xlib import X, display, XK, protocol

class WindowManager:
    """
    Gerenciador de Janela X11 para execução 100% em Background (Modo Backend).
    Permite capturar a tela do Tibia e enviar cliques e teclas diretamente para a janela,
    sem mover o ponteiro do mouse físico e sem exigir que a janela esteja focada em primeiro plano.
    """
    def __init__(self, window_title="Tibia"):
        self.d = None
        self.root = None
        self.win = None
        self.win_name = ""
        self.win_id = None
        self.window_title = window_title
        self.connect()

    def raise_window(self):
        """
        Traz a janela do jogo para a frente (primeiro plano) no Linux para calibração limpa sem sobreposição.
        """
        if self.win_id:
            try:
                os.system(f"wmctrl -i -a {hex(self.win_id)} >/dev/null 2>&1")
                time.sleep(0.15)
            except Exception:
                pass

    def connect(self):
        try:
            self.d = display.Display()
            self.root = self.d.screen().root
            self.find_window(self.window_title)
        except Exception as e:
            print(f"[WindowManager] Erro ao conectar com X11: {e}")

    def list_all_windows(self):
        """
        Retorna uma lista de tuplas (win_obj, win_title, win_id) de todas as janelas visíveis no Linux X11.
        """
        if not self.d:
            return []
        
        results = []
        seen_ids = set()

        def _traverse(win):
            try:
                name = win.get_wm_name()
                if name and isinstance(name, str) and name.strip():
                    geom = win.get_geometry()
                    if geom.width >= 200 and geom.height >= 200 and win.id not in seen_ids:
                        seen_ids.add(win.id)
                        results.append((win, name.strip(), win.id))
            except Exception:
                pass

            try:
                children = win.query_tree().children
                for child in children:
                    _traverse(child)
            except Exception:
                pass

        _traverse(self.root)
        return results

    def find_window(self, title_query="Tibia"):
        if not self.d:
            return False
        
        target_win = None
        target_name = ""

        def _search(win):
            nonlocal target_win, target_name
            try:
                name = win.get_wm_name()
                if name and title_query.lower() in name.lower():
                    target_win = win
                    target_name = name
                    return True
            except Exception:
                pass

            try:
                for child in win.query_tree().children:
                    if _search(child):
                        return True
            except Exception:
                pass
            return False

        _search(self.root)

        if target_win:
            self.win = target_win
            self.win_name = target_name
            self.win_id = target_win.id
            return True
        return False

    def get_offset(self):
        """
        Retorna (win_x, win_y), a posição da janela na tela do monitor.
        """
        if not self.win:
            return 0, 0
        try:
            geom = self.win.get_geometry()
            return geom.x, geom.y
        except Exception:
            return 0, 0

    def adjust_roi(self, roi):
        """
        Converte uma ROI de tela [x, y, w, h] para coordenadas relativas da janela [rel_x, rel_y, w, h].
        """
        if not roi:
            return roi
        win_x, win_y = self.get_offset()
        x, y, w, h = [int(v) for v in roi]
        rel_x = max(0, x - win_x)
        rel_y = max(0, y - win_y)
        return [rel_x, rel_y, w, h]

    def get_screenshot(self):
        """
        Captura o frame atual da janela do Tibia em background via XGetImage.
        Retorna numpy array BGR (OpenCV) ou None se falhar.
        """
        if not self.win:
            if not self.find_window(self.window_title):
                return None
        try:
            geom = self.win.get_geometry()
            raw = self.win.get_image(0, 0, geom.width, geom.height, X.ZPixmap, 0xffffffff)
            image_bytes = raw.data
            bgra = np.frombuffer(image_bytes, dtype=np.uint8).reshape((geom.height, geom.width, 4))
            bgr = bgra[:, :, :3].copy()
            return bgr
        except Exception:
            self.find_window(self.window_title)
            return None

    def send_key(self, key_name):
        """
        Envia um toque de tecla em background diretamente para a janela do Tibia.
        """
        if not self.win or not self.d:
            return False
        
        try:
            key_name_clean = str(key_name).lower().strip()
            keysym = XK.string_to_keysym(key_name_clean)
            if not keysym:
                mapping = {
                    'space': XK.XK_space,
                    '-': XK.XK_minus,
                    # Setas direcionais
                    'up':    XK.XK_Up,
                    'down':  XK.XK_Down,
                    'left':  XK.XK_Left,
                    'right': XK.XK_Right,
                    # Numpad (movimento diagonal no Tibia)
                    'kp_up':        XK.XK_KP_Up,
                    'kp_down':      XK.XK_KP_Down,
                    'kp_left':      XK.XK_KP_Left,
                    'kp_right':     XK.XK_KP_Right,
                    'kp_home':      XK.XK_KP_Home,      # noroeste
                    'kp_end':       XK.XK_KP_End,       # sudoeste
                    'kp_page_up':   XK.XK_KP_Page_Up,   # nordeste
                    'kp_page_down': XK.XK_KP_Page_Down, # sudeste
                    # Funcoes
                    'f1': XK.XK_F1,
                    'f2': XK.XK_F2,
                    'f3': XK.XK_F3,
                    'f4': XK.XK_F4,
                    'f5': XK.XK_F5,
                    'f6': XK.XK_F6,
                    'f7': XK.XK_F7,
                    'f8': XK.XK_F8,
                    'f9': XK.XK_F9,
                    'f10': XK.XK_F10,
                    'f11': XK.XK_F11,
                    'f12': XK.XK_F12,
                }
                keysym = mapping.get(key_name_clean, 0)

            if not keysym:
                return False

            keycode = self.d.keysym_to_keycode(keysym)
            if not keycode:
                return False

            event_press = protocol.event.KeyPress(
                time=int(time.time() * 1000) & 0xffffffff,
                root=self.root,
                window=self.win,
                same_screen=1,
                child=X.NONE,
                root_x=0,
                root_y=0,
                event_x=0,
                event_y=0,
                state=0,
                detail=keycode
            )
            self.win.send_event(event_press, propagate=True)
            self.d.flush()
            time.sleep(0.015)

            event_release = protocol.event.KeyRelease(
                time=int(time.time() * 1000) & 0xffffffff,
                root=self.root,
                window=self.win,
                same_screen=1,
                child=X.NONE,
                root_x=0,
                root_y=0,
                event_x=0,
                event_y=0,
                state=0,
                detail=keycode
            )
            self.win.send_event(event_release, propagate=True)
            self.d.flush()
            return True
        except Exception:
            return False

    def send_click(self, x, y, button=1):
        """
        Envia um clique de mouse em background para coordenadas relativas da janela (x, y).
        """
        if not self.win or not self.d:
            return False
        
        try:
            rel_x = int(x)
            rel_y = int(y)

            event_press = protocol.event.ButtonPress(
                time=int(time.time() * 1000) & 0xffffffff,
                root=self.root,
                window=self.win,
                same_screen=1,
                child=X.NONE,
                root_x=rel_x,
                root_y=rel_y,
                event_x=rel_x,
                event_y=rel_y,
                state=0,
                detail=button
            )
            self.win.send_event(event_press, propagate=True)
            self.d.flush()
            time.sleep(0.02)

            event_release = protocol.event.ButtonRelease(
                time=int(time.time() * 1000) & 0xffffffff,
                root=self.root,
                window=self.win,
                same_screen=1,
                child=X.NONE,
                root_x=rel_x,
                root_y=rel_y,
                event_x=rel_x,
                event_y=rel_y,
                state=0,
                detail=button
            )
            self.win.send_event(event_release, propagate=True)
            self.d.flush()
            return True
        except Exception:
            return False
