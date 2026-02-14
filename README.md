#🧪 Sistema de Análisis de Sedimento Urinario mediante Inteligencia Artificial

Sistema web académico que permite analizar imágenes microscópicas de sedimento urinario mediante técnicas de Visión Computacional e Inteligencia Artificial, almacenando resultados en la nube con seguridad por usuario.

Proyecto desarrollado para las asignaturas:

Interacción Humano–Computador

Base de Datos en la Nube

📌 Descripción General

El sistema permite a un médico:

Iniciar sesión de manera segura.

Registrar pacientes.

Crear visitas clínicas.

Subir imágenes microscópicas (PNG/JPG).

Procesar automáticamente la imagen mediante un modelo de IA (YOLO).

Visualizar detecciones y conteo de partículas.

Guardar resultados en la nube.

El sistema está diseñado como herramienta académica experimental y no reemplaza diagnóstico médico profesional.

🧠 Modelo de Inteligencia Artificial

Se utiliza un modelo de detección de objetos basado en YOLO (You Only Look Once).

Clases detectadas:

Eritrocitos

Leucocitos

Células epiteliales

Cristales

Cilindros

Bacterias

Levaduras

El modelo devuelve:

Bounding boxes

Clase detectada

Nivel de confianza

Conteo total por clase

🏗️ Arquitectura del Sistema

Frontend → FastAPI Backend → Modelo YOLO → Supabase (PostgreSQL + Storage)

Componentes:

Backend: FastAPI

IA: YOLO

Base de datos: PostgreSQL (Supabase)

Storage: Supabase Storage

Autenticación: JWT

Deploy: Render

🗄️ Base de Datos

Base de datos en la nube implementada con Supabase (PostgreSQL).

Tablas principales:

profiles

patients

cases

visits

images

results

Características implementadas:

UUID como claves primarias

Foreign Keys

Row Level Security (RLS)

Multi-tenant por médico

Conexión segura HTTPS/TLS

🔐 Seguridad

Autenticación mediante JWT

Verificación de identidad del médico

Row Level Security (RLS)

Separación de datos por usuario

Conexión cifrada

Cada médico solo puede visualizar sus propios pacientes y resultados.

🖥️ Instalación Local
1️⃣ Clonar el repositorio
git clone https://github.com/usuario/sistema-sedimento-urinario.git
cd sistema-sedimento-urinario

2️⃣ Crear entorno virtual
python -m venv venv


Activar entorno:

Windows:

venv\Scripts\activate


Mac/Linux:

source venv/bin/activate

3️⃣ Instalar dependencias
pip install -r requirements.txt

4️⃣ Crear archivo .env

Crear un archivo .env en la raíz del proyecto:

SUPABASE_URL=tu_url_de_supabase
SUPABASE_KEY=tu_service_role_key
SECRET_KEY=tu_clave_secreta
MODEL_PATH=path_del_modelo.pt

5️⃣ Ejecutar el servidor
uvicorn main:app --reload


El sistema estará disponible en:

http://127.0.0.1:8000

🚀 Deploy

Backend desplegado en Render.

Para producción se debe:

Configurar variables de entorno en Render

Definir correctamente el puerto (PORT)

Establecer WEB_CONCURRENCY=1 si se requiere

🎯 Alcance del Proyecto

Incluye:

Subida de imágenes PNG/JPG

Procesamiento automático con IA

Almacenamiento en la nube

Visualización de resultados

Gestión de pacientes y visitas

No incluye:

Diagnóstico médico oficial

Integración hospitalaria

Análisis en tiempo real desde microscopio

Procesamiento 3D

🧩 Principios de Ingeniería Aplicados

SRP (Single Responsibility Principle)

Separación por capas

Inyección de dependencias

Arquitectura cliente-servidor

Seguridad por diseño

📚 Tecnologías Utilizadas

Python

FastAPI

YOLO

Supabase

PostgreSQL

JWT

Uvicorn

Render

⚠️ Limitaciones

El modelo puede mejorarse con más datos.

El tiempo de inferencia depende del entorno de ejecución.

Proyecto de carácter académico.

👩‍💻 Autora

Sury Nohelia Delgado Buste
Carrera de Software
Cuarto Semestre
Periodo 2025-02