from pydantic import BaseModel

class ParkingCreate(BaseModel):

    name: str
    location: str
    latitude: float
    longitude: float
    total_spots: int