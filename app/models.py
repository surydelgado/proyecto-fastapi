from database.session import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func



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
    attendances = relationship("Attendance", back_populates="user")
    credentials = relationship ("Credential",back_populates="user")


#Eventos

class Event(Base):
    __tablename__= "events"
    id = Column(Integer, primary_key=True,index=True)
    title = Column(String(500), nullable=False)
    description =Column(Text)
    event_type =Column(String(100))
    audience = Column(String(30), default="publico")
    allowed_domains = Column(Text)
    allowed_emails = Column(Text)
    access_note = Column(Text)
    cover_image_url = Column(Text)
    requires_certificate = Column(Boolean, default=False)
    certificate_template = Column(String(100), default="default")
    certificate_title = Column(String(200))
    certificate_signer_name = Column(String(200))
    certificate_signer_role = Column(String(200))
    certificate_signer_image_url = Column(Text)
    requires_professor_signature = Column(Boolean, default=False)
    certificate_professor_signer_name = Column(String(200))
    certificate_professor_signer_role = Column(String(200))
    certificate_professor_signer_image_url = Column(Text)
    certificate_background_url = Column(Text)
    start_date = Column(DateTime,nullable=False)
    end_date = Column(DateTime, nullable= False)
    location = Column(String(150))
    status = Column (String(30), default="pending") #Este es el estado en el que se puede encontrar la solicituda, ya sea pendiente, aprobado o denegado
    is_active = Column(Boolean, default=True)


    creator_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", back_populates="events_created")
    attendances = relationship("Attendance", back_populates="event")
    credentials = relationship("Credential", back_populates="event")

#Attendance (QR)

class Attendance (Base):
    __tablename__="attendances"

    id =Column(Integer, primary_key= True, index = True)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_id = Column(Integer, ForeignKey("events.id"))
    attended = Column(Boolean, default=False)
    attended_at = Column(DateTime(timezone=True), nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="attendances")
    event = relationship("Event", back_populates="attendances")

#Microcredenciales
class Credential(Base):
    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True, index=True)
    credential_code = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    event_id = Column(Integer, ForeignKey("events.id"))
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    is_valid = Column(Boolean, default=True)
    certificate_url = Column(Text)

    user = relationship("User", back_populates="credentials")
    event = relationship("Event", back_populates="credentials")









    

