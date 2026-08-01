"""
test_map_stitch.py - Teste de juncao dos tiles do minimap do TibiaMaps

Uso:
    python test_map_stitch.py           -> Gera mapa de TODOS os floors
    python test_map_stitch.py 7         -> Gera so o floor 7 (surface)
    python test_map_stitch.py 7 8       -> Gera floors 7 e 8
"""

import os
import sys
import re
import numpy as np
from PIL import Image

MINIMAP_DIR = "minimap"
OUTPUT_DIR  = "minimap_output"

def parse_tiles(minimap_dir):
    pattern = re.compile(r"Minimap_Color_(\d+)_(\d+)_(\d+)\.png$")
    tiles_by_floor = {}

    for fname in os.listdir(minimap_dir):
        m = pattern.match(fname)
        if not m:
            continue
        ox = int(m.group(1))
        oy = int(m.group(2))
        z  = int(m.group(3))
        fpath = os.path.join(minimap_dir, fname)
        tiles_by_floor.setdefault(z, []).append((ox, oy, fpath))

    return tiles_by_floor

def stitch_floor(tiles, z, output_dir):
    if not tiles:
        return None

    min_x = min(ox for ox, oy, _ in tiles)
    min_y = min(oy for ox, oy, _ in tiles)
    max_x = max(ox for ox, oy, _ in tiles) + 256
    max_y = max(oy for ox, oy, _ in tiles) + 256

    width  = max_x - min_x
    height = max_y - min_y

    print(f"  Floor {z}: {len(tiles)} tiles | Area: {width}x{height} px "
          f"| Coords: X[{min_x}..{max_x}] Y[{min_y}..{max_y}]")

    canvas = Image.new("RGB", (width, height), color=(0, 0, 0))

    loaded = 0
    for ox, oy, fpath in tiles:
        try:
            tile_img = Image.open(fpath).convert("RGB")
            if tile_img.size != (256, 256):
                tile_img = tile_img.resize((256, 256), Image.NEAREST)
            px = ox - min_x
            py = oy - min_y
            canvas.paste(tile_img, (px, py))
            loaded += 1
        except Exception as e:
            print(f"    Erro ao carregar {fpath}: {e}")

    print(f"    {loaded}/{len(tiles)} tiles carregados")

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"floor_{z}.png")
    canvas.save(out_path)
    print(f"    Salvo em: {out_path}  ({width}x{height} px, "
          f"{os.path.getsize(out_path) // 1024} KB)")
    return out_path, min_x, min_y, max_x, max_y

def main():
    requested_floors = None
    if len(sys.argv) > 1:
        try:
            requested_floors = [int(a) for a in sys.argv[1:]]
        except ValueError:
            print("Uso: python test_map_stitch.py [floor1] [floor2] ...")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  TIBIA MAP STITCHER - Teste de Composicao de Tiles")
    print(f"{'='*60}")
    print(f"  Pasta: {os.path.abspath(MINIMAP_DIR)}")
    print()

    if not os.path.isdir(MINIMAP_DIR):
        print(f"Pasta '{MINIMAP_DIR}' nao encontrada!")
        sys.exit(1)

    tiles_by_floor = parse_tiles(MINIMAP_DIR)

    if not tiles_by_floor:
        print("Nenhum tile encontrado na pasta minimap/")
        sys.exit(1)

    floors_found = sorted(tiles_by_floor.keys())
    total_tiles  = sum(len(v) for v in tiles_by_floor.values())

    print(f"Total de tiles encontrados: {total_tiles}")
    print(f"Floors disponiveis: {floors_found}")
    print()

    floors_to_process = requested_floors if requested_floors else floors_found

    results = {}
    for z in floors_to_process:
        if z not in tiles_by_floor:
            print(f"  Floor {z} nao encontrado nos tiles.")
            continue
        print(f"Processando Floor {z}...")
        result = stitch_floor(tiles_by_floor[z], z, OUTPUT_DIR)
        if result:
            path, xmin, ymin, xmax, ymax = result
            results[z] = {"file": path, "x": [xmin, xmax], "y": [ymin, ymax]}
        print()

    print(f"{'='*60}")
    print(f"  CONCLUIDO - {len(results)} floor(s) gerado(s)")
    print(f"  Pasta de saida: {os.path.abspath(OUTPUT_DIR)}/")
    print(f"{'='*60}\n")

    if results:
        print("Resumo de coordenadas por floor:")
        for z, info in sorted(results.items()):
            w = info['x'][1] - info['x'][0]
            h = info['y'][1] - info['y'][0]
            print(f"  Floor {z}: X[{info['x'][0]}..{info['x'][1]}] "
                  f"Y[{info['y'][0]}..{info['y'][1]}] "
                  f"({w}x{h} tiles de cobertura)")

if __name__ == "__main__":
    main()
