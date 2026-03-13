"""
car_data.py — Combinaison NHTSA + API Ninjas
- NHTSA  : valider que le modèle existe
- API Ninjas : récupérer la hauteur du modèle
"""

import httpx
from functools import lru_cache
import os
API_NINJAS_KEY = os.getenv("API_NINJAS_KEY")
NHTSA_BASE_URL = os.getenv("NHTSA_BASE_URL")
API_NINJAS_URL = os.getenv("API_NINJAS_URL")


# -----------------------------
# 1. NHTSA — Valider le modèle
# -----------------------------

@lru_cache(maxsize=200)
def get_models_for_make(make: str) -> list:
    """
    Retourne tous les modèles d'une marque via NHTSA.
    Cache intégré pour éviter les appels répétés.
    """
    try:
        response = httpx.get(
            f"{NHTSA_BASE_URL}/GetModelsForMake/{make}?format=json",
            timeout=10
        )
        data = response.json()
        return [item["Model_Name"] for item in data["Results"]]
    except Exception:
        return []


def validate_car_model(make: str, model: str) -> bool:
    """
    Vérifie via NHTSA que le modèle existe pour cette marque.

    Ex: validate_car_model("Audi", "RS6") → True
        validate_car_model("Audi", "XYZ") → False
    """
    models = get_models_for_make(make)
    return model.strip().upper() in [m.upper() for m in models]


# -----------------------------
# 2. API Ninjas — Récupérer la hauteur
# -----------------------------

@lru_cache(maxsize=200)
def get_car_height(make: str, model: str) -> float | None:
    """
    Récupère la hauteur du véhicule en mm via API Ninjas.
    Convertit en mètres pour la comparaison avec height_limit des parkings.

    Ex: get_car_height("Audi", "RS6") → 1.46

    Returns:
        Hauteur en mètres (ex: 1.46) ou None si introuvable
    """
    try:
        response = httpx.get(
            API_NINJAS_URL,
            headers={"X-Api-Key": API_NINJAS_KEY},
            params={"make": make, "model": model, "limit": 1},
            timeout=10
        )
        data = response.json()

        if not data:
            return None

        car = data[0]

        # API Ninjas retourne la hauteur en mm dans le champ "height_mm"
        height_mm = car.get("height_mm") or car.get("height")

        if height_mm:
            return round(float(height_mm) / 1000, 2)  # convertir mm → mètres

        return None

    except Exception:
        return None


# -----------------------------
# 3. Fonction principale — infos complètes
# -----------------------------

def get_car_info(make: str, model: str) -> dict | None:
    """
    Retourne les infos complètes d'un véhicule :
    1. NHTSA valide que le modèle existe
    2. API Ninjas récupère la hauteur

    Args:
        make: Marque (ex: "Audi")
        model: Modèle (ex: "RS6")

    Returns:
        {
            "make": "Audi",
            "model": "RS6",
            "vehicle_type": "car",
            "height": 1.46       ← en mètres
        }
        ou None si le modèle n'existe pas
    """
    # Étape 1 — NHTSA : valider le modèle
    if not validate_car_model(make, model):
        return None

    # Étape 2 — API Ninjas : récupérer la hauteur
    height = get_car_height(make, model)

    # Étape 3 — Déterminer le type de véhicule
    vehicle_type = get_vehicle_type(make, model)

    return {
        "make": make,
        "model": model,
        "vehicle_type": vehicle_type,
        "height": height,  # None si API Ninjas ne trouve pas
    }


# -----------------------------
# 4. Déterminer le type de véhicule
# -----------------------------

def get_vehicle_type(make: str, model: str) -> str:
    """
    Détermine le type : "car", "truck" ou "moto"
    """
    MOTO_MAKES = [
        "yamaha", "kawasaki", "ducati", "ktm",
        "triumph", "harley-davidson", "bmw motorrad", "suzuki"
    ]
    TRUCK_KEYWORDS = [
        "transit", "sprinter", "master", "ranger",
        "hilux", "f-150", "pickup", "transporter"
    ]

    if make.lower() in MOTO_MAKES:
        return "moto"

    if any(kw in model.lower() for kw in TRUCK_KEYWORDS):
        return "truck"

    return "car"


# -----------------------------
# 5. Recherche / Autocomplétion
# -----------------------------

def search_car_models(query: str) -> list:
    """
    Recherche des modèles via NHTSA pour l'autocomplétion.
    """
    query = query.strip().lower()
    results = []

    POPULAR_MAKES = [
        "Audi", "BMW", "Mercedes-Benz", "Volkswagen", "Renault",
        "Peugeot", "Toyota", "Ford", "Honda", "Hyundai",
        "Kia", "Nissan", "Fiat", "Opel", "Seat",
        "Skoda", "Volvo", "Porsche", "Ferrari", "Tesla", "Mazda",
    ]

    for make in POPULAR_MAKES:
        if query in make.lower():
            models = get_models_for_make(make)
            for model in models[:20]:
                results.append({"make": make, "model": model})
            if results:
                break
        else:
            models = get_models_for_make(make)
            for model in models:
                if query in model.lower():
                    results.append({"make": make, "model": model})

    return results[:30]


# -----------------------------
# 6. Toutes les marques
# -----------------------------

def get_all_makes() -> list:
    """Retourne toutes les marques via NHTSA."""
    try:
        response = httpx.get(
            f"{NHTSA_BASE_URL}/GetAllMakes?format=json",
            timeout=10
        )
        data = response.json()
        return [item["Make_Name"] for item in data["Results"]]
    except Exception:
        return []