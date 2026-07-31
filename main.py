import cv2
import numpy as np
import pyautogui
import time

def select_region():
    print("Capturando a tela para você selecionar a região...")
    # Tira um print da tela inteira
    screenshot = pyautogui.screenshot()
    frame = np.array(screenshot)
    # Converte de RGB (pyautogui) para BGR (opencv)
    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    
    print("Uma janela vai abrir. Desenhe um retângulo na área que deseja monitorar e aperte ENTER ou ESPAÇO.")
    # cv2.selectROI abre uma janela para selecionar a região
    roi = cv2.selectROI("Selecione a Regiao", frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow("Selecione a Regiao")
    
    # roi retorna (x, y, w, h)
    return roi

def check_for_changes(roi, threshold=50, delay=1.0):
    x, y, w, h = roi
    
    if w == 0 or h == 0:
        print("Região inválida selecionada (largura ou altura igual a 0).")
        return

    print(f"Monitorando a região: X={x}, Y={y}, Largura={w}, Altura={h}")
    print("Pressione Ctrl+C para parar no terminal.")

    # Captura inicial da região
    last_screenshot = pyautogui.screenshot(region=(x, y, w, h))
    last_frame = np.array(last_screenshot)
    last_gray = cv2.cvtColor(last_frame, cv2.COLOR_RGB2GRAY)

    try:
        while True:
            time.sleep(delay)
            
            # Captura a região novamente
            current_screenshot = pyautogui.screenshot(region=(x, y, w, h))
            current_frame = np.array(current_screenshot)
            current_gray = cv2.cvtColor(current_frame, cv2.COLOR_RGB2GRAY)
            
            # Calcula a diferença absoluta entre o frame atual e o anterior
            diff = cv2.absdiff(last_gray, current_gray)
            
            # Conta quantos pixels mudaram de forma significativa
            _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            changed_pixels = np.count_nonzero(thresh)
            
            if changed_pixels > threshold:
                print(f"[{time.strftime('%H:%M:%S')}] Mudança detectada! Pixels alterados: {changed_pixels}")
                # Atualiza o último frame para não ficar avisando continuamente da mesma mudança
                last_gray = current_gray
                
    except KeyboardInterrupt:
        print("\nMonitoramento encerrado pelo usuário.")

if __name__ == "__main__":
    print("Iniciando o script...")
    roi = select_region()
    # threshold define a quantidade mínima de pixels que precisam mudar
    # delay define de quanto em quanto tempo (segundos) ele checa a tela
    check_for_changes(roi, threshold=50, delay=1.0)
