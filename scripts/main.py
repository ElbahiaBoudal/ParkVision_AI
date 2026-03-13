from ultralytics import YOLO
import cv2
from send_results import send_detection

model = YOLO("model_data/weights/best.pt")

VIDEO_PATH = "data/video1.mp4"
PARKING_ID = 1


def run_detection():

    cap = cv2.VideoCapture(VIDEO_PATH)

    while True:

        ret, frame = cap.read()

        if not ret:
            break

        results = model(frame)

        free = 0
        occupied = 0

        for box in results[0].boxes:

            cls = int(box.cls)

            if cls == 0:
                free += 1
            else:
                occupied += 1

        send_detection(PARKING_ID, free, occupied)

        annotated = results[0].plot()

        cv2.imshow("Detection", annotated)

        if cv2.waitKey(1) == 27:
            break

    cap.release()


if __name__ == "__main__":
    run_detection()