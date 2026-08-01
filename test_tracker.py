"""
test_tracker.py - Teste visual do template matching de posicao

Abre uma janela mostrando:
  - Esquerda:  canvas do mapa composto (tiles do TibiaMaps)
  - Direita:   minimap capturado do jogo
  - Highlight: regiao onde o match foi encontrado

Uso:
  python test_tracker.py          -> usa config.json para saber o minimap_roi
  python test_tracker.py --live   -> loop continuo capturando a tela
"""

import sys
import cv2
import numpy as np
import time
from utils.calibrator import load_config
from utils.screen import take_screenshot
from utils.map_loader import MapLoader
from utils.position_tracker import PositionTracker


def draw_result(canvas, origin_x, origin_y, match_loc, template_w, template_h, world_x, world_y, confidence):
    """Desenha o resultado do match no canvas."""
    vis = canvas.copy()
    # Se a imagem for muito grande para exibir, reduz
    max_side = 900
    scale = 1.0
    h, w = vis.shape[:2]
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        vis = cv2.resize(vis, (int(w * scale), int(h * scale)))

    # Retangulo da regiao encontrada
    col, row = match_loc
    x1 = int((col) * scale)
    y1 = int((row) * scale)
    x2 = int((col + template_w) * scale)
    y2 = int((row + template_h) * scale)
    color = (0, 255, 80) if confidence >= 0.55 else (0, 100, 255)
    cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

    # Cruz no centro do personagem
    cx = int((col + template_w // 2) * scale)
    cy = int((row + template_h // 2) * scale)
    cv2.drawMarker(vis, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 12, 2)

    # Label
    txt = f"X:{world_x}  Y:{world_y}  Conf:{confidence*100:.1f}%"
    cv2.putText(vis, txt, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    return vis


def main():
    live_mode = "--live" in sys.argv
    config    = load_config()
    roi       = config.get("minimap_roi", [0, 0, 100, 100])

    print(f"\n{'='*55}")
    print(f"  TESTE DE TEMPLATE MATCHING - Position Tracker")
    print(f"{'='*55}")
    print(f"  Minimap ROI: {roi}")
    print(f"  Modo: {'LIVE (loop continuo)' if live_mode else 'SNAPSHOT (unico frame)'}")
    print(f"  Floors disponíveis: carregando...")
    print()

    tracker = PositionTracker(roi)
    floors  = tracker.loader.available_floors()
    print(f"  Floors: {floors}")
    print()

    def run_once():
        t0         = time.time()
        full_frame = take_screenshot()
        result     = tracker.locate(full_frame, floor=None)
        elapsed    = time.time() - t0

        if result and result.get("found"):
            x, y, z   = result["x"], result["y"], result["z"]
            conf      = result["confidence"]
            print(f"  [OK] Posicao encontrada: X={x}  Y={y}  Z={z}  "
                  f"Confianca={conf*100:.1f}%  Tempo={elapsed*1000:.0f}ms")

            # Visualizacao do resultado
            debug = tracker._debug_result
            if debug and "canvas" in debug:
                canvas_vis = draw_result(
                    debug["canvas"],
                    debug["origin_x"], debug["origin_y"],
                    debug["match_loc"],
                    roi[2], roi[3],
                    x, y, conf
                )

                # Minimap capturado (ampliado para visualizacao)
                x0, y0, w, h = roi
                minimap_crop = full_frame[y0:y0+h, x0:x0+w]
                zoom_factor  = max(1, 200 // max(w, h))
                minimap_big  = cv2.resize(minimap_crop, (w*zoom_factor, h*zoom_factor),
                                         interpolation=cv2.INTER_NEAREST)

                # Painel lateral com minimap
                pad_h = canvas_vis.shape[0]
                panel_w = minimap_big.shape[1] + 20
                panel   = np.zeros((pad_h, panel_w, 3), dtype=np.uint8)
                panel[:] = (20, 22, 28)

                # Cola minimap no centro do painel
                my = (pad_h - minimap_big.shape[0]) // 2
                mh = minimap_big.shape[0]
                mw = minimap_big.shape[1]
                if my >= 0 and my + mh <= pad_h:
                    panel[my:my+mh, 10:10+mw] = minimap_big

                cv2.putText(panel, "MINIMAP", (10, min(my-8, pad_h-5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100,100,100), 1)

                combined = np.hstack([canvas_vis, panel])
                cv2.imshow("Position Tracker - Template Matching", combined)
        else:
            conf = result["confidence"] if result else 0.0
            print(f"  [FALHA] Match nao encontrado.  Confianca={conf*100:.1f}%  Tempo={elapsed*1000:.0f}ms")
            print(f"  Dica: verifique se o minimap_roi esta correto e o jogo esta aberto.")
            cv2.imshow("Position Tracker - Template Matching",
                       np.zeros((300, 600, 3), dtype=np.uint8))

    if live_mode:
        print("  Pressione ESC ou Q para sair. S para screenshot.\n")
        while True:
            run_once()
            key = cv2.waitKey(500) & 0xFF
            if key in (27, ord('q'), ord('Q')):
                break
            if key in (ord('s'), ord('S')):
                cv2.imwrite("tracker_debug.png",
                            cv2.getWindowImageRect("Position Tracker - Template Matching") or
                            np.zeros((1,1,3), dtype=np.uint8))
    else:
        run_once()
        print("\n  Pressione qualquer tecla na janela para fechar.")
        cv2.waitKey(0)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
