#!/usr/bin/env python3
import tkinter as tk
import subprocess

def get_mouse():
    try:
        out = subprocess.check_output(['xdotool', 'getmouselocation', '--shell'], text=True)
        lines = out.strip().split('\n')
        x = lines[0].split('=')[1]
        y = lines[1].split('=')[1]
        return x, y
    except:
        return "0", "0"

root = tk.Tk()
root.title("Rastreador de Mouse")

# Remove bordas da janela e força ficar no topo (se o sistema permitir)
try:
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.attributes('-alpha', 0.9)
except:
    pass

root.configure(bg='#13131f')

# Label de texto
label = tk.Label(root, text=" X: 0 | Y: 0 ", font=('Monospace', 14, 'bold'), fg='#4ecca3', bg='#13131f')
label.pack(padx=10, pady=10)

# Posiciona no canto da tela (X=20, Y=20)
root.geometry("+20+20")

# Loop infinito leve
def update_coords():
    x, y = get_mouse()
    label.config(text=f" X: {x} | Y: {y} ")
    root.after(100, update_coords) # Atualiza a cada 100ms

update_coords()
root.mainloop()
