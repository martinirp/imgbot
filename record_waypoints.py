"""
record_waypoints.py - Gravador interativo de Waypoints por Coordenadas

Como usar:
  1. Abra o Tibia e va ate o primeiro ponto da rota
  2. Rode: DISPLAY=:0 python3 record_waypoints.py
  3. Pressione ESPACO para gravar o waypoint na posicao atual
  4. Caminhe ate o proximo ponto e repita
  5. Pressione ENTER para salvar a rota com um nome
  6. Pressione Q para cancelar

O arquivo de rota e salvo em: routes/<nome>.json
Formato: [{"x": int, "y": int, "z": int}, ...]
"""

import sys
import os
import json
import time
import cv2
import numpy as np
from utils.screen import take_screenshot
from utils.calibrator import load_config
from utils.position_tracker import PositionTracker

ROUTES_DIR = "routes"


def main():
    config = load_config()
    roi = config.get("minimap_roi", [0, 0, 100, 100])

    tracker = PositionTracker(roi)
    waypoints = []
    last_pos = None

    os.makedirs(ROUTES_DIR, exist_ok=True)

    print("\n" + "=" * 55)
    print("   GRAVADOR INTERATIVO DE WAYPOINTS (Coordenadas)")
    print("=" * 55)
    print("  -> ESPACO : Grava waypoint na posicao atual")
    print("  -> U      : Desfaz o ultimo waypoint")
    print("  -> ENTER  : Salva a rota e sai")
    print("  -> Q/ESC  : Cancela sem salvar")
    print("=" * 55)
    print("\n  Localizando personagem no mapa...\n")

    cv2.namedWindow("Gravador de Waypoints", cv2.WINDOW_AUTOSIZE)

    while True:
        frame = take_screenshot()
        result = tracker.locate(frame, floor=None)

        x0, y0, w, h = roi
        minimap_crop = frame[y0:y0+h, x0:x0+w]
        zoom = max(1, 250 // max(w, h))
        canvas = cv2.resize(minimap_crop, (w * zoom, h * zoom), interpolation=cv2.INTER_NEAREST)

        panel_h = canvas.shape[0] + 120
        panel = np.zeros((panel_h, max(canvas.shape[1], 400), 3), dtype=np.uint8)
        panel[:] = (20, 22, 28)
        panel[:canvas.shape[0], :canvas.shape[1]] = canvas

        if result and result.get("found"):
            last_pos = (result["x"], result["y"], result["z"])
            conf = result["confidence"]
            pos_txt = f"Posicao: X={last_pos[0]}  Y={last_pos[1]}  Z={last_pos[2]}  ({conf*100:.0f}%)"
            color = (0, 255, 80)
        else:
            conf = result["confidence"] if result else 0.0
            pos_txt = f"Localizando... ({conf*100:.0f}%)"
            color = (0, 100, 255)

        wp_txt = f"Waypoints gravados: {len(waypoints)}"
        if waypoints:
            lw = waypoints[-1]
            last_txt = f"Ultimo: X={lw[chr(120)]} Y={lw[chr(121)]} Z={lw[chr(122)]}"
        else:
            last_txt = "Nenhum waypoint ainda"

        y_off = canvas.shape[0] + 22
        cv2.putText(panel, pos_txt,  (10, y_off),      cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        cv2.putText(panel, wp_txt,   (10, y_off + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(panel, last_txt, (10, y_off + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 200, 150), 1)
        cv2.putText(panel, "[ESPACO] Gravar  [U] Desfazer  [ENTER] Salvar  [Q] Sair",
                    (10, y_off + 80), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 120, 120), 1)

        cv2.imshow("Gravador de Waypoints", panel)
        key = cv2.waitKey(300) & 0xFF

        if key == 32:
            if last_pos is None:
                print("  [!] Aguardando localizacao... tente novamente.")
            else:
                wp = {"x": last_pos[0], "y": last_pos[1], "z": last_pos[2]}
                waypoints.append(wp)
                print(f"  [WP{len(waypoints)}] Gravado: X={wp['x']}  Y={wp['y']}  Z={wp['z']}")

        elif key in (ord('u'), ord('U')):
            if waypoints:
                removed = waypoints.pop()
                print(f"  [Desfazer] WP removido: X={removed['x']}  Y={removed['y']}")
            else:
                print("  [Desfazer] Nenhum waypoint para remover.")

        elif key == 13:
            cv2.destroyAllWindows()
            if not waypoints:
                print("\n  Nenhum waypoint gravado. Saindo.")
                return
            print(f"\n  {len(waypoints)} waypoints prontos para salvar.")
            nome = input("  Digite o nome da rota (ex: rotworms, trolls): ").strip()
            if not nome:
                nome = "rota"
            filename = os.path.join(ROUTES_DIR, nome + ".json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(waypoints, f, indent=2)
            print(f"\n  [OK] Rota '{nome}' salva com {len(waypoints)} waypoints em '{filename}'!")
            print(f"  Use 'DISPLAY=:0 python3 test_walker.py {nome}.json' para testar.\n")
            return

        elif key in (ord('q'), ord('Q'), 27):
            print("\n  Gravacao cancelada.")
            cv2.destroyAllWindows()
            return


if __name__ == "__main__":
    main()
