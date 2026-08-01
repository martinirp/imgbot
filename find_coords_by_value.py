#!/usr/bin/env python3
"""
find_coords_by_value.py - Acha os enderecos de X, Y, Z na memoria do Tibia
usando as coordenadas conhecidas do template matching como ancora.

Uso: sudo DISPLAY=:0 ./venv/bin/python3 find_coords_by_value.py
"""

import os, sys, struct, time, json, subprocess
import numpy as np

# sudo limpa o DISPLAY -- garante que mss consegue conectar ao X11
if not os.environ.get("DISPLAY"):
    os.environ["DISPLAY"] = ":0"

CONFIG_FILE = "config.json"


def find_tibia_pid():
    for pattern in ["Tibia/bin/client", "tibia", "Tibia"]:
        try:
            out = subprocess.check_output(["pgrep", "-f", pattern], text=True).strip()
            pids = [p.strip() for p in out.splitlines() if p.strip()]
            if pids:
                return int(pids[0])
        except Exception:
            pass
    return None

def get_rw_regions(pid):
    regions = []
    try:
        with open(f"/proc/{pid}/maps") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                perms = parts[1]
                if 'r' not in perms or 'w' not in perms:
                    continue
                # ignora bibliotecas e especiais (mantem heap, stack, anonimas)
                name = parts[5] if len(parts) > 5 else ""
                if name.startswith("/") and ".so" in name:
                    continue
                start, end = [int(x, 16) for x in parts[0].split("-")]
                size = end - start
                if size < 4096 or size > 512 * 1024 * 1024:
                    continue
                regions.append((start, end))
    except Exception as e:
        print(f"[ERRO] /proc/{pid}/maps: {e}")
    return regions

def read_region(pid, start, end):
    try:
        with open(f"/proc/{pid}/mem", "rb") as f:
            f.seek(start)
            return f.read(end - start)
    except Exception:
        return b""

def search_uint16(data, value):
    """Retorna lista de offsets onde uint16 LE == value."""
    arr = np.frombuffer(data, dtype=np.uint16)
    return np.where(arr == value)[0] * 2

def search_uint32(data, value):
    """Retorna lista de offsets onde uint32 LE == value."""
    arr = np.frombuffer(data, dtype=np.uint32)
    return np.where(arr == value)[0] * 4

def read_val(pid, addr, fmt="<H"):
    size = struct.calcsize(fmt)
    try:
        with open(f"/proc/{pid}/mem", "rb") as f:
            f.seek(addr)
            return struct.unpack(fmt, f.read(size))[0]
    except Exception:
        return None

def get_position_from_tracker():
    """Roda o template matching uma unica vez para pegar posicao atual."""
    from utils.calibrator import load_config
    from utils.screen import take_screenshot
    from utils.position_tracker import PositionTracker

    cfg = load_config()
    roi = cfg.get("minimap_roi", [0,0,100,100])
    tracker = PositionTracker(roi)

    print("[Tracker] Capturando posicao via template matching...")
    print("          (primeira rodada pode levar ate 45s, aguarde)\n")

    t0 = time.time()
    frame = take_screenshot()
    result = tracker.locate(frame, floor=None)

    if result and result.get("found"):
        x, y, z = result["x"], result["y"], result["z"]
        conf = result["confidence"]
        print(f"[Tracker] Posicao: X={x}  Y={y}  Z={z}  ({conf*100:.1f}%)  em {time.time()-t0:.0f}s\n")
        return x, y, z
    else:
        conf = result["confidence"] if result else 0.0
        print(f"[ERRO] Tracker falhou (conf={conf*100:.1f}%). Verifique o jogo e calibracao.")
        return None

def find_xyz_addresses(pid, regions, tx, ty, tz):
    """
    Busca na memoria por enderecos onde encontra [X, Y, Z] como uint16 consecutivos.
    Tambem testa uint32.
    """
    print(f"[Scan] Procurando X={tx}, Y={ty}, Z={tz} na memoria...")
    print(f"[Scan] {len(regions)} regioes para varrer...\n")

    candidates_16 = []  # (addr_x, addr_y, addr_z)
    candidates_32 = []

    for i, (start, end) in enumerate(regions):
        data = read_region(pid, start, end)
        if not data or len(data) < 8:
            continue

        # --- uint16 search ---
        hits_x = search_uint16(data, tx)
        for off_x in hits_x:
            # testa Y em off_x+2 e off_x+4
            for off_y_delta in [2, 4]:
                off_y = off_x + off_y_delta
                if off_y + 2 > len(data):
                    continue
                vy = struct.unpack_from("<H", data, off_y)[0]
                if vy != ty:
                    continue
                # testa Z nos proximos bytes
                for off_z_delta in [2, 4]:
                    off_z = off_y + off_z_delta
                    if off_z + 2 > len(data):
                        continue
                    vz = struct.unpack_from("<H", data, off_z)[0]
                    if vz == tz:
                        addr_x = start + off_x
                        addr_y = start + off_y
                        addr_z = start + off_z
                        candidates_16.append((addr_x, addr_y, addr_z))

        # --- uint32 search ---
        if len(data) >= 4:
            hits_x32 = search_uint32(data, tx)
            for off_x in hits_x32:
                for off_y_delta in [4, 8]:
                    off_y = off_x + off_y_delta
                    if off_y + 4 > len(data):
                        continue
                    vy = struct.unpack_from("<I", data, off_y)[0]
                    if vy != ty:
                        continue
                    for off_z_delta in [4, 8]:
                        off_z = off_y + off_z_delta
                        if off_z + 4 > len(data):
                            continue
                        vz = struct.unpack_from("<I", data, off_z)[0]
                        if vz == tz:
                            addr_x = start + off_x
                            addr_y = start + off_y
                            addr_z = start + off_z
                            candidates_32.append((addr_x, addr_y, addr_z))

        if (i+1) % 20 == 0:
            print(f"  [{i+1}/{len(regions)}] uint16:{len(candidates_16)}  uint32:{len(candidates_32)}", end="\r")

    print(f"\n[Scan] Concluido! uint16: {len(candidates_16)} candidatos | uint32: {len(candidates_32)} candidatos")
    return candidates_16, candidates_32

