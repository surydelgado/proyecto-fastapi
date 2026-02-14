# Proyecto FastAPI - Gestión de Eventos Académicos

Sistema web para la gestión de eventos académicos (PUCE Manabí) con FastAPI,
plantillas HTML y servicios de notificaciones.

## Requisitos

- Python 3.11+
- Git
- Acceso a Supabase

## Configuración

Crea un archivo `.env` en la raíz del proyecto con estas variables:

```
SUPABASE_URL=
SUPABASE_KEY=
SUPABASE_SERVICE_KEY=
APP_BASE_URL=
QR_TOKEN_SECRET=
PUCE_ALLOWED_DOMAINS=pucesm.edu.ec
RESEND_KEY=
```

> Nota: en producción (Render) estas variables se configuran en el panel de
> Environment.

## Ejecutar en local

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Si necesitas exponer la app en la red local:

```
python run_server.py
```

## Despliegue en Render

El proyecto incluye `Dockerfile` y `render.yaml`, por lo que el flujo es:

1. Conectar el repositorio en Render (Blueprint).
2. Configurar variables de entorno en el servicio.
3. Deploy.

Cuando cambies variables de entorno en Render, usa **Save, rebuild and deploy**
para aplicar los cambios.

### Variables recomendadas en Render

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_KEY`
- `RESEND_KEY`
- `APP_BASE_URL` (URL pública del servicio Render)
- `QR_TOKEN_SECRET`
- `PUCE_ALLOWED_DOMAINS`

## Tests

```
pytest
```
