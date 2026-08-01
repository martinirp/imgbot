#!/usr/bin/env python3
"""
mem_scan.py - Encontra automaticamente os endereços de memória das coordenadas X, Y do Tibia.
Uso: sudo python3 mem_scan.py
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
    """Encontra o PID do processo do Tibia automaticamente."""
    try:
        result = subprocess.check_output(["pgrep", "-f", "Tibia/bin/client"], text=True).strip()
        pids = result.splitlines()
        # Pega o processo com maior uso de memória (o jogo principal)
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
    """
    Lê /proc/PID/maps e retorna apenas regiões anônimas de leitura/escrita (heap/stack/data).
    Ignora bibliotecas .so mapeadas em arquivo.
    """
    regions = []
    try:
        with open(f"/proc/{pid}/maps", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 2:
                    continue
                addr_range = parts[0]
                perms = parts[1]
                # Arquivo mapeado (biblioteca, etc.) - pula
                pathname = parts[5] if len(parts) > 5 else ""
                if pathname and pathname != "[heap]" and pathname != "[stack]":
                    continue
                # Só regiões leitura+escrita (rw) sem execução
                if 'r' not in perms or 'w' not in perms:
                    continue
                start, end = [int(x, 16) for x in addr_range.split('-')]
                size = end - start
                # Ignora regiões muito grandes (> 200MB) ou muito pequenas (< 4KB)
                if size > 200 * 1024 * 1024 or size < 4096:
                    continue
                regions.append((start, end))
    except Exception as e:
        print(f"[ERRO] Não foi possível ler /proc/{pid}/maps: {e}")
    return regions

def take_snapshot(pid, regions):
    """Lê todas as regiões de memória e retorna um dicionário {start_addr: bytes}."""
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
        print("[ERRO] Permissão negada para ler a memória do processo.")
        print("       Execute este script com: sudo python3 mem_scan.py")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO] Falha ao ler memória: {e}")
    return snapshot

def find_candidates(snapshot_before, snapshot_after, delta, dtype=np.uint16 if HAS_NUMPY else None):
    """
    Encontra endereços onde o valor mudou exatamente por 'delta'.
    Retorna lista de (endereço_absoluto, valor_antes, valor_depois).
    """
    candidates = []
    size = 2  # uint16 = 2 bytes

    for start, data_before in snapshot_before.items():
        if start not in snapshot_after:
            continue
        data_after = snapshot_after[start]
        min_len = min(len(data_before), len(data_after))

        if HAS_NUMPY:
            # Versão rápida com NumPy
            arr_before = np.frombuffer(data_before[:min_len & ~1], dtype=np.uint16).astype(np.int32)
            arr_after  = np.frombuffer(data_after[:min_len & ~1],  dtype=np.uint16).astype(np.int32)
            diff = arr_after - arr_before
            indices = np.where(diff == delta)[0]
            for idx in indices:
                byte_offset = int(idx) * size
                addr = start + byte_offset
                v1 = int(arr_before[idx])
                v2 = int(arr_after[idx])
                candidates.append((addr, v1, v2))
        else:
            # Versão lenta sem NumPy
            for i in range(0, min_len - size, size):
                v1 = struct.unpack_from('<H', data_before, i)[0]
                v2 = struct.unpack_from('<H', data_after, i)[0]
                if int(v2) - int(v1) == delta:
                    candidates.append((start + i, v1, v2))

    return candidates

def filter_candidates(candidates, snapshot_before, snapshot_after, delta):
    """Filtra a lista de candidatos existente para os que mudaram por 'delta' novamente."""
    filtered = []
    size = 2

    for addr, _, _ in candidates:
        # Encontra qual região contém esse endereço
        for start, data_before in snapshot_before.items():
            end = start + len(data_before)
            if start <= addr < end:
                offset = addr - start
                if offset + size > len(data_before):
                    break
                if start not in snapshot_after:
                    break
                data_after = snapshot_after[start]
                if offset + size > len(data_after):
                    break
                v1 = struct.unpack_from('<H', data_before, offset)[0]
                v2 = struct.unpack_from('<H', data_after, offset)[0]
                if int(v2) - int(v1) == delta:
                    filtered.append((addr, v1, v2))
                break

    return filtered

def read_value_at(pid, addr, dtype='<H'):
    """Lê o valor atual em um endereço de memória."""
    size = struct.calcsize(dtype)
    try:
        with open(f"/proc/{pid}/mem", "rb") as mem_file:
            mem_file.seek(addr)
            data = mem_file.read(size)
            return struct.unpack(dtype, data)[0]
    except Exception:
        return None

def main():
    print("=" * 55)
    print("   SCANNER DE COORDENADAS DO TIBIA NA MEMÓRIA")
    print("=" * 55)

    # 1. Encontra o PID do Tibia
    pid = find_tibia_pid()
    if not pid:
        print("[ERRO] Processo do Tibia não encontrado!")
        print("       Certifique-se que o jogo está aberto.")
        sys.exit(1)
    print(f"\n[OK] Tibia encontrado! PID: {pid}")

    # 2. Lê as regiões de memória relevantes
    print("[...] Lendo mapa de memória do processo...")
    regions = get_scan_regions(pid)
    if not regions:
        print("[ERRO] Nenhuma região de memória encontrada.")
        sys.exit(1)
    total_mb = sum(e - s for s, e in regions) / 1024 / 1024
    print(f"[OK] {len(regions)} regiões encontradas ({total_mb:.1f} MB para escanear)")

    print("\n" + "=" * 55)
    print(" PASSO 1: ENCONTRANDO COORDENADA X")
    print("=" * 55)
    print("\n 1. Deixe o personagem PARADO no jogo.")
    input(" 2. Quando estiver parado, pressione ENTER aqui...")

    print("[...] Capturando snapshot inicial da memória...")
    snap1 = take_snapshot(pid, regions)
    print("[OK] Snapshot 1 capturado!")

    print("\n 3. Ande exatamente 1 tile para a DIREITA e pare.")
    input(" 4. Quando parar, pressione ENTER aqui...")

    print("[...] Capturando snapshot 2...")
    snap2 = take_snapshot(pid, regions)
    print(f"[...] Comparando snapshots (procurando valores que aumentaram em +1)...")
    x_candidates = find_candidates(snap1, snap2, delta=+1)
    print(f"[OK] {len(x_candidates)} candidatos para X encontrados.")

    # Repete para filtrar mais
    rounds = 0
    while len(x_candidates) > 5 and rounds < 5:
        rounds += 1
        print(f"\n 5. Ande mais 1 tile para a DIREITA e pare. (Rodada {rounds})")
        input(f" 6. Quando parar, pressione ENTER aqui...")
        snap_prev = snap2
        snap2 = take_snapshot(pid, regions)
        x_candidates = filter_candidates(x_candidates, snap_prev, snap2, delta=+1)
        print(f"[OK] Filtrado! Restam {len(x_candidates)} candidatos.")

    if not x_candidates:
        print("[ERRO] Nenhum candidato de X encontrado. Tente novamente.")
        sys.exit(1)

    print(f"\n[RESULTADO] Melhores candidatos para X:")
    for i, (addr, v1, v2) in enumerate(x_candidates[:10]):
        print(f"  [{i}] Endereço: {hex(addr)} | Valor atual: {v2}")

    x_addr = x_candidates[0][0]
    if len(x_candidates) > 1:
        try:
            choice = int(input(f"\nEscolha o índice do endereço correto [0]: ") or "0")
            x_addr = x_candidates[choice][0]
        except Exception:
            pass

    print(f"\n[OK] Endereço X definido: {hex(x_addr)}")

    print("\n" + "=" * 55)
    print(" PASSO 2: ENCONTRANDO COORDENADA Y")
    print("=" * 55)

    print("\n 1. Deixe o personagem PARADO.")
    input(" 2. Quando estiver parado, pressione ENTER aqui...")
    snap_y1 = take_snapshot(pid, regions)

    print("\n 3. Ande exatamente 1 tile para BAIXO e pare.")
    input(" 4. Quando parar, pressione ENTER aqui...")
    snap_y2 = take_snapshot(pid, regions)
    y_candidates = find_candidates(snap_y1, snap_y2, delta=+1)
    print(f"[OK] {len(y_candidates)} candidatos para Y encontrados.")

    rounds = 0
    best_y_candidates = y_candidates  # Guarda o melhor resultado caso zere
    while len(y_candidates) > 5 and rounds < 5:
        rounds += 1
        print(f"\n 5. Ande mais 1 tile para BAIXO e pare. (Rodada {rounds})")
        print("   IMPORTANTE: Ande apenas 1 tile e pare completamente antes de pressionar ENTER.")
        input(f" 6. Quando parar, pressione ENTER aqui...")
        snap_prev = snap_y2
        snap_y2 = take_snapshot(pid, regions)
        new_candidates = filter_candidates(y_candidates, snap_prev, snap_y2, delta=+1)
        if len(new_candidates) == 0:
            print(f"[AVISO] Filtragem zerou os candidatos (você pode ter andado mais de 1 tile).")
            print(f"        Mantendo os {len(y_candidates)} candidatos da rodada anterior.")
            break  # Mantém y_candidates como estava
        y_candidates = new_candidates
        best_y_candidates = y_candidates
        print(f"[OK] Filtrado! Restam {len(y_candidates)} candidatos.")

    if not y_candidates:
        print("[ERRO] Nenhum candidato de Y encontrado. Tente novamente.")
        sys.exit(1)

    print(f"\n[RESULTADO] Melhores candidatos para Y:")
    for i, (addr, v1, v2) in enumerate(y_candidates[:10]):
        print(f"  [{i}] Endereço: {hex(addr)} | Valor atual: {v2}")

    y_addr = y_candidates[0][0]
    if len(y_candidates) > 1:
        try:
            choice = int(input(f"\nEscolha o índice do endereço correto [0]: ") or "0")
            y_addr = y_candidates[choice][0]
        except Exception:
            pass

    print(f"[OK] Endereço Y definido: {hex(y_addr)}")

    # Verificação final
    print("\n" + "=" * 55)
    print(" VERIFICAÇÃO FINAL")
    print("=" * 55)
    print("Ande alguns tiles e veja se os valores mudam corretamente:")
    for _ in range(5):
        x_val = read_value_at(pid, x_addr)
        y_val = read_value_at(pid, y_addr)
        print(f"  X = {x_val} | Y = {y_val}")
        time.sleep(0.5)

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

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

    print(f"\n[OK] Endereços salvos no config.json!")
    print(f"     X addr: {hex(x_addr)}")
    print(f"     Y addr: {hex(y_addr)}")
    print("\nAgora o bot pode ler as coordenadas em tempo real!")

if __name__ == "__main__":
    main()
