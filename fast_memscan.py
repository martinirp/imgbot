#!/usr/bin/env python3
"""
fast_memscan.py - Acha X e Y do Tibia por scan diferencial puro.
Uso: sudo python3 fast_memscan.py
Funciona independente do template matching.
"""
import os, sys, struct, time, json
import numpy as np

CONFIG_FILE = "config.json"

def find_pid():
    for pat in ["Tibia/bin/client", "tibia", "Tibia"]:
        try:
            out = __import__("subprocess").check_output(["pgrep","-f",pat],text=True).strip()
            pids = [p for p in out.splitlines() if p.strip()]
            if pids: return int(pids[0])
        except: pass
    return None

def get_regions(pid):
    regions = []
    try:
        with open(f"/proc/{pid}/maps") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2: continue
                perms = parts[1]
                if "r" not in perms or "w" not in perms: continue
                start, end = [int(x,16) for x in parts[0].split("-")]
                if (end - start) < 4 or (end - start) > 1024*1024*1024: continue
                regions.append((start, end))
    except: pass
    return regions

def snapshot(pid, regions):
    snap = {}
    try:
        with open(f"/proc/{pid}/mem","rb") as f:
            for s, e in regions:
                try:
                    f.seek(s)
                    d = f.read(e - s)
                    if d: snap[s] = np.frombuffer(d, dtype=np.uint16).copy()
                except: pass
    except PermissionError:
        print("[ERRO] Permissao negada. Use: sudo python3 fast_memscan.py")
        sys.exit(1)
    return snap

def find_delta(snap1, snap2, delta, exclude_zero=True):
    hits = []
    for s, arr1 in snap1.items():
        if s not in snap2: continue
        arr2 = snap2[s]
        n = min(len(arr1), len(arr2))
        d = arr2[:n].astype(np.int32) - arr1[:n].astype(np.int32)
        idxs = np.where(d == delta)[0]
        for i in idxs:
            v = int(arr1[i])
            if exclude_zero and v < 100: continue  # ignora valores muito pequenos
            hits.append((s + i*2, v, int(arr2[i])))
    return hits

def filter_stable(candidates, snap1, snap2):
    # Keeps candidates where value did NOT change between snap1 and snap2
    stable = []
    for addr, v_before, _ in candidates:
        for s, arr in snap1.items():
            e = s + len(arr)*2
            if s <= addr < e:
                off = (addr - s)//2
                if off < len(arr) and s in snap2:
                    arr2 = snap2[s]
                    if off < len(arr2) and int(arr[off]) == int(arr2[off]):
                        stable.append((addr, v_before))
                break
    return stable

def read_u16(pid, addr):
    try:
        with open(f"/proc/{pid}/mem","rb") as f:
            f.seek(addr); return struct.unpack("<H", f.read(2))[0]
    except: return None

