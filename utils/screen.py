import cv2
import numpy as np
import mss

_sct = None

def get_sct():
    global _sct
    if _sct is None:
        _sct = mss.mss()
    return _sct

def take_screenshot(region=None):
    """
    Captura a tela inteira via mss (comprovadamente funcional).
    O WindowManager/XGetImage foi removido pois retorna imagem preta para
    apps OpenGL/aceleração de hardware (como o Tibia).
    """
    sct = get_sct()
    if region is None:
        monitor = sct.monitors[0]
    else:
        x, y, w, h = region
        monitor = {"top": int(y), "left": int(x), "width": int(w), "height": int(h)}
    
    sct_img = sct.grab(monitor)
    frame = np.array(sct_img)
    return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

def crop_roi(image, roi):
    """
    Recorta a região de interesse (x, y, w, h) de uma imagem dada.
    """
    x, y, w, h = [int(v) for v in roi]
    return image[y:y+h, x:x+w]

