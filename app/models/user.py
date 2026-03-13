from sqlalchemy import Column, Integer, String, Float
from app.db.session import Base

class User(Base):

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String, unique=True, index=True)

    email = Column(String, unique=True)

    hashed_password = Column(String)

    car_model = Column(String, nullable=True)  # ex: "RS6 ABT", "Clio 4"