def main():
    print("="*55)
    print("  FAST MEMSCAN - Scan diferencial para X e Y")
    print("="*55)
    
    pid = find_pid()
    if not pid:
        print("[ERRO] Tibia nao encontrado!")
        sys.exit(1)
    print(f"[OK] Tibia PID: {pid}")
    
    regions = get_regions(pid)
    total = sum(e-s for s,e in regions)/1024/1024
    print(f"[OK] {len(regions)} regioes ({total:.0f} MB)\n")
    
    # === SCAN X ===
    print("[ PASSO 1: ENCONTRAR X ]")
    print("Fique PARADO. Pressione ENTER...")
    input()
    snap_before = snapshot(pid, regions)
    print("[OK] Snapshot tirado. Agora ande exatamente 1 tile para a DIREITA e pressione ENTER...")
    input()
    snap_after = snapshot(pid, regions)
    
    x_cands = find_delta(snap_before, snap_after, delta=+1)
    print(f"[OK] {len(x_cands)} candidatos de X (delta +1)")
    
    # Filtra rounds adicionais para X
    round_x = 0
    while len(x_cands) > 3 and round_x < 4:
        round_x += 1
        print(f"\nAinda {len(x_cands)} candidatos. Ande mais 1 tile para a DIREITA e pressione ENTER...")
        snap_before2 = snap_after
        input()
        snap_after2 = snapshot(pid, regions)
        x_new = []
        for addr, _, _ in x_cands:
            for s, arr in snap_before2.items():
                e = s + len(arr)*2
                if s <= addr < e:
                    off = (addr-s)//2
                    if s in snap_after2 and off < len(snap_after2[s]):
                        dv = int(snap_after2[s][off]) - int(arr[off])
                        if dv == 1:
                            x_new.append((addr, int(arr[off]), int(snap_after2[s][off])))
                    break
        if x_new:
            x_cands = x_new
            snap_after = snap_after2
        print(f"[OK] Restam {len(x_cands)} candidatos de X")
    
    # === SCAN Y ===
    print("\n[ PASSO 2: ENCONTRAR Y ]")
    print("Fique PARADO. Pressione ENTER...")
    input()
    snap_y_before = snapshot(pid, regions)
    print("[OK] Snapshot tirado. Ande exatamente 1 tile para BAIXO e pressione ENTER...")
    input()
    snap_y_after = snapshot(pid, regions)
    
    y_cands = find_delta(snap_y_before, snap_y_after, delta=+1)
    
    # X deve ter ficado ESTAVEL durante o scan de Y
    x_stable = filter_stable(x_cands, snap_y_before, snap_y_after)
    print(f"[OK] {len(y_cands)} candidatos de Y | {len(x_stable)} candidatos de X ainda estáveis")
    
    # === FILTRA VIZINHOS ===
    # O X e Y devem estar proximos na memoria (mesma struct)
    # Geralmente o layout e: X(2bytes) Y(2bytes) Z(2bytes)
    print("\n[Analise] Procurando X e Y adjacentes na memoria...")
    
    x_addrs = {addr for addr, _ in x_stable}
    y_addrs = {addr for addr, _, _ in y_cands}
    
    pairs = []
    for ax in x_addrs:
        for delta_xy in [2, 4, 6, 8]:
            ay = ax + delta_xy
            if ay in y_addrs:
                vx = read_u16(pid, ax)
                vy = read_u16(pid, ay)
                pairs.append((ax, ay, vx, vy, delta_xy))
    
    if not pairs:
        print("[AVISO] Nenhum par X/Y adjacente encontrado.")
        print("Candidatos de X:")
        for addr, _ in x_stable[:5]: print(f"  {hex(addr)} = {read_u16(pid, addr)}")
        print("Candidatos de Y:")
        for addr, _, _ in y_cands[:5]: print(f"  {hex(addr)} = {read_u16(pid, addr)}")
    else:
        print(f"[OK] {len(pairs)} par(es) X/Y encontrado(s):")
        for i, (ax, ay, vx, vy, d) in enumerate(pairs[:10]):
            print(f"  [{i}] X={hex(ax)}({vx}) Y={hex(ay)}({vy}) offset={d}b")
    
    # Escolha
    ax, ay = pairs[0][0], pairs[0][1]
    if len(pairs) > 1:
        try: idx = int(input("\nEscolha o par [0]: ") or "0")
        except: idx = 0
        ax, ay = pairs[idx][0], pairs[idx][1]
    
    # Z: procura valor 7 em ax+4 ou ax+6
    az = None
    for dz in [4, 6, 8, 2]:
        v = read_u16(pid, ax + dz)
        if v is not None and 0 <= v <= 15:
            az = ax + dz
            print(f"[OK] Z encontrado em {hex(az)} = {v}")
            break
    
    # Monitor
    print("\n[Monitor] Ande e veja se X/Y mudam. CTRL+C para salvar.\n")
    fmt = "<H"
    try:
        while True:
            vx = read_u16(pid, ax)
            vy = read_u16(pid, ay)
            vz = read_u16(pid, az) if az else "?"
            print(f"  X={vx}  Y={vy}  Z={vz}    ", end="\r", flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[OK] Confirmado!")
    
    # Salva
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try: cfg = json.load(open(CONFIG_FILE))
        except: pass
    cfg["mem_pid"] = pid
    cfg["mem_x_addr"] = ax
    cfg["mem_y_addr"] = ay
    if az: cfg["mem_z_addr"] = az
    cfg["mem_fmt"] = "<H"
    with open(CONFIG_FILE,"w") as f: json.dump(cfg, f, indent=4)
    print(f"[OK] Salvo! X={hex(ax)} Y={hex(ay)} Z={hex(az) if az else 'N/A'}")

if __name__ == "__main__":
    main()
