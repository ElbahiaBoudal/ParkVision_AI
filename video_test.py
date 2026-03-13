from ultralytics import YOLO
import cv2
import os

# Chemin du modèle
model_path = "model_data/weights/best.pt"
model = YOLO(model_path)

# Chemin de la vidéo
video_path = "data/video1.mp4"
output_dir = "data/output"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "video_output1.mp4")

# Ouvrir la vidéo
cap = cv2.VideoCapture(video_path)
width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps    = cap.get(cv2.CAP_PROP_FPS)

fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Prédiction
    results = model.predict(frame)

    # Frame annoté
    annotated_frame = results[0].plot()

    # Écrire le frame
    out.write(annotated_frame)

    # Affichage en direct (optionnel)
    cv2.imshow("YOLOv8 OBB", annotated_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
out.release()
cv2.destroyAllWindows()

print(f"✅ Vidéo traitée et sauvegardée ici : {output_path}")