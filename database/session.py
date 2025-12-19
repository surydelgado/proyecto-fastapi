from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Engine
engine = create_engine (

    DATABASE_URL,
    pool_pre_ping= True

)

# Sesiones
SessionLocal = sessionmaker(
    bind= engine,
    autocommit = False,
    autoflush= False
    
)

# Base para los modelos
Base = declarative_base()
# Dependencia para FastAPI
def get_db ():
    db = SessionLocal()
    try:
        yield db

    finally:
        db.close()    
