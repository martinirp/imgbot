import json
import os

ROUTES_DIR = "routes"

def ensure_routes_dir():
    if not os.path.exists(ROUTES_DIR):
        os.makedirs(ROUTES_DIR)

def list_routes():
    """
    Lista todos os arquivos de rota salvos na pasta 'routes/'.
    """
    ensure_routes_dir()
    files = [f for f in os.listdir(ROUTES_DIR) if f.endswith(".json")]
    return sorted(files)

def save_route(route_name, waypoints):
    """
    Salva uma lista de waypoints em 'routes/<route_name>.json'.
    """
    ensure_routes_dir()
    if not route_name.endswith(".json"):
        route_name += ".json"
    
    filepath = os.path.join(ROUTES_DIR, route_name)
    data = {
        "name": route_name.replace(".json", ""),
        "waypoints_count": len(waypoints),
        "waypoints": waypoints
    }
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"[RouteManager] Rota '{route_name}' salva com sucesso em '{filepath}'.")
        return True
    except Exception as e:
        print(f"[RouteManager] Erro ao salvar rota: {e}")
        return False

def load_route(route_name):
    """
    Carrega os waypoints de 'routes/<route_name>.json'.
    """
    ensure_routes_dir()
    if not route_name.endswith(".json"):
        route_name += ".json"
        
    filepath = os.path.join(ROUTES_DIR, route_name)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("waypoints", [])
        except Exception as e:
            print(f"[RouteManager] Erro ao carregar rota '{route_name}': {e}")
    return []
