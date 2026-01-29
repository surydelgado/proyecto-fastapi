"""
Arranca el servidor en 0.0.0.0 para permitir acceso desde la red local (p. ej. celular).
Uso: python run_server.py
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
