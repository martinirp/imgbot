import os, json, time, threading, cv2, numpy as np
from utils.screen import take_screenshot
from utils.calibrator import load_config
from utils.position_tracker import PositionTracker

ROUTES_DIR = "routes"

def main():
    config = load_config()
    roi = config.get("minimap_roi", [0,0,100,100])
    tracker = PositionTracker(roi)
    waypoints = []
    state = {"pos": None, "conf": 0.0, "found": False, "stop": False}

    def tracking_loop():
        while not state["stop"]:
            try:
                frame = take_screenshot()
                result = tracker.locate(frame, floor=None)
                if result and result.get("found"):
                    state["pos"] = (result["x"], result["y"], result["z"])
                    state["conf"] = result["confidence"]
                    state["found"] = True
                else:
                    state["conf"] = result["confidence"] if result else 0.0
                    state["found"] = False
            except Exception:
                pass
            time.sleep(0.2)

    threading.Thread(target=tracking_loop, daemon=True).start()
    os.makedirs(ROUTES_DIR, exist_ok=True)

    print("\n" + "="*55)
    print("   GRAVADOR INTERATIVO DE WAYPOINTS")
    print("="*55)
    print("  -> ESPACO : Grava waypoint na posicao atual")
    print("  -> U      : Desfaz o ultimo waypoint")
    print("  -> ENTER  : Salva a rota e sai")
    print("  -> Q/ESC  : Cancela sem salvar")
    print("="*55)
    print("\n  Localizando (aguarde ~5-45s)...\n")

    cv2.namedWindow("Gravador de Waypoints", cv2.WINDOW_AUTOSIZE)

    while True:
        try:
            frame = take_screenshot()
            x0,y0,w,h = roi
            crop = frame[y0:y0+h, x0:x0+w]
            zoom = max(1, 250 // max(w,h))
            canvas = cv2.resize(crop, (w*zoom, h*zoom), interpolation=cv2.INTER_NEAREST)
        except:
            canvas = np.zeros((200,200,3), dtype=np.uint8)

        ph = canvas.shape[0]+130
        panel = np.zeros((ph, max(canvas.shape[1],440), 3), dtype=np.uint8)
        panel[:] = (20,22,28)
        panel[:canvas.shape[0], :canvas.shape[1]] = canvas

        conf_val = state["conf"]
        found = state["found"]
        pos = state["pos"]

        if found and pos:
            px,py,pz = pos
            ptxt = "Posicao: X=%d  Y=%d  Z=%d  (%.0f%%)" % (px,py,pz,conf_val*100)
            col = (0,255,80)
        else:
            ptxt = "Localizando... (%.0f%%)" % (conf_val*100)
            col = (0,140,255)

        wtxt = "Waypoints: %d" % len(waypoints)
        ltxt = ("Ultimo: X=%d Y=%d Z=%d" % (waypoints[-1]["x"],waypoints[-1]["y"],waypoints[-1]["z"])) if waypoints else "Nenhum ainda"

        yo = canvas.shape[0]+22
        cv2.putText(panel, ptxt, (10,yo),   cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
        cv2.putText(panel, wtxt, (10,yo+28),cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
        cv2.putText(panel, ltxt, (10,yo+54),cv2.FONT_HERSHEY_SIMPLEX, 0.45,(150,200,150), 1)
        cv2.putText(panel,"[ESPACO] Gravar  [U] Desfazer  [ENTER] Salvar  [Q] Sair",
                    (10,yo+86),cv2.FONT_HERSHEY_SIMPLEX, 0.38,(100,100,100),1)
        cv2.imshow("Gravador de Waypoints", panel)
        key = cv2.waitKey(100) & 0xFF

        if key == 32:
            if not found or pos is None:
                print("  [!] Aguardando localizacao...")
            else:
                px,py,pz = pos
                wp = {"x":px,"y":py,"z":pz}
                waypoints.append(wp)
                print("  [WP%d] X=%d  Y=%d  Z=%d" % (len(waypoints),px,py,pz))
        elif key in (ord("u"),ord("U")):
            if waypoints:
                r=waypoints.pop()
                print("  [Desfazer] X=%d Y=%d" % (r["x"],r["y"]))
            else:
                print("  [Desfazer] Vazio.")
        elif key == 13:
            state["stop"]=True
            cv2.destroyAllWindows()
            if not waypoints:
                print("\n  Nenhum WP gravado.")
                return
            nome = raw_input("  Nome da rota: ") if False else input("  Nome da rota: ")
            nome = nome.strip() or "rota"
            fname = os.path.join(ROUTES_DIR, nome+".json")
            with open(fname,"w",encoding="utf-8") as f:
                json.dump(waypoints,f,indent=2)
            print("\n  [OK] Rota salva em '%s'!" % fname)
            return
        elif key in (ord("q"),ord("Q"),27):
            state["stop"]=True
            cv2.destroyAllWindows()
            print("\n  Cancelado.")
            return

if __name__ == "__main__":
    main()
