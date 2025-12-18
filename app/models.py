from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.session import Base

#Usuarios

class User (Base):
    __tablename__= "users"

    id = Column(Integer, primary_key=True, index=True)
    names= Column(String(200), nullable=False)
    surnames = Column(String(200), nullable=False)
    cedula = Column(String(20), nullable=False)
    email = Column(String(200), unique= True, index=True, nullable=False)
    password_hash = Column(String(255), nullable = False)
    role = Column (String(20), default= "student") # Aqui los roles pueden ser, admin, teacher, student, external
    is_active = Column (Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    events_created = relationship("Event", back_populates="creator")
    attendaces = relationship("Attendance", back_populates= "user")
    credentials = relationship ("Credential",back_populates="user")




    