def validate_candidate(pid, addr_x, addr_y, addr_z, fmt):
    """Mostra valores atuais e pede confirmacao do usuario."""
    vx = read_val(pid, addr_x, fmt)
    vy = read_val(pid, addr_y, fmt)
    vz = read_val(pid, addr_z, fmt)
    print(f"    X={vx}  Y={vy}  Z={vz}   (enderecos: X={hex(addr_x)} Y={hex(addr_y)} Z={hex(addr_z)})")

def main():
    print("=" * 60)
    print("   LOCALIZADOR DE COORDS NA MEMORIA (Ancora por Mapa)")
    print("=" * 60)

    # 1. Pega posicao: via args (modo sudo) ou template matching
    if len(sys.argv) == 4:
        try:
            tx, ty, tz = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
            print(f"[OK] Coordenadas recebidas por argumento: X={tx}  Y={ty}  Z={tz}\n")
        except ValueError:
            print("[ERRO] Argumentos invalidos. Use: script.py X Y Z")
            sys.exit(1)
    else:
        pos = get_position_from_tracker()
        if pos is None:
            sys.exit(1)
        tx, ty, tz = pos

    # 2. Encontra o Tibia
    pid = find_tibia_pid()
    if not pid:
        print("[ERRO] Processo do Tibia nao encontrado!")
        sys.exit(1)
    print(f"[OK] Tibia PID: {pid}")

    # 3. Le regioes de memoria
    regions = get_rw_regions(pid)
    total_mb = sum(e-s for s,e in regions) / 1024 / 1024
    print(f"[OK] {len(regions)} regioes ({total_mb:.1f} MB)\n")

    # 4. Busca na memoria
    cands_16, cands_32 = find_xyz_addresses(pid, regions, tx, ty, tz)

    # 5. Mostra resultados
    all_cands = []
    for ax, ay, az in cands_16[:20]:
        all_cands.append((ax, ay, az, "<H"))
    for ax, ay, az in cands_32[:20]:
        all_cands.append((ax, ay, az, "<I"))

    if not all_cands:
        print("\n[ERRO] Nenhum candidato encontrado.")
        print("Dica: tente mover o personagem 1 tile e rode novamente.")
        sys.exit(1)

    print(f"\n[Resultado] {len(all_cands)} candidatos encontrados:\n")
    for i, (ax, ay, az, fmt) in enumerate(all_cands[:15]):
        label = "uint16" if fmt == "<H" else "uint32"
        vx = read_val(pid, ax, fmt)
        vy = read_val(pid, ay, fmt)
        vz = read_val(pid, az, fmt)
        print(f"  [{i:2d}] {label}  X={hex(ax)} ({vx})  Y={hex(ay)} ({vy})  Z={hex(az)} ({vz})")

    # 6. Usuario escolhe
    choice = 0
    if len(all_cands) > 1:
        try:
            choice = int(input(f"\nEscolha o candidato mais provavel [0]: ") or "0")
        except Exception:
            choice = 0

    ax, ay, az, fmt = all_cands[choice]
    print(f"\n[OK] Candidato escolhido: X={hex(ax)}  Y={hex(ay)}  Z={hex(az)}  ({fmt})")

    # 7. Monitor ao vivo para confirmar
    print("\n[Monitor] Ande pelo jogo e confirme se os valores mudam corretamente.")
    print("          X aumenta -> DIREITA | Y aumenta -> BAIXO | CTRL+C para salvar\n")
    try:
        while True:
            vx = read_val(pid, ax, fmt)
            vy = read_val(pid, ay, fmt)
            vz = read_val(pid, az, fmt)
            print(f"  X={vx}  Y={vy}  Z={vz}     ", end="\r", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\n[OK] Confirmado.")

    # 8. Salva no config
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            cfg = json.load(open(CONFIG_FILE))
        except Exception:
            pass

    cfg["mem_pid"]    = pid
    cfg["mem_x_addr"] = ax
    cfg["mem_y_addr"] = ay
    cfg["mem_z_addr"] = az
    cfg["mem_fmt"]    = fmt

    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

    print(f"[OK] Enderecos salvos no config.json!")
    print(f"     X: {hex(ax)}  Y: {hex(ay)}  Z: {hex(az)}")
    print(f"\nAgora o bot pode ler as coordenadas instantaneamente!")

if __name__ == "__main__":
    main()
