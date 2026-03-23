from ultralytics import YOLO
import cv2
import time
import requests
import mlflow
import os

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

BACKEND_URL = "http://localhost:8000/api/ai/update-detection"

VIDEOS = {
    1: "data/video1.mp4",
    2: "data/video2.mp4",
    3: "data/video3.mp4",
}

# ⚠️ Mets tes vrais identifiants ici
USERNAME = "string"
PASSWORD = "string"

# ─────────────────────────────────────────────
# TOKEN
# ─────────────────────────────────────────────

def get_token():
    response = requests.post(
        "http://localhost:8000/login",
        data={
            "username": USERNAME,
            "password": PASSWORD
        }
    )

    print("LOGIN:", response.status_code, response.text)

    if response.status_code != 200:
        raise Exception("❌ Login failed")

    return response.json()["access_token"]


TOKEN = get_token()

# ─────────────────────────────────────────────
# MLflow (optionnel)
# ─────────────────────────────────────────────

USE_MLFLOW = False  # 🔥 mets False si erreur MLflow

if USE_MLFLOW:
    mlflow.set_tracking_uri("http://localhost:5000")
    mlflow.set_experiment("parking_inference")

# ─────────────────────────────────────────────
# MODEL
# ─────────────────────────────────────────────

model = YOLO("model_data/weights/runs_obb_parking_project_version_m_balanced_weights_best.pt")

# ─────────────────────────────────────────────
# SEND RESULT
# ─────────────────────────────────────────────

def send_detection(parking_id, free, occupied):
    data = {
        "parking_id": parking_id,
        "free_spots": free,
        "occupied_spots": occupied
    }

    headers = {
        "Authorization": f"Bearer {TOKEN}"
    }

    try:
        res = requests.post(BACKEND_URL, json=data, headers=headers)
        print(f"[✔] Parking {parking_id} → Free: {free}, Occupied: {occupied}")
    except Exception as e:
        print("[❌] Error sending:", e)

# ─────────────────────────────────────────────
# DETECTION
# ─────────────────────────────────────────────

def run_detection(video_path, parking_id):

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"❌ Impossible d'ouvrir {video_path}")
        return

    print(f"\n🚀 Start Parking {parking_id}")

    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame)

        free = 0
        occupied = 0

        boxes = results[0].boxes

        # ✅ IMPORTANT: éviter erreur None
        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                cls = int(box.cls[0])

                # ⚠️ adapte selon ton dataset
                if cls == 0:
                    free += 1
                else:
                    occupied += 1
        else:
            print("No detection")

        # 🔥 envoyer au backend
        send_detection(parking_id, free, occupied)

        # afficher vidéo annotée
        annotated = results[0].plot()
        cv2.imshow(f"Parking {parking_id}", annotated)

        if cv2.waitKey(1) == 27:
            break

        frame_count += 1

    cap.release()
    cv2.destroyAllWindows()

    print(f"✅ Parking {parking_id} terminé ({frame_count} frames)")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == "__main__":

    for parking_id, video_path in VIDEOS.items():
        run_detection(video_path, parking_id)