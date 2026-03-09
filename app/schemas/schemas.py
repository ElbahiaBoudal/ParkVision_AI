from pydantic import BaseModel

class ParkingCreate(BaseModel):
    name: str
    latitude: float
    longitude: float
    total_spots: int

class ParkingResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    total_spots: int