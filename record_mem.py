#!/usr/bin/env python3
"""
record_mem.py - Grava waypoints lendo posicao DIRETO DA MEMORIA.
Uso: sudo XAUTHORITY=$HOME/.Xauthority DISPLAY=:0 python3 record_mem.py nome_da_rota
"""
import os, sys, json, struct, time, tty, termios

CONFIG_FILE = "config.json"
ROUTES_DIR  = "routes"

def load_cfg():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def read_pos(cfg):
    pid  = cfg["mem_pid"]
    fmt  = cfg.get("mem_fmt", "<H")
    size = struct.calcsize(fmt)
    def _r(addr):
        with open(f"/proc/{pid}/mem", "rb") as f:
            f.seek(addr); return struct.unpack(fmt, f.read(size))[0]
    return _r(cfg["mem_x_addr"]), _r(cfg["mem_y_addr"]), _r(cfg["mem_z_addr"])

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def main():
    nome = sys.argv[1] if len(sys.argv) > 1 else "rota"
    cfg  = load_cfg()
    wps  = []
    os.makedirs(ROUTES_DIR, exist_ok=True)

    print("\n=== GRAVADOR DE WAYPOINTS (Memoria) ===")
    print("  ESPACO  -> grava posicao atual")
    print("  U       -> desfaz ultimo")
    print("  ENTER   -> salva e sai")
    print("  Q       -> cancela")
    print("=========================================\n")

    while True:
        x, y, z = read_pos(cfg)
        print(f"\r  Posicao: X={x}  Y={y}  Z={z}   WPs={len(wps)}  ", end="", flush=True)

        ch = getch()

        if ch == " ":
            wps.append({"x": x, "y": y, "z": z})
            print(f"\n  [WP{len(wps)}] Gravado: X={x}  Y={y}  Z={z}")

        elif ch in ("u", "U"):
            if wps:
                r = wps.pop()
                print(f"\n  [Desfazer] Removido: X={r['x']}  Y={r['y']}")
            else:
                print("\n  [Desfazer] Nenhum WP para remover.")

        elif ch in ("\r", "\n"):
            break

        elif ch in ("q", "Q", "\x1b"):
            print("\n\n  Cancelado.")
            return

        time.sleep(0.05)

    if not wps:
        print("\n\n  Nenhum WP gravado.")
        return

    fname = os.path.join(ROUTES_DIR, nome + ".json")
    with open(fname, "w") as f:
        json.dump(wps, f, indent=2)
    print(f"\n\n  [OK] {len(wps)} waypoints salvos em '{fname}'!")

if __name__ == "__main__":
    main()
