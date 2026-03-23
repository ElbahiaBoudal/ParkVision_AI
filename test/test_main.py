import pytest
from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)

# ── Auth ──────────────────────────────────────────────────────

def test_register_success():
    """Créer un compte utilisateur"""
    res = client.post("/register", json={
        "username": "testuser",
        "email": "test@test.com",
        "password": "password123"
    })
    assert res.status_code == 200
    assert res.json()["username"] == "testuser"

def test_login_success():
    """Login avec bons identifiants"""
    client.post("/register", json={
        "username": "loginuser",
        "email": "login@test.com",
        "password": "password123"
    })
    res = client.post("/login", data={
        "username": "loginuser",
        "password": "password123"
    })
    assert res.status_code == 200
    assert "access_token" in res.json()    

def get_token():
    client.post("/register", json={
        "username": "parkinguser",
        "email": "parking@test.com",
        "password": "password123"
    })
    res = client.post("/login", data={
        "username": "parkinguser",
        "password": "password123"
    })
    return res.json()["access_token"]



def test_create_parking():
    """Créer un parking"""
    token = get_token()
    res = client.post("/api/parking",
        json={
            "name": "Parking Test",
            "location": "Rabat Centre",
            "latitude": 34.02,
            "longitude": -6.84,
            "total_spots": 50
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Parking Test"
    assert res.json()["total_spots"] == 50