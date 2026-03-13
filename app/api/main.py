from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional

# Database
from app.db.session import Base, engine, get_db

# Models
from app.models.user import User
from app.models.parking import Parking
from app.models.detection import ParkingDetection

# Schemas
from app.schemas.user import UserRegister
from app.schemas.parking import ParkingCreate
from app.schemas.detection import DetectionUpdate

# Auth
from app.authentification.security import hash_password, verify_password
from app.authentification.auth import create_access_token, verify_token

# Scripts
from app.scripts.parking_utile import get_parkings_sorted_by_distance, get_optimal_parking, geocode_address
from app.scripts.notification import connected_clients, notify_parking_change
from app.scripts.car_data import get_car_info, search_car_models, get_all_makes

# Création des tables
Base.metadata.create_all(bind=engine)

# App FastAPI
app = FastAPI(
    title="ParkingVision API",
    description="API intelligente pour la recherche et recommandation de parkings disponibles.",
    version="2.0.0",
)

# CORS — Autorise toutes les origines à accéder à l'API (utile pour le frontend React/Flutter)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth2 — Schéma de sécurité : le token JWT est attendu dans le header Authorization: Bearer <token>
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


# ================================================================
# DÉPENDANCE GLOBALE — Récupérer l'utilisateur connecté
# ================================================================
# Cette fonction est injectée dans toutes les routes protégées.
# Elle décode le JWT, vérifie sa validité, puis retourne l'utilisateur
# correspondant depuis la base de données. Si le token est invalide
# ou si l'utilisateur n'existe pas, une erreur 401 est levée.
# ================================================================

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        username = verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur non autorisé")

    return user


# ================================================================
# AUTH — Inscription et connexion
# ================================================================

# POST /register
# ---------------------------------------------------------------
# Rôle : Créer un nouveau compte utilisateur.
# - Vérifie que le nom d'utilisateur n'est pas déjà pris.
# - Hash le mot de passe avant de le stocker (sécurité).
# - Retourne les informations de base du compte créé (id, username, email).
# Accès : Public (pas de token requis).
# ---------------------------------------------------------------
@app.post("/register", tags=["Auth"])
def register(user: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Utilisateur déjà existant")

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hash_password(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"id": new_user.id, "username": new_user.username, "email": new_user.email}


# POST /login
# ---------------------------------------------------------------
# Rôle : Authentifier un utilisateur et lui délivrer un token JWT.
# - Vérifie les identifiants (username + password).
# - Si valides, génère et retourne un access_token JWT.
# - Ce token devra être inclus dans toutes les requêtes suivantes
#   via le header : Authorization: Bearer <token>
# Accès : Public (pas de token requis).
# ---------------------------------------------------------------
@app.post("/login", tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Username ou password incorrect")

    return {"access_token": create_access_token(user.username), "token_type": "bearer"}


# ================================================================
# UTILISATEUR — Gestion du véhicule et du profil
# ================================================================

# POST /api/user/set-car
# ---------------------------------------------------------------
# Rôle : Enregistrer le véhicule personnel de l'utilisateur connecté.
# - Valide l'existence du modèle via l'API NHTSA.
# - Récupère automatiquement la hauteur du véhicule via API Ninjas.
# - Sauvegarde le modèle (ex: "Audi RS6") dans le profil utilisateur.
# - Ces informations seront utilisées par /api/parking/for-my-car
#   pour filtrer les parkings compatibles avec la taille du véhicule.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.post("/api/user/set-car", tags=["Utilisateur"])
def set_user_car(
    make: str = Query(..., description='Marque, ex: "Audi"'),
    model: str = Query(..., description='Modèle, ex: "RS6"'),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    car_info = get_car_info(make, model)
    if not car_info:
        raise HTTPException(
            status_code=404,
            detail=f"Modèle '{model}' introuvable pour '{make}'. Utilise /api/cars/search?query=... pour chercher."
        )

    current_user.car_model = f"{make} {model}"
    db.commit()

    return {
        "message": "Véhicule enregistré avec succès.",
        "make": make,
        "model": model,
        "vehicle_type": car_info["vehicle_type"],
        "height": car_info["height"],
    }


# GET /api/user/profile
# ---------------------------------------------------------------
# Rôle : Retourner le profil complet de l'utilisateur connecté.
# - Inclut : id, username, email, modèle du véhicule.
# - Si un véhicule est enregistré, enrichit la réponse avec
#   le type de véhicule (car/moto/truck) et la hauteur.
# - Utile pour afficher les infos de compte dans l'application.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.get("/api/user/profile", tags=["Utilisateur"])
def get_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    car_info = None
    if current_user.car_model:
        parts = current_user.car_model.split(" ", 1)
        if len(parts) == 2:
            car_info = get_car_info(parts[0], parts[1])

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "car_model": current_user.car_model,
        "vehicle_type": car_info["vehicle_type"] if car_info else None,
        "car_height": car_info["height"] if car_info else None,
    }


# ================================================================
# PARKINGS — CRUD
# ================================================================

# POST /api/parking
# ---------------------------------------------------------------
# Rôle : Ajouter un nouveau parking dans la base de données.
# - Reçoit les infos du parking : nom, adresse, coordonnées GPS,
#   nombre de places totales, type de véhicule accepté, hauteur max.
# - Ce parking sera ensuite visible dans les recherches et sur la carte.
# - Typiquement appelé par un administrateur ou un gestionnaire de parking.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.post("/api/parking", tags=["Parkings"])
def create_parking(
    data: ParkingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parking = Parking(
        name=data.name,
        location=data.location,
        latitude=data.latitude,
        longitude=data.longitude,
        total_spots=data.total_spots,
        vehicle_type=getattr(data, "vehicle_type", "all"),
        height_limit=getattr(data, "height_limit", None),
    )
    db.add(parking)
    db.commit()
    db.refresh(parking)
    return parking


# GET /api/parkings
# ---------------------------------------------------------------
# Rôle : Récupérer la liste complète de tous les parkings enregistrés.
# - Retourne tous les parkings sans filtre de distance ni de disponibilité.
# - Principalement utilisé pour afficher tous les marqueurs sur la carte.
# - Ne tient pas compte de la position de l'utilisateur.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.get("/api/parkings", tags=["Parkings"])
def get_parkings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Parking).all()


# ================================================================
# RECHERCHE — Trouver un parking selon différents critères
# ================================================================

# GET /api/parking/nearby-sorted
# ---------------------------------------------------------------
# Rôle : Rechercher les parkings proches d'une position GPS,
#        triés par distance croissante.
# Paramètres :
#   - lat / lon : position GPS actuelle de l'utilisateur
#   - radius    : rayon de recherche en km (défaut : 2 km)
#   - vehicle_type : filtrer par type de véhicule (car, moto, truck)
#   - min_free_spots : nombre minimum de places libres requis
# - Interroge la dernière détection IA pour connaître les places libres.
# - Idéal pour afficher les parkings disponibles autour de l'utilisateur.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.get("/api/parking/nearby-sorted", tags=["Recherche"])
def nearby_sorted_parking(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: float = Query(2.0),
    vehicle_type: Optional[str] = Query(None, description="car, moto, truck"),
    min_free_spots: int = Query(1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parkings = db.query(Parking).all()
    if not parkings:
        return {"message": "Aucun parking enregistré dans la base de données."}

    if vehicle_type:
        parkings = [p for p in parkings if getattr(p, "vehicle_type", "all") in ("all", vehicle_type)]

    if min_free_spots > 0:
        filtered = []
        for p in parkings:
            last = db.query(ParkingDetection).filter(ParkingDetection.parking_id == p.id).order_by(ParkingDetection.id.desc()).first()
            free = last.free_spots if last else p.total_spots
            if free >= min_free_spots:
                filtered.append(p)
        parkings = filtered

    return get_parkings_sorted_by_distance(lat, lon, parkings, radius)


# GET /api/parking/near-destination
# ---------------------------------------------------------------
# Rôle : Trouver des parkings proches d'une adresse texte (ex: "Gare de Lyon, Paris").
# - Géocode automatiquement l'adresse en coordonnées GPS.
# - Retourne les parkings triés par distance autour de cette destination.
# - Pratique pour chercher un parking avant d'arriver à un endroit précis.
# - Filtre optionnel par type de véhicule.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.get("/api/parking/near-destination", tags=["Recherche"])
def parking_near_destination(
    address: str = Query(..., description="Adresse ou lieu de destination"),
    radius: float = Query(2.0),
    vehicle_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    coords = geocode_address(address)
    if not coords:
        raise HTTPException(status_code=404, detail=f"Impossible de géolocaliser : '{address}'")

    lat, lon = coords
    parkings = db.query(Parking).all()

    if vehicle_type:
        parkings = [p for p in parkings if getattr(p, "vehicle_type", "all") in ("all", vehicle_type)]

    return {
        "destination": address,
        "coordinates": {"lat": lat, "lon": lon},
        "parkings": get_parkings_sorted_by_distance(lat, lon, parkings, radius),
    }


# GET /api/parking/for-my-car
# ---------------------------------------------------------------
# Rôle : Trouver les parkings compatibles avec le véhicule enregistré
#        par l'utilisateur connecté.
# - Récupère automatiquement le type et la hauteur du véhicule de l'utilisateur.
# - Filtre les parkings par type de véhicule accepté ET par hauteur maximale autorisée.
# - Évite à l'utilisateur d'arriver dans un parking où son véhicule ne rentre pas.
# - Nécessite d'avoir enregistré son véhicule via /api/user/set-car au préalable.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.get("/api/parking/for-my-car", tags=["Recherche"])
def parking_for_my_car(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: float = Query(2.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.car_model:
        raise HTTPException(status_code=400, detail="Enregistre ton véhicule d'abord via /api/user/set-car.")

    parts = current_user.car_model.split(" ", 1)
    car_info = get_car_info(parts[0], parts[1] if len(parts) > 1 else "")
    if not car_info:
        raise HTTPException(status_code=404, detail="Modèle de voiture non reconnu.")

    vehicle_type = car_info["vehicle_type"]
    car_height = car_info["height"]

    parkings = db.query(Parking).all()

    # Filtre par type de véhicule accepté par le parking
    compatible = [p for p in parkings if getattr(p, "vehicle_type", "all") in ("all", vehicle_type)]

    # Filtre par contrainte de hauteur (ex: parking souterrain avec barre de 2m)
    if car_height:
        compatible = [p for p in compatible if getattr(p, "height_limit", None) is None or p.height_limit >= car_height]

    if not compatible:
        return {"message": "Aucun parking compatible avec ton véhicule dans cette zone."}

    return {
        "car_model": current_user.car_model,
        "vehicle_type": vehicle_type,
        "car_height": car_height,
        "parkings": get_parkings_sorted_by_distance(lat, lon, compatible, radius),
    }


# ================================================================
# RECOMMANDATION — Meilleur parking selon un score combiné
# ================================================================

# GET /api/parking/recommend
# ---------------------------------------------------------------
# Rôle : Recommander LE meilleur parking selon un score combinant
#        la distance et le taux de disponibilité des places.
# - Contrairement à nearby-sorted (tri par distance uniquement), cette route
#   calcule un score optimal : un parking proche mais plein sera moins bien
#   classé qu'un parking légèrement plus loin mais très disponible.
# - Filtre optionnel par type de véhicule et rayon de recherche.
# - Utilise la dernière détection IA pour connaître les places libres réelles.
# - Idéal pour une recommandation "intelligente" en un seul appel.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.get("/api/parking/recommend", tags=["Recommandation"])
def recommend_parking(
    lat: float = Query(...),
    lon: float = Query(...),
    vehicle_type: Optional[str] = Query(None, description="car, moto, truck"),
    radius: float = Query(5.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parkings = db.query(Parking).all()
    if not parkings:
        raise HTTPException(status_code=404, detail="Aucun parking disponible.")

    enriched = []
    for p in parkings:
        if vehicle_type and getattr(p, "vehicle_type", "all") not in ("all", vehicle_type):
            continue
        last = db.query(ParkingDetection).filter(ParkingDetection.parking_id == p.id).order_by(ParkingDetection.id.desc()).first()
        enriched.append({"parking": p, "free_spots": last.free_spots if last else p.total_spots})

    if not enriched:
        raise HTTPException(status_code=404, detail="Aucun parking compatible avec ce type de véhicule.")

    result = get_optimal_parking(lat, lon, enriched, radius)
    if not result:
        raise HTTPException(status_code=404, detail="Aucun parking disponible dans ce rayon.")

    return result


# ================================================================
# DÉTECTIONS IA (YOLO) — Mise à jour et consultation de disponibilité
# ================================================================

# POST /api/ai/update-detection
# ---------------------------------------------------------------
# Rôle : Recevoir et enregistrer les résultats d'analyse du modèle YOLO.
# - Appelé automatiquement par le système de détection IA (caméras de parking).
# - Enregistre en base le nombre de places libres et occupées à un instant T.
# - Après enregistrement, notifie en temps réel tous les clients WebSocket
#   connectés pour mettre à jour l'affichage instantanément.
# - C'est le point d'entrée central du pipeline IA → API → frontend.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.post("/api/ai/update-detection", tags=["Détections"])
async def update_detection(
    data: DetectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parking = db.query(Parking).filter(Parking.id == data.parking_id).first()
    if not parking:
        raise HTTPException(status_code=404, detail="Parking non trouvé.")

    detection = ParkingDetection(
        parking_id=data.parking_id,
        free_spots=data.free_spots,
        occupied_spots=data.occupied_spots,
    )
    db.add(detection)
    db.commit()
    db.refresh(detection)

    # Notification temps réel via WebSocket à tous les clients connectés
    await notify_parking_change(parking.id, parking.name, data.free_spots)

    return {
        "message": "Détection mise à jour avec succès.",
        "parking": parking.name,
        "free_spots": data.free_spots,
        "occupied_spots": data.occupied_spots,
    }


# GET /api/parking/{parking_id}/availability
# ---------------------------------------------------------------
# Rôle : Consulter la disponibilité actuelle d'un parking spécifique.
# - Retourne la dernière détection IA connue pour ce parking.
# - Inclut : places libres, places occupées, total, taux de remplissage (%)
#   et un statut lisible ("disponible" ou "complet").
# - Si aucune détection n'a encore été reçue, considère toutes les places libres.
# - Utilisé par le frontend pour afficher l'état en temps réel d'un parking.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.get("/api/parking/{parking_id}/availability", tags=["Détections"])
def get_current_availability(
    parking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parking = db.query(Parking).filter(Parking.id == parking_id).first()
    if not parking:
        raise HTTPException(status_code=404, detail="Parking non trouvé.")

    last = db.query(ParkingDetection).filter(ParkingDetection.parking_id == parking_id).order_by(ParkingDetection.id.desc()).first()

    if not last:
        return {
            "parking_id": parking_id,
            "parking_name": parking.name,
            "free_spots": parking.total_spots,
            "occupied_spots": 0,
            "total_spots": parking.total_spots,
            "availability_rate": 100.0,
            "status": "unknown",
        }

    return {
        "parking_id": parking_id,
        "parking_name": parking.name,
        "free_spots": last.free_spots,
        "occupied_spots": last.occupied_spots,
        "total_spots": parking.total_spots,
        "availability_rate": round((last.free_spots / parking.total_spots) * 100, 1),
        "status": "disponible" if last.free_spots > 0 else "complet",
    }


# GET /api/parking/{parking_id}/history
# ---------------------------------------------------------------
# Rôle : Consulter l'historique des détections IA d'un parking.
# - Retourne les N dernières détections (défaut : 10) pour un parking donné.
# - Permet d'analyser l'évolution de la disponibilité dans le temps.
# - Utile pour générer des graphiques ou statistiques d'occupation.
# - Le paramètre `limit` permet de contrôler le nombre de résultats retournés.
# Accès : Protégé (JWT requis).
# ---------------------------------------------------------------
@app.get("/api/parking/{parking_id}/history", tags=["Détections"])
def get_detection_history(
    parking_id: int,
    limit: int = Query(10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parking = db.query(Parking).filter(Parking.id == parking_id).first()
    if not parking:
        raise HTTPException(status_code=404, detail="Parking non trouvé.")

    detections = db.query(ParkingDetection).filter(ParkingDetection.parking_id == parking_id).order_by(ParkingDetection.id.desc()).limit(limit).all()

    return {"parking_id": parking_id, "parking_name": parking.name, "history": detections}


# ================================================================
# VÉHICULES — Recherche de modèles via API NHTSA
# ================================================================

# GET /api/cars/search
# ---------------------------------------------------------------
# Rôle : Rechercher des modèles de voitures par mot-clé (autocomplétion).
# - Interroge l'API NHTSA (base officielle américaine des véhicules).
# - Utile pour afficher des suggestions pendant la saisie de l'utilisateur
#   dans le formulaire d'enregistrement du véhicule.
# - Exemple : query="audi" → retourne tous les modèles Audi disponibles.
# Accès : Public (pas de token requis).
# ---------------------------------------------------------------
@app.get("/api/cars/search", tags=["Véhicules"])
def search_cars(query: str = Query(..., description='Ex: "audi", "rs6", "clio"')):
    results = search_car_models(query)
    if not results:
        raise HTTPException(status_code=404, detail=f"Aucun modèle trouvé pour '{query}'.")
    return results


# GET /api/cars/makes
# ---------------------------------------------------------------
# Rôle : Retourner la liste complète de toutes les marques de véhicules.
# - Source : API NHTSA (National Highway Traffic Safety Administration).
# - Utilisé pour peupler une liste déroulante de marques dans le frontend.
# - Retourne également le nombre total de marques disponibles.
# - Si l'API NHTSA est indisponible, retourne une erreur 503.
# Accès : Public (pas de token requis).
# ---------------------------------------------------------------
@app.get("/api/cars/makes", tags=["Véhicules"])
def get_makes():
    makes = get_all_makes()
    if not makes:
        raise HTTPException(status_code=503, detail="API NHTSA indisponible.")
    return {"total": len(makes), "makes": makes}


# ================================================================
# WEBSOCKET — Notifications en temps réel
# ================================================================

# WS /ws/parking
# ---------------------------------------------------------------
# Rôle : Maintenir une connexion WebSocket pour recevoir des notifications
#        en temps réel sur la disponibilité des parkings.
# - Dès qu'une nouvelle détection IA est reçue via /api/ai/update-detection,
#   tous les clients WebSocket connectés sont notifiés instantanément.
# - Permet au frontend de mettre à jour l'affichage sans polling HTTP.
# - Gère proprement la déconnexion des clients (WebSocketDisconnect).
# - Peut être utilisé par l'application mobile ou le dashboard web.
# Accès : Public (pas de token JWT requis, connexion directe WebSocket).
# ---------------------------------------------------------------
@app.websocket("/ws/parking")
async def websocket_parking(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)