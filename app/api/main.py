from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import cv2
import threading
import time

from app.db.session import Base, engine, get_db
from app.models.user import User
from app.models.parking import Parking
from app.models.detection import ParkingDetection
from app.schemas.user import UserRegister
from app.schemas.parking import ParkingCreate
from app.schemas.detection import DetectionUpdate
from app.authentification.security import hash_password, verify_password
from app.authentification.auth import create_access_token, verify_token
from app.scripts.parking_utile import get_parkings_sorted_by_distance, get_optimal_parking, geocode_address
from app.scripts.notification import connected_clients, notify_parking_change
from app.scripts.car_data import get_car_info, search_car_models, get_all_makes
from mlflow_utils.mlflow_tracker import log_detection_event
from ultralytics import YOLO
import asyncio
# ── OpenTelemetry Setup ───────────────────────────────────────────────────────
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
RESOURCE_ATTRIBUTES = ResourceAttributes
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
import os

# Configuration des ressources (Nom du service dans Jaeger)
resource = Resource.create({
    "service.name": "parkingvision-backend",
    "service.version": "2.0.0",
    "deployment.environment": "development"
})

# Setup du Provider de traces
tracer_provider = TracerProvider(resource=resource)

# Exportateur vers le container Jaeger (utilise l'URL définie dans docker-compose)
otlp_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317"),
    insecure=True
)

tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

# ── Fin Setup OTEL ────────────────────────────────────────────────────────────

app = FastAPI(title="ParkingVision API", version="2.0.0")

# Instrumentation automatique
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)

# ── Init ──────────────────────────────────────────────────────────────────────

model = YOLO("model_data/weights/runs_obb_parking_project_version_m_balanced_weights_best.pt")
latest_frames = {}

Base.metadata.create_all(bind=engine)



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


# ── Auth dependency ───────────────────────────────────────────────────────────

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        username = verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur non autorisé")
    return user


# ── Auth ──────────────────────────────────────────────────────────────────────

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


@app.post("/login", tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Username ou password incorrect")
    return {"access_token": create_access_token(user.username), "token_type": "bearer"}


# ── User ──────────────────────────────────────────────────────────────────────

@app.post("/api/user/set-car", tags=["Utilisateur"])
def set_user_car(
    make: str = Query(...),
    model: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    car_info = get_car_info(make, model)
    if not car_info:
        raise HTTPException(status_code=404, detail=f"Modèle '{model}' introuvable pour '{make}'.")
    current_user.car_model = f"{make} {model}"
    db.commit()
    return {"message": "Véhicule enregistré.", "make": make, "model": model, **car_info}


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


# ── Parkings CRUD ─────────────────────────────────────────────────────────────

@app.post("/api/parking", tags=["Parkings"])
def create_parking(data: ParkingCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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


@app.get("/api/parkings", tags=["Parkings"])
def get_parkings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Parking).all()


# ── Recherche ─────────────────────────────────────────────────────────────────

@app.get("/api/parking/nearby-sorted", tags=["Recherche"])
def nearby_sorted_parking(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: float = Query(2.0),
    vehicle_type: Optional[str] = Query(None),
    min_free_spots: int = Query(1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parkings = db.query(Parking).all()
    if not parkings:
        return {"message": "Aucun parking enregistré."}
    if vehicle_type:
        parkings = [p for p in parkings if getattr(p, "vehicle_type", "all") in ("all", vehicle_type)]
    if min_free_spots > 0:
        filtered = []
        for p in parkings:
            last = db.query(ParkingDetection).filter(ParkingDetection.parking_id == p.id).order_by(ParkingDetection.id.desc()).first()
            if (last.free_spots if last else p.total_spots) >= min_free_spots:
                filtered.append(p)
        parkings = filtered
    return get_parkings_sorted_by_distance(lat, lon, parkings, radius)


@app.get("/api/parking/near-destination", tags=["Recherche"])
def parking_near_destination(
    address: str = Query(...),
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
    compatible = [p for p in db.query(Parking).all()
                  if getattr(p, "vehicle_type", "all") in ("all", car_info["vehicle_type"])]
    if car_info["height"]:
        compatible = [p for p in compatible
                      if getattr(p, "height_limit", None) is None or p.height_limit >= car_info["height"]]
    if not compatible:
        return {"message": "Aucun parking compatible dans cette zone."}
    return {
        "car_model": current_user.car_model,
        "vehicle_type": car_info["vehicle_type"],
        "car_height": car_info["height"],
        "parkings": get_parkings_sorted_by_distance(lat, lon, compatible, radius),
    }


# ── Recommandation ────────────────────────────────────────────────────────────

@app.get("/api/parking/recommend", tags=["Recommandation"])
def recommend_parking(
    lat: float = Query(...),
    lon: float = Query(...),
    vehicle_type: Optional[str] = Query(None),
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
        raise HTTPException(status_code=404, detail="Aucun parking compatible.")
    result = get_optimal_parking(lat, lon, enriched, radius)
    if not result:
        raise HTTPException(status_code=404, detail="Aucun parking dans ce rayon.")
    return result


# ── Détections ────────────────────────────────────────────────────────────────

@app.post("/api/ai/update-detection", tags=["Détections"])
async def update_detection(
    data: DetectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parking = db.query(Parking).filter(Parking.id == data.parking_id).first()
    if not parking:
        raise HTTPException(status_code=404, detail="Parking non trouvé.")
    detection = ParkingDetection(parking_id=data.parking_id, free_spots=data.free_spots, occupied_spots=data.occupied_spots)
    db.add(detection)
    db.commit()
    db.refresh(detection)
    log_detection_event(
        parking_id=parking.id, parking_name=parking.name,
        free_spots=data.free_spots, occupied_spots=data.occupied_spots, total_spots=parking.total_spots,
    )
    await notify_parking_change(parking.id, parking.name, data.free_spots)
    return {"message": "Détection mise à jour.", "parking": parking.name, "free_spots": data.free_spots, "occupied_spots": data.occupied_spots}


@app.get("/api/parking/{parking_id}/availability", tags=["Détections"])
def get_availability(
    parking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parking = db.query(Parking).filter(Parking.id == parking_id).first()
    if not parking:
        raise HTTPException(status_code=404, detail="Parking non trouvé.")
    last = db.query(ParkingDetection).filter(ParkingDetection.parking_id == parking_id).order_by(ParkingDetection.id.desc()).first()
    if not last:
        return {"parking_id": parking_id, "parking_name": parking.name, "free_spots": parking.total_spots,
                "occupied_spots": 0, "total_spots": parking.total_spots, "availability_rate": 100.0, "status": "unknown"}
    return {
        "parking_id": parking_id,
        "parking_name": parking.name,
        "free_spots": last.free_spots,
        "occupied_spots": last.occupied_spots,
        "total_spots": parking.total_spots,
        "availability_rate": round((last.free_spots / parking.total_spots) * 100, 1),
        "status": "available" if last.free_spots > 0 else "full",
    }


@app.get("/api/parking/{parking_id}/history", tags=["Détections"])
def get_history(
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


# ── Véhicules ─────────────────────────────────────────────────────────────────

@app.get("/api/cars/search", tags=["Véhicules"])
def search_cars(query: str = Query(...)):
    results = search_car_models(query)
    if not results:
        raise HTTPException(status_code=404, detail=f"Aucun modèle trouvé pour '{query}'.")
    return results


@app.get("/api/cars/makes", tags=["Véhicules"])
def get_makes():
    makes = get_all_makes()
    if not makes:
        raise HTTPException(status_code=503, detail="API NHTSA indisponible.")
    return {"total": len(makes), "makes": makes}


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/parking")
async def websocket_parking(websocket: WebSocket):
    await websocket.accept()
    print(" NOUNEAU CLIENT CONNECTÉ !")
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)


# ── YOLO Stream ───────────────────────────────────────────────────────────────



# Récupérer la boucle d'événements principale au démarrage
main_loop = None

def send_detection_internal(parking_id: int, free: int, occupied: int):
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        # 1. Mise à jour DB
        db.add(ParkingDetection(parking_id=parking_id, free_spots=free, occupied_spots=occupied))
        db.commit()
        
        # 2. Notification WebSocket (Safe Threading)
        if main_loop:
            # On détermine le statut pour le toast
            status = "full" if free == 0 else "available"
            
            # On prépare le message pour le frontend
            data = {
                "parking_id": parking_id,
                "name": f"Parking {parking_id}", # Idéalement, récupère le vrai nom en DB
                "free_spots": free,
                "status": status
            }
            
            # Envoi sécurisé vers la boucle principale
            asyncio.run_coroutine_threadsafe(notify_parking_change(parking_id, data["name"], free), main_loop)
            
        print(f"[DB]  parking {parking_id} → free={free}")
    except Exception as e:
        print(f"[DB] Erreur : {e}")
        db.rollback()
    finally:
        db.close()


def run_detection_stream(video_path: str, parking_id: int):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f" Impossible d'ouvrir {video_path}")
        return
    print(f" Thread démarré parking {parking_id}")
    while True:
        with tracer.start_as_current_span("yolo_inference") as span:
            span.set_attribute("parking_id", parking_id)
            
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
                
            results = model(frame)
            # Tu peux ajouter des détails sur la détection dans Jaeger
            span.set_attribute("boxes_detected", len(results[0].obb) if results[0].obb is not None else 0)
        annotated = results[0].plot()
        _, buffer = cv2.imencode('.jpg', annotated)
        latest_frames[parking_id] = buffer.tobytes()
        free, occupied = 0, 0
        obb = results[0].obb
        if obb is not None and len(obb) > 0:
            for box in obb:
                cls_name = results[0].names[int(box.cls[0])].lower()
                if cls_name == "empty":
                    free += 1
                elif cls_name == "occupied":
                    occupied += 1
        print(f"[YOLO] Parking {parking_id} → free={free}, occupied={occupied}")
        send_detection_internal(parking_id, free, occupied)
        time.sleep(0.05)


@app.on_event("startup")
async def startup():
    global main_loop
    main_loop = asyncio.get_running_loop() # <--- Crucial
    
    for pid, path in {1: "data/video1.mp4", 2: "data/video2.mp4", 3: "data/video3.mp4"}.items():
        threading.Thread(target=run_detection_stream, args=(path, pid), daemon=True).start()
        print(f"Thread YOLO démarré pour parking {pid}")


@app.get("/api/parking/{parking_id}/stream", tags=["Stream"])
async def video_stream(parking_id: int):
    def generate():
        while True:
            if parking_id in latest_frames:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + latest_frames[parking_id] + b"\r\n"
            else:
                time.sleep(0.1)
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")