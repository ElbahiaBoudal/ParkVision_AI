from pydantic import BaseModel

class DetectionUpdate(BaseModel):

    parking_id: int
    free_spots: int
    occupied_spots: int  