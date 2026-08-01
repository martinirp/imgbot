#!/usr/bin/env python3
"""
mem_scan.py - Encontra automaticamente os endereços de memória das coordenadas X, Y, Z do Tibia.
Uso: sudo ./venv/bin/python mem_scan.py
"""

import os
import sys
import struct
import time
import json
import subprocess

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("[AVISO] NumPy não encontrado. O scan será mais lento.")

CONFIG_FILE = "config.json"

def find_tibia_pid():
    try:
        result = subprocess.check_output(["pgrep", "-f", "Tibia/bin/client"], text=True).strip()
        pids = result.splitlines()
        best_pid = None
        best_mem = 0
        for pid in pids:
            pid = pid.strip()
            if not pid:
                continue
            try:
                with open(f"/proc/{pid}/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            mem = int(line.split()[1])
                            if mem > best_mem:
                                best_mem = mem
                                best_pid = int(pid)
                            break
            except Exception:
                pass
        return best_pid
    except Exception:
        return None

def get_scan_regions(pid):
    regions = []
    try:
        with open(f"/proc/{pid}/maps", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                addr_range = parts[0]
                perms = parts[1]
                pathname = parts[5] if len(parts) > 5 else ""
                if pathname and pathname != "[heap]" and pathname != "[stack]":
                    continue
                if 'r' not in perms or 'w' not in perms:
                    continue
                start, end = [int(x, 16) for x in addr_range.split('-')]
                size = end - start
                if size > 200 * 1024 * 1024 or size < 4096:
                    continue
                regions.append((start, end))
    except Exception as e:
        print(f"[ERRO] Não foi possível ler /proc/{pid}/maps: {e}")
    return regions

def take_snapshot(pid, regions):
    snapshot = {}
    try:
        with open(f"/proc/{pid}/mem", "rb") as mem_file:
            for start, end in regions:
                try:
                    mem_file.seek(start)
                    data = mem_file.read(end - start)
                    if data:
                        snapshot[start] = bytearray(data)
                except Exception:
                    pass
    except PermissionError:
        print("[ERRO] Permissão negada. Execute com: sudo ./venv/bin/python mem_scan.py")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO] Falha ao ler memória: {e}")
    return snapshot

def find_candidates(snap_before, snap_after, delta):
    """Encontra endereços onde uint16 mudou exatamente por 'delta'."""
    candidates = []
    size = 2
    for start, data_before in snap_before.items():
        if start not in snap_after:
            continue
        data_after = snap_after[start]
        min_len = min(len(data_before), len(data_after)) & ~1
        if HAS_NUMPY:
            arr_before = np.frombuffer(data_before[:min_len], dtype=np.uint16).astype(np.int32)
            arr_after  = np.frombuffer(data_after[:min_len],  dtype=np.uint16).astype(np.int32)
            indices = np.where(arr_after - arr_before == delta)[0]
            for idx in indices:
                candidates.append((start + int(idx)*size, int(arr_before[idx]), int(arr_after[idx])))
        else:
            for i in range(0, min_len, size):
                v1 = struct.unpack_from('<H', data_before, i)[0]
                v2 = struct.unpack_from('<H', data_after, i)[0]
                if int(v2) - int(v1) == delta:
                    candidates.append((start + i, v1, v2))
    return candidates

def filter_candidates(candidates, snap_before, snap_after, delta):
    """Filtra candidatos existentes pelos que mudaram por 'delta' entre dois snapshots."""
    filtered = []
    size = 2
    # Monta índice rápido para lookup
    snap_index = {start: data for start, data in snap_before.items()}
    snap_after_index = {start: data for start, data in snap_after.items()}

    for addr, _, _ in candidates:
        found = False
        for start, data_before in snap_index.items():
            end = start + len(data_before)
            if start <= addr < end:
                offset = addr - start
                if offset + size > len(data_before):
                    break
                if start not in snap_after_index:
                    break
                data_after = snap_after_index[start]
                if offset + size > len(data_after):
                    break
                v1 = struct.unpack_from('<H', data_before, offset)[0]
                v2 = struct.unpack_from('<H', data_after, offset)[0]
                if int(v2) - int(v1) == delta:
                    filtered.append((addr, v1, v2))
                found = True
                break
    return filtered

def read_value_at(pid, addr, dtype='<H'):
    size = struct.calcsize(dtype)
    try:
        with open(f"/proc/{pid}/mem", "rb") as mem_file:
            mem_file.seek(addr)
            data = mem_file.read(size)
            return struct.unpack(dtype, data)[0]
    except Exception:
        return None

def scan_coord(pid, regions, axis_name, direction_pos, direction_neg):
    """
    Escaneia a memória para encontrar o endereço de uma coordenada.
    Usa comparação cumulativa (sempre compara contra o snapshot base).
    Depois valida com direção reversa para eliminar contadores.
    """
    print(f"\n{'='*55}")
    print(f" PASSO: ENCONTRANDO COORDENADA {axis_name}")
    print(f"{'='*55}")

    print(f"\n 1. Deixe o personagem PARADO.")
    input(f" 2. Pressione ENTER aqui...")
    snap_base = take_snapshot(pid, regions)

    print(f"\n 3. Ande 1-2 tiles para {direction_pos} e pare.")
    input(f" 4. Quando parar, pressione ENTER aqui...")
    snap_cur = take_snapshot(pid, regions)
    total_moved = 1

    candidates = find_candidates(snap_base, snap_cur, delta=+1)
    # Tenta delta=2 caso tenha andado 2 tiles
    if len(candidates) > 5000:
        c2 = find_candidates(snap_base, snap_cur, delta=+2)
        if 0 < len(c2) < len(candidates):
            candidates = c2
            total_moved = 2
    print(f"[OK] {len(candidates)} candidatos encontrados.")

    rounds = 0
    while len(candidates) > 5 and rounds < 6:
        rounds += 1
        print(f"\n 5. Ande mais 1-2 tiles para {direction_pos} e pare. (Rodada {rounds})")
        input(f" 6. Quando parar, pressione ENTER aqui...")
        snap_cur = take_snapshot(pid, regions)

        # Tenta vários deltas cumulativos
        best_new = []
        for try_delta in [total_moved + 1, total_moved + 2, total_moved + 3]:
            new_c = filter_candidates(candidates, snap_base, snap_cur, delta=try_delta)
            if len(new_c) > 0:
                best_new = new_c
                total_moved = try_delta
                break

        if not best_new:
            print(f"[AVISO] Rodada não filtrou. Mantendo {len(candidates)} candidatos.")
        else:
            candidates = best_new
            print(f"[OK] Filtrado! Restam {len(candidates)} candidatos. (Total ~{total_moved} tiles)")

    # Validação reversa: elimina contadores
    print(f"\n{'='*55}")
    print(f" VALIDAÇÃO REVERSA ({axis_name}): eliminando contadores")
    print(f"{'='*55}")
    print(f"\n [!] Ande {total_moved} tiles para {direction_neg} e pare.")
    print(f"     Coordenadas reais DIMINUEM. Contadores não diminuem.")
    input(f" Quando parar, pressione ENTER aqui...")
    snap_rev = take_snapshot(pid, regions)

    validated = filter_candidates(candidates, snap_cur, snap_rev, delta=-1)
    if not validated:
        # Tenta com delta maior (pode ter andado mais tiles na validação)
        for try_neg in [-2, -3]:
            validated = filter_candidates(candidates, snap_cur, snap_rev, delta=try_neg)
            if validated:
                break

    if validated:
        candidates = validated
        print(f"[OK] Após validação reversa: {len(candidates)} candidatos reais de {axis_name}.")
    else:
        print(f"[AVISO] Validação reversa zerou. Mantendo {len(candidates)} candidatos.")

    if not candidates:
        print(f"[ERRO] Nenhum candidato de {axis_name} encontrado.")
        return None

    print(f"\n[RESULTADO] Candidatos para {axis_name}:")
    for i, (addr, v1, v2) in enumerate(candidates[:10]):
        cur = read_value_at(pid, addr)
        print(f"  [{i}] {hex(addr)} | Valor atual: {cur}")

    chosen_addr = candidates[0][0]
    if len(candidates) > 1:
        try:
            choice = int(input(f"\nEscolha o índice [0]: ") or "0")
            chosen_addr = candidates[choice][0]
        except Exception:
            pass

    print(f"[OK] Endereço {axis_name} definido: {hex(chosen_addr)}")
    return chosen_addr

def scan_z(pid, regions):
    """Escaneia Z usando mudança de andar (escadas/buracos)."""
    print(f"\n{'='*55}")
    print(f" PASSO: ENCONTRANDO COORDENADA Z (ANDAR)")
    print(f"{'='*55}")
    print("\n Vá até uma ESCADA ou BURACO.")
    print(" Deixe o personagem PARADO no andar atual.")
    input(" Pressione ENTER aqui...")
    snap_z1 = take_snapshot(pid, regions)

    print("\n Suba ou desça 1 ANDAR pela escada.")
    input(" Quando chegar no outro andar, pressione ENTER aqui...")
    snap_z2 = take_snapshot(pid, regions)

    z_pos = find_candidates(snap_z1, snap_z2, delta=+1)
    z_neg = find_candidates(snap_z1, snap_z2, delta=-1)

    if len(z_neg) < len(z_pos) and len(z_neg) > 0:
        z_candidates = z_neg
        z_direction = -1
    else:
        z_candidates = z_pos
        z_direction = +1
    print(f"[OK] {len(z_candidates)} candidatos para Z.")

    print(f"\n [!] Volte ao andar original pela escada.")
    input(" Quando chegar, pressione ENTER aqui...")
    snap_z_rev = take_snapshot(pid, regions)
    z_validated = filter_candidates(z_candidates, snap_z2, snap_z_rev, delta=-z_direction)
    if z_validated:
        z_candidates = z_validated
        print(f"[OK] Após validação: {len(z_candidates)} candidatos de Z.")
    else:
        print(f"[AVISO] Validação zerou. Mantendo {len(z_candidates)} candidatos.")

    if not z_candidates:
        print("[AVISO] Z não encontrado.")
        return None

    print(f"\n[RESULTADO] Candidatos para Z:")
    for i, (addr, v1, v2) in enumerate(z_candidates[:10]):
        cur = read_value_at(pid, addr)
        print(f"  [{i}] {hex(addr)} | Valor atual: {cur}")

    z_addr = z_candidates[0][0]
    if len(z_candidates) > 1:
        try:
            choice = int(input(f"\nEscolha o índice do Z [0]: ") or "0")
            z_addr = z_candidates[choice][0]
        except Exception:
            pass

    print(f"[OK] Endereço Z definido: {hex(z_addr)}")
    return z_addr

def main():
    print("=" * 55)
    print("   SCANNER DE COORDENADAS DO TIBIA NA MEMÓRIA")
    print("=" * 55)

    pid = find_tibia_pid()
    if not pid:
        print("[ERRO] Processo do Tibia não encontrado! O jogo está aberto?")
        sys.exit(1)
    print(f"\n[OK] Tibia encontrado! PID: {pid}")

    print("[...] Lendo mapa de memória do processo...")
    regions = get_scan_regions(pid)
    if not regions:
        print("[ERRO] Nenhuma região de memória encontrada.")
        sys.exit(1)
    total_mb = sum(e - s for s, e in regions) / 1024 / 1024
    print(f"[OK] {len(regions)} regiões ({total_mb:.1f} MB para escanear)\n")

    x_addr = scan_coord(pid, regions, "X", "DIREITA (→)", "ESQUERDA (←)")
    if not x_addr:
        sys.exit(1)

    y_addr = scan_coord(pid, regions, "Y", "BAIXO (↓)", "CIMA (↑)")
    if not y_addr:
        sys.exit(1)

    z_resp = input("\nDeseja escanear o Z (andar/floor) também? (s/n): ").strip().lower()
    z_addr = None
    if z_resp == 's':
        z_addr = scan_z(pid, regions)

    # Monitor ao vivo
    print("\n" + "=" * 55)
    print(" VERIFICAÇÃO FINAL (Ctrl+C para parar e salvar)")
    print("=" * 55)
    print(" Ande pelos tiles para verificar:")
    print("   X aumenta → DIREITA, diminui → ESQUERDA")
    print("   Y aumenta → BAIXO,   diminui → CIMA")
    if z_addr:
        print("   Z muda ao subir/descer andares\n")
    try:
        while True:
            x_val = read_value_at(pid, x_addr)
            y_val = read_value_at(pid, y_addr)
            z_val = read_value_at(pid, z_addr) if z_addr else "N/A"
            print(f"  X={x_val} | Y={y_val} | Z={z_val}    ", end='\r', flush=True)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[OK] Monitor encerrado.")

    # Salva no config.json
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except Exception:
            pass

    config["mem_pid"] = pid
    config["mem_x_addr"] = x_addr
    config["mem_y_addr"] = y_addr
    if z_addr:
        config["mem_z_addr"] = z_addr

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

    print(f"\n[OK] Endereços salvos no config.json!")
    print(f"     X: {hex(x_addr)}")
    print(f"     Y: {hex(y_addr)}")
    if z_addr:
        print(f"     Z: {hex(z_addr)}")
    print("\nAgora o bot pode ler as coordenadas em tempo real!")

if __name__ == "__main__":
    main()
