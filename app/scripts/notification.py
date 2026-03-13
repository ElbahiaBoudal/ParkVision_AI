# app/scripts/notification.py

from fastapi import WebSocket

connected_clients: list[WebSocket] = []  # <-- tous les clients connectés

async def notify_parking_change(parking_id: int, parking_name: str, free_spots: int):
    if free_spots > 0:
        status = "available"
        message = f"Parking {parking_name} a {free_spots} places libres !"
    else:
        status = "full"
        message = f"Parking {parking_name} est COMPLET !"

    data = {
        "parking_id": parking_id,
        "name": parking_name,
        "free_spots": free_spots,
        "status": status,
        "message": message
    }

    for client in connected_clients.copy():
        try:
            await client.send_json(data)
        except:
            connected_clients.remove(client)