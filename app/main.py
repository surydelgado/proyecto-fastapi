from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from app.api import event, user, attendance, auth, credentials
from app.config import supabase, supabase_admin

app = FastAPI(
    title="Sistema de Gestión de Eventos Académicos - PUCE Manabí",
    description="Sistema institucional para la gestión de eventos académicos",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(event.router, prefix="/events", tags=["events"])
app.include_router(user.router, prefix="/users", tags=["users"])
app.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
app.include_router(credentials.router, tags=["credentials"])

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/api/carousel-images")
async def get_carousel_images():
    """
    Obtiene las URLs públicas de las imágenes del bucket 'eventos'
    para mostrar en el carrusel de la página principal.
    """
    try:
        bucket_name = "eventos"
        
        # Usar cliente admin si está disponible, sino usar el cliente normal
        client = supabase_admin if supabase_admin else supabase
        
        # Listar archivos directamente del bucket (raíz)
        try:
            response = client.storage.from_(bucket_name).list()
        except Exception as e:
            return JSONResponse(content={"images": [], "error": f"No se pudo acceder al bucket: {str(e)}"})
        
        # Extraer la lista de archivos de la respuesta
        files_list = []
        if isinstance(response, list):
            files_list = response
        elif isinstance(response, dict):
            files_list = response.get('data', response.get('files', []))
        elif hasattr(response, 'data'):
            files_list = response.data if response.data else []
        elif hasattr(response, 'files'):
            files_list = response.files if response.files else []
        
        # Si la lista está vacía, retornar
        if not files_list or len(files_list) == 0:
            return JSONResponse(content={"images": []})
        
        # Filtrar solo imágenes (jpg, jpeg, png, webp)
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        image_files = []
        
        for file in files_list:
            # Manejar diferentes formatos de respuesta
            file_name = None
            if isinstance(file, dict):
                file_name = file.get('name') or file.get('filename') or file.get('id')
            elif isinstance(file, str):
                file_name = file
            
            if file_name and any(file_name.lower().endswith(ext) for ext in image_extensions):
                image_files.append(file_name)
        
        if not image_files:
            return JSONResponse(content={"images": []})
        
        # Obtener URLs públicas para cada imagen
        images = []
        for file_name in image_files:
            try:
                # Obtener URL pública directamente del bucket (sin carpeta)
                public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
                images.append({
                    "url": public_url,
                    "name": file_name
                })
            except Exception as e:
                # Si hay error al obtener una imagen, continuar con las demás
                continue
        
        return JSONResponse(content={"images": images})
    except Exception as e:
        # Si el bucket no existe o hay algún error, retornar lista vacía con error para debug
        import logging
        logging.error(f"Error al obtener imágenes del carrusel: {str(e)}")
        return JSONResponse(
            status_code=200,
            content={"images": [], "error": str(e)}
        )
