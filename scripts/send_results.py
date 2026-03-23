import requests

BACKEND_URL = "http://localhost:8000/api/ai/update-detection"

TOKEN = "COLLE_ICI_TON_TOKEN"  # 🔥 IMPORTANT


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

        print("Status:", res.status_code)
        print("Response:", res.text)

    except Exception as e:
        print("Error sending detection:", e)