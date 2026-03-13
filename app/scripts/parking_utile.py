"""
parking_utile.py — Fonctions utilitaires pour la logique métier des parkings.
"""

from math import radians, cos, sin, asin, sqrt
from typing import List, Optional, Tuple


# -----------------------------
# CALCUL DE DISTANCE (Haversine)
# -----------------------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcule la distance en km entre deux points GPS (formule Haversine).
    """
    R = 6371  # rayon de la Terre en km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * R * asin(sqrt(a))


# -----------------------------
# TRI PAR DISTANCE
# -----------------------------

def get_parkings_sorted_by_distance(
    user_lat: float,
    user_lon: float,
    parkings: list,
    radius_km: float = 2.0,
) -> list:
    """
    Filtre les parkings dans le rayon donné et les trie par distance croissante.

    Args:
        user_lat: Latitude de l'utilisateur
        user_lon: Longitude de l'utilisateur
        parkings: Liste d'objets Parking SQLAlchemy
        radius_km: Rayon de recherche en kilomètres

    Returns:
        Liste de dicts {parking, distance_km} triés par distance
    """
    results = []

    for p in parkings:
        dist = haversine(user_lat, user_lon, p.latitude, p.longitude)
        if dist <= radius_km:
            results.append({
                "id": p.id,
                "name": p.name,
                "location": p.location,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "total_spots": p.total_spots,
                "vehicle_type": getattr(p, "vehicle_type", "all"),
                "height_limit": getattr(p, "height_limit", None),
                "distance_km": round(dist, 3),
            })

    results.sort(key=lambda x: x["distance_km"])
    return results


# -----------------------------
# RECOMMANDATION OPTIMALE (score multi-critères)
# -----------------------------

def compute_score(
    distance_km: float,
    free_spots: int,
    total_spots: int,
    max_distance: float,
) -> float:
    """
    Calcule un score de recommandation entre 0 et 100.

    Critères :
    - Distance (40%) : plus proche = meilleur score
    - Taux de disponibilité (60%) : plus de places libres = meilleur score
    """
    if total_spots == 0:
        return 0.0

    # Score distance : inversé et normalisé (0 = très loin, 1 = très proche)
    distance_score = max(0, 1 - (distance_km / max_distance))

    # Score disponibilité : taux de places libres
    availability_score = free_spots / total_spots

    # Score global pondéré
    score = (distance_score * 0.4 + availability_score * 0.6) * 100
    return round(score, 2)


def get_optimal_parking(
    user_lat: float,
    user_lon: float,
    enriched_parkings: list,
    radius_km: float = 5.0,
) -> Optional[dict]:
    """
    Recommande le meilleur parking selon un score combiné.

    Args:
        user_lat: Latitude de l'utilisateur
        user_lon: Longitude de l'utilisateur
        enriched_parkings: Liste de dicts {"parking": <Parking>, "free_spots": int}
        radius_km: Rayon de recherche en km

    Returns:
        Le meilleur parking avec son score, ou None si aucun trouvé
    """
    candidates = []

    for item in enriched_parkings:
        p = item["parking"]
        free_spots = item["free_spots"]

        dist = haversine(user_lat, user_lon, p.latitude, p.longitude)

        if dist > radius_km:
            continue

        if free_spots <= 0:
            continue

        score = compute_score(dist, free_spots, p.total_spots, radius_km)

        candidates.append({
            "id": p.id,
            "name": p.name,
            "location": p.location,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "total_spots": p.total_spots,
            "free_spots": free_spots,
            "occupied_spots": p.total_spots - free_spots,
            "vehicle_type": getattr(p, "vehicle_type", "all"),
            "height_limit": getattr(p, "height_limit", None),
            "distance_km": round(dist, 3),
            "availability_rate": round((free_spots / p.total_spots) * 100, 1),
            "score": score,
        })

    if not candidates:
        return None

    # Trier par score décroissant
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    return {
        "recommended": best,
        "reason": (
            f"Ce parking est recommandé car il est à {best['distance_km']} km "
            f"avec {best['free_spots']} place(s) disponible(s) "
            f"({best['availability_rate']}% de disponibilité). "
            f"Score : {best['score']}/100."
        ),
        "alternatives": candidates[1:3],  # 2 alternatives
    }


# -----------------------------
# GÉOCODAGE D'ADRESSE
# -----------------------------

def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Convertit une adresse texte en coordonnées GPS (lat, lon).
    Utilise l'API Nominatim d'OpenStreetMap (gratuite, sans clé API).

    Args:
        address: Adresse ou lieu (ex: "Tour Eiffel, Paris")

    Returns:
        Tuple (latitude, longitude) ou None si non trouvé
    """
    try:
        import urllib.request
        import urllib.parse
        import json

        encoded = urllib.parse.quote(address)
        url = (
            f"https://nominatim.openstreetmap.org/search"
            f"?q={encoded}&format=json&limit=1"
        )

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ParkingVisionApp/2.0"}
        )

        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

        if not data:
            return None

        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon

    except Exception:
        return None