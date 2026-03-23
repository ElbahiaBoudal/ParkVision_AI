import mlflow
import os

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


def get_or_create_experiment(name: str) -> str:
    experiment = mlflow.get_experiment_by_name(name)
    if experiment is None:
        return mlflow.create_experiment(name)
    return experiment.experiment_id


# ──────────────────────────────────────────
# TRAINING — Logger une session d'entraînement YOLO
# ──────────────────────────────────────────
def log_training_run(
    run_name: str,
    params: dict,        # ex: {"epochs": 50, "imgsz": 640, "batch": 16}
    metrics: dict,       # ex: {"mAP50": 0.91, "precision": 0.88, "recall": 0.85}
    model_path: str = None,  # chemin vers best.pt
):
    experiment_id = get_or_create_experiment("yolo_training")
    with mlflow.start_run(experiment_id=experiment_id, run_name=run_name):
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)
        if model_path and os.path.exists(model_path):
            mlflow.log_artifact(model_path, artifact_path="weights")
    print(f"[MLflow] Training run '{run_name}' logged.")


# ──────────────────────────────────────────
# PRODUCTION — Logger une détection IA reçue par l'API
# ──────────────────────────────────────────
def log_detection_event(
    parking_id: int,
    parking_name: str,
    free_spots: int,
    occupied_spots: int,
    total_spots: int,
):
    experiment_id = get_or_create_experiment("parking_detections")
    availability_rate = round((free_spots / total_spots) * 100, 1) if total_spots > 0 else 0.0

    with mlflow.start_run(
        experiment_id=experiment_id,
        run_name=f"detection_parking_{parking_id}",
    ):
        mlflow.log_params({
            "parking_id": parking_id,
            "parking_name": parking_name,
            "total_spots": total_spots,
        })
        mlflow.log_metrics({
            "free_spots": free_spots,
            "occupied_spots": occupied_spots,
            "availability_rate": availability_rate,
        })