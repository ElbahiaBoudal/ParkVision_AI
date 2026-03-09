from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .db import Base

class Parking(Base):
    __tablename__ = "parkings"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    total_spots = Column(Integer)

class ParkingSpot(Base):
    __tablename__ = "parking_spots"

    id = Column(Integer, primary_key=True)
    parking_id = Column(Integer, ForeignKey("parkings.id"))
    width = Column(Float)
    length = Column(Float)
    is_free = Column(Boolean)

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    width = Column(Float)
    length = Column(Float)