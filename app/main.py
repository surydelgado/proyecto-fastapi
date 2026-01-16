from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pathlib import Path
from app.api import event, user, attendance

app = FastAPI()

# Configurar templates y archivos estáticos
# Obtener la ruta base del proyecto (dos niveles arriba de app/main.py)
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Aqui incluimos los routers para gestionar los eventos, usuarios y asistencias
app.include_router(event.router, prefix="/events", tags=["events"])
app.include_router(user.router, prefix= "/users", tags = ["users"])
app.include_router(attendance.router, prefix= "/attendance", tags = ["attendance"])

# Ruta para la página principal (interfaz web)
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

