from sqlalchemy import Column, Integer
from app.db.session import Base

class ParkingDetection(Base):

    __tablename__ = "parking_detection"

    id = Column(Integer, primary_key=True, index=True)

    parking_id = Column(Integer)

    free_spots = Column(Integer)

    occupied_spots = Column(Integer)