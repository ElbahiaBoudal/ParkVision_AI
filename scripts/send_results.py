import requests

BACKEND_URL = "http://localhost:8000/api/ai/update-detection"


def send_detection(parking_id, free, occupied):

    data = {
        "parking_id": parking_id,
        "free_spots": free,
        "occupied_spots": occupied
    }

    try:

        requests.post(BACKEND_URL, json=data)

        print("Detection sent:", data)

    except Exception as e:

        print("Error sending detection:", e)