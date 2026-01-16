from fastapi import FastAPI
from app.api import event, user, attendance

app = FastAPI()
#Aqui incluimos los routers para gestionar los eventos, usuarios y asistencias

app.include_router(event.router, prefix="/events", tags=["events"])
app.include_router(user.router, prefix= "/users", tags = ["users"])
app.include_router(attendance.router, prefix= "/attendance", tags = ["attendance"])

#Definimos el metodo
@app.get ("/")
def read_root():
    return {"mensaje": "Bienvenido al sistema de gestion de eventos academicos."}

