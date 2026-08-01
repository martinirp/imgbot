import sys, time, cv2, json
from utils.screen import take_screenshot
from utils.calibrator import load_config
from utils.coord_walker import CoordWalker
from utils.window_manager import WindowManager

route_file = sys.argv[1] if len(sys.argv) > 1 else "routes/teste_abs.json"

config = load_config()
roi    = config.get("minimap_roi", [0,0,100,100])

waypoints = json.load(open(route_file, encoding="utf-8"))
print("Rota carregada: %d waypoints de '%s'" % (len(waypoints), route_file))

wm = None
try:
    wm = WindowManager(config.get("target_window_title","Tibia"))
    if wm.win:
        print("[WindowManager] Janela encontrada: %s" % wm.win_name)
    else:
        wm = None
        print("[WindowManager] Janela nao encontrada, usando pyautogui")
except Exception as e:
    wm = None

walker = CoordWalker(roi, waypoints, walk_delay=0.6, min_distance=5, window_manager=wm)

print("\nIniciando walker. CTRL+C para parar.\n")

while True:
    frame = take_screenshot()
    walked, msg = walker.step_walk(frame)
    print(msg)
    time.sleep(0.1)
