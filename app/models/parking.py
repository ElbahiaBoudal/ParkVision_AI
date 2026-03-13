from sqlalchemy import Column, Integer, String, Float
from app.db.session import Base

class Parking(Base):

    __tablename__ = "parkings"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String)

    location = Column(String)

    latitude = Column(Float)

    longitude = Column(Float)

    total_spots = Column(Integer)

    vehicle_type = Column(String, default="all")  # "car", "moto", "truck", "all"

    height_limit = Column(Float, nullable=True)   # hauteur max en mètres, ex: 2.